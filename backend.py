#!/usr/bin/env python3
"""Authenticated Synology portal and direct-to-NAS download controller."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from email.message import Message
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import hashlib
import html
import ipaddress
import json
import logging
from logging.handlers import RotatingFileHandler
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import signal
import shlex
import shutil
import stat
import subprocess
import tarfile
import threading
import time
import unicodedata
import zipfile
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener, urlopen


ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("NAS_PORTAL_STATE_DIR", str(ROOT / "runtime"))).resolve()
STATE_FILE = STATE_DIR / "jobs.json"
TOKEN_FILE = STATE_DIR / "access_token"
AUTH_FILE = STATE_DIR / "credentials.json"
CONFIG_FILE = STATE_DIR / "config.json"
GOFILE_COOLDOWN_FILE = STATE_DIR / "gofile_cooldown.json"
SECRET_DIR = STATE_DIR / "job-secrets"


def load_config() -> dict[str, object]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"설정 파일을 읽을 수 없습니다: {CONFIG_FILE}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"설정 파일은 JSON 객체여야 합니다: {CONFIG_FILE}")
    return data


CONFIG = load_config()


def setting(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        value = CONFIG.get(name, default)
    return str(value).strip()


LISTEN_HOST = os.environ.get("NAS_PORTAL_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(setting("NAS_PORTAL_LISTEN_PORT", "8791"))
NAS_TARGET = setting("NAS_PORTAL_NAS_TARGET")
STATIC_DIR = Path(setting("NAS_PORTAL_STATIC_DIR", str(ROOT / "synology" / "web"))).resolve()
LAUNCHER_FILE_SETTING = setting("NAS_PORTAL_LAUNCHER_FILE")
LAUNCHER_FILE = Path(LAUNCHER_FILE_SETTING).resolve() if LAUNCHER_FILE_SETTING else None
PACKAGE_VERSION = setting("NAS_PORTAL_VERSION", "0.9.9")
SEVEN_ZIP = Path(setting("NAS_PORTAL_7ZZ", str(ROOT / "bin" / "7zz"))).resolve()
MAX_FILE_BYTES = 300 * 1024**3
MAX_ARCHIVE_ENTRIES = 100_000
MAX_EXTRACTED_BYTES = 1024**4
MAX_PARALLEL_DOWNLOADS = 3
BATCH_QUEUE_STAGGER_SECONDS = 20
GOFILE_MIN_REQUEST_INTERVAL_SECONDS = 2.0
GOFILE_RATE_LIMIT_COOLDOWN_SECONDS = 30 * 60
GOFILE_NETWORK_COOLDOWN_SECONDS = 5 * 60
GOFILE_MAX_COOLDOWN_SECONDS = 6 * 60 * 60
GIGAFILE_HOST = re.compile(r"^[a-z0-9-]+\.gigafile\.nu$", re.I)
BUZZHEAVIER_DOWNLOAD_HOST = re.compile(r"^[a-z0-9-]+\.buzzheavier\.com$", re.I)
BUZZHEAVIER_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,4096}$")
SAFE_SERVICE_ID = re.compile(r"^[A-Za-z0-9._~-]{1,256}$")
GOFILE_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
LOG_MAX_BYTES = 1024 * 1024
LOG_BACKUP_COUNT = 2
PASSWORD_HASH_ITERATIONS = 600_000
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_SESSION_ENTRIES = 256
LOGIN_FAILURE_LIMIT = 5
LOGIN_BLOCK_SECONDS = 15 * 60
LOGIN_FAILURE_RETENTION_SECONDS = 15 * 60
MAX_LOGIN_FAILURE_ENTRIES = 4096
REQUEST_BODY_LIMIT = 16_384
REQUEST_TIMEOUT_SECONDS = 30
LAUNCHER_SESSION_TTL_SECONDS = 60 * 60
LAUNCHER_ACCOUNT_RESET_WINDOW_SECONDS = 5 * 60
ARCHIVE_EXTRACT_TIMEOUT_SECONDS = 6 * 60 * 60
CURL_HTTPS_ONLY = "--proto '=https' --proto-redir '=https'"
LOGGER = logging.getLogger("nasdrop")
LOGGER.addHandler(logging.NullHandler())
JOB_SECRET_LOCK = threading.RLock()
CONFIG_LOCK = threading.RLock()
LAUNCHER_TOKEN_LOCK = threading.RLock()


def rotating_log_handler(path: str, max_bytes: int = LOG_MAX_BYTES, backup_count: int = LOG_BACKUP_COUNT):
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    return RotatingFileHandler(
        target, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8", delay=True,
    )


def configure_logging() -> None:
    for handler in list(LOGGER.handlers):
        LOGGER.removeHandler(handler)
        handler.close()
    log_path = setting("NAS_PORTAL_LOG_FILE")
    handler = rotating_log_handler(log_path) if log_path else logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%dT%H:%M:%S%z"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def bool_setting(name: str, default: bool = False) -> bool:
    return setting(name, "1" if default else "0").lower() in {"1", "true", "yes", "on"}


def parallel_limit_setting() -> int:
    try:
        value = int(setting("NAS_PORTAL_SAME_PROVIDER_LIMIT", "2"))
    except ValueError:
        value = 2
    return min(3, max(2, value))


def normalize_launcher_port(value: object) -> int:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("아이콘 외부 포트는 1~65535 사이의 숫자여야 합니다.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("아이콘 외부 포트는 1~65535 사이의 숫자여야 합니다.")
    return port


def launcher_port_setting() -> int:
    try:
        return normalize_launcher_port(setting("NAS_PORTAL_LAUNCHER_PORT", str(LISTEN_PORT)))
    except ValueError:
        return LISTEN_PORT


def normalize_download_mode(value: object) -> str:
    mode = str(value).strip().lower()
    if mode not in {"segmented", "single"}:
        raise ValueError("다운로드 방식은 분할 또는 단일 연결이어야 합니다.")
    return mode


def download_mode_setting() -> str:
    try:
        return normalize_download_mode(setting("NAS_PORTAL_DOWNLOAD_MODE", "segmented"))
    except ValueError:
        return "segmented"


ALLOW_SAME_PROVIDER_PARALLEL = bool_setting("NAS_PORTAL_ALLOW_SAME_PROVIDER_PARALLEL")
SAME_PROVIDER_LIMIT = parallel_limit_setting()
LAUNCHER_PORT = launcher_port_setting()
DOWNLOAD_MODE = download_mode_setting()
AUTO_EXTRACT_ARCHIVES = bool_setting("NAS_PORTAL_AUTO_EXTRACT_ARCHIVES", True)
DISK_PROTECTION = bool_setting("NAS_PORTAL_DISK_PROTECTION", True)
TRUST_FORWARDED_FOR = bool_setting("NAS_PORTAL_TRUST_FORWARDED_FOR", False)


def public_error_code(message: object) -> str:
    """Return a stable, non-sensitive category for API and persisted job errors."""
    value = str(message)
    rules = (
        (("로그인이 필요",), "auth_required"),
        (("ID 또는 비밀번호",), "invalid_credentials"),
        (("계정이 아직 설정",), "account_not_configured"),
        (("현재 비밀번호",), "current_password_invalid"),
        (("DSM 아이콘 연결",), "launcher_expired"),
        (("권한", "쓰기 권한", "볼 권한"), "permission_denied"),
        (("암호가 필요", "암호를 입력", "Wrong password", "password"), "password_required"),
        (("Gofile 요청이 몰려", "429", "제한되었"), "rate_limited"),
        (("연결하지 못", "HTTP ", "응답을 반환"), "network_error"),
        (("만료", "링크를 다시", "Copy download link"), "link_expired"),
        (("무결성", "손상", "크기가 예상값"), "integrity_failed"),
        (("압축", "7-Zip", "archive"), "archive_error"),
        (("지원 서비스", "정식 GigaFile", "정식 Gofile", "정식 Pixeldrain", "Buzzheavier"), "invalid_link"),
        (("작업", "파일 정보가 변경", "파일이 없습니다"), "invalid_job_state"),
        (("설정", "선택값", "선택해 주세요", "올바르지 않습니다"), "invalid_request"),
        (("찾을 수 없습니다",), "not_found"),
        (("재시작",), "service_restarted"),
        (("내부 처리",), "internal_error"),
    )
    for fragments, code in rules:
        if any(fragment.casefold() in value.casefold() for fragment in fragments):
            return code
    return "generic_error"


def storage_roots_setting() -> tuple[Path, ...]:
    configured = setting("NAS_PORTAL_STORAGE_ROOTS")
    candidates = [item.strip() for item in configured.split(",") if item.strip()] if configured else [
        str(path) for path in Path("/").iterdir() if re.fullmatch(r"volume[0-9]+", path.name) and path.is_dir()
    ]
    roots = []
    for value in candidates:
        root = Path(value).resolve()
        if not root.is_absolute() or root == Path(root.anchor) or not root.is_dir():
            continue
        if root not in roots:
            roots.append(root)
    return tuple(roots)


STORAGE_ROOTS = storage_roots_setting()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_launcher_token() -> str:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    temporary = TOKEN_FILE.with_suffix(".tmp")
    temporary.write_text(token + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(TOKEN_FILE)
    return token


LAUNCHER_TOKEN = load_launcher_token()


def normalize_username(value: object) -> str:
    username = str(value).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username):
        raise ValueError("ID는 영문, 숫자, 마침표, 밑줄, 하이픈을 사용해 3~32자로 입력하세요.")
    return username


def validate_password(value: object) -> str:
    if not isinstance(value, str) or not 10 <= len(value) <= 128:
        raise ValueError("비밀번호는 10~128자로 입력하세요.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("비밀번호에는 제어 문자를 사용할 수 없습니다.")
    return value


def load_credentials() -> dict[str, object]:
    if not AUTH_FILE.exists():
        return {}
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or data.get("algorithm") != "pbkdf2_sha256":
        return {}
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", str(data.get("username", ""))):
        return {}
    if not re.fullmatch(r"[0-9a-f]{32}", str(data.get("salt", ""))):
        return {}
    if not re.fullmatch(r"[0-9a-f]{64}", str(data.get("password_hash", ""))):
        return {}
    return data


CREDENTIALS = load_credentials()
SESSIONS: dict[str, tuple[str, float, str, float]] = {}
SESSIONS_LOCK = threading.Lock()
LOGIN_FAILURES: dict[str, tuple[int, float, float]] = {}
LOGIN_FAILURES_LOCK = threading.Lock()


def credentials_configured() -> bool:
    return bool(CREDENTIALS)


def password_hash(password: str, salt: bytes, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def verify_credentials(username: object, password: object) -> bool:
    if not CREDENTIALS or not isinstance(username, str) or not isinstance(password, str):
        return False
    stored_username = str(CREDENTIALS.get("username", ""))
    username_matches = secrets.compare_digest(
        username.strip().casefold().encode("utf-8"), stored_username.casefold().encode("utf-8"),
    )
    try:
        salt = bytes.fromhex(str(CREDENTIALS["salt"]))
        iterations = int(CREDENTIALS.get("iterations", PASSWORD_HASH_ITERATIONS))
        candidate = password_hash(password, salt, iterations)
    except (KeyError, TypeError, ValueError):
        return False
    hash_matches = secrets.compare_digest(candidate, str(CREDENTIALS.get("password_hash", "")))
    return username_matches and hash_matches


def create_session(username: str, kind: str = "session", ttl: int = SESSION_TTL_SECONDS) -> str:
    token = secrets.token_urlsafe(32)
    with SESSIONS_LOCK:
        current = time.time()
        expired = [value for value, (_, expiry, _, _) in SESSIONS.items() if expiry <= current]
        for value in expired:
            SESSIONS.pop(value, None)
        overflow = len(SESSIONS) - MAX_SESSION_ENTRIES + 1
        if overflow > 0:
            oldest = sorted(SESSIONS, key=lambda value: SESSIONS[value][3])[:overflow]
            for value in oldest:
                SESSIONS.pop(value, None)
        SESSIONS[token] = (username, current + ttl, kind, current)
    return token


def session_username(token: str) -> str:
    with SESSIONS_LOCK:
        session = SESSIONS.get(token)
        if not session:
            return ""
        username, expiry, _, _ = session
        if expiry <= time.time():
            SESSIONS.pop(token, None)
            return ""
        return username


def session_kind(token: str) -> str:
    with SESSIONS_LOCK:
        session = SESSIONS.get(token)
        if not session:
            return ""
        _, expiry, kind, _ = session
        if expiry <= time.time():
            SESSIONS.pop(token, None)
            return ""
        return kind


def launcher_account_reset_allowed(token: str) -> bool:
    with SESSIONS_LOCK:
        session = SESSIONS.get(token)
        if not session:
            return False
        _, expiry, kind, issued_at = session
        current = time.time()
        if expiry <= current:
            SESSIONS.pop(token, None)
            return False
        return kind == "launcher" and current - issued_at <= LAUNCHER_ACCOUNT_RESET_WINDOW_SECONDS


def revoke_session(token: str) -> None:
    with SESSIONS_LOCK:
        SESSIONS.pop(token, None)


def replace_credentials(username: object, password: object) -> str:
    global CREDENTIALS
    normalized_username = normalize_username(username)
    normalized_password = validate_password(password)
    salt = secrets.token_bytes(16)
    updated = {
        "algorithm": "pbkdf2_sha256",
        "iterations": PASSWORD_HASH_ITERATIONS,
        "username": normalized_username,
        "salt": salt.hex(),
        "password_hash": password_hash(normalized_password, salt),
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = AUTH_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(AUTH_FILE)
    CREDENTIALS = updated
    with SESSIONS_LOCK:
        SESSIONS.clear()
    return normalized_username


def _prune_login_failures(current: float) -> None:
    expired = [
        client_ip for client_ip, (_, blocked_until, last_failure) in LOGIN_FAILURES.items()
        if blocked_until <= current and current - last_failure >= LOGIN_FAILURE_RETENTION_SECONDS
    ]
    for client_ip in expired:
        LOGIN_FAILURES.pop(client_ip, None)
    overflow = len(LOGIN_FAILURES) - MAX_LOGIN_FAILURE_ENTRIES
    if overflow > 0:
        oldest = sorted(LOGIN_FAILURES, key=lambda value: LOGIN_FAILURES[value][2])[:overflow]
        for client_ip in oldest:
            LOGIN_FAILURES.pop(client_ip, None)


def login_block_remaining(client_ip: str) -> int:
    with LOGIN_FAILURES_LOCK:
        current = time.time()
        _prune_login_failures(current)
        failures, blocked_until, _ = LOGIN_FAILURES.get(client_ip, (0, 0, 0))
        if not failures or not blocked_until:
            return 0
        if blocked_until <= current:
            LOGIN_FAILURES.pop(client_ip, None)
            return 0
        return max(1, int(blocked_until - current))


def record_login_result(client_ip: str, success: bool) -> None:
    with LOGIN_FAILURES_LOCK:
        current = time.time()
        _prune_login_failures(current)
        if success:
            LOGIN_FAILURES.pop(client_ip, None)
            return
        failures, blocked_until, _ = LOGIN_FAILURES.get(client_ip, (0, 0, 0))
        if blocked_until > current:
            return
        failures += 1
        LOGIN_FAILURES[client_ip] = (
            failures,
            current + LOGIN_BLOCK_SECONDS if failures >= LOGIN_FAILURE_LIMIT else 0,
            current,
        )
        _prune_login_failures(current)


def trusted_client_ip(peer_ip: str, forwarded_for: str = "", trust_forwarded: bool | None = None) -> str:
    """Use the rightmost forwarded IP only after explicitly trusting a local reverse proxy."""
    try:
        peer = ipaddress.ip_address(peer_ip)
    except ValueError:
        return peer_ip
    trust = TRUST_FORWARDED_FOR if trust_forwarded is None else trust_forwarded
    if not trust or not peer.is_loopback or not forwarded_for:
        return peer_ip
    candidate = forwarded_for.rsplit(",", 1)[-1].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return peer_ip


def render_launcher_html(token: str, public_port: int) -> str:
    encoded_token = json.dumps(str(token))
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><title>NASDrop</title></head>
<body><script>
  var host = location.hostname;
  var plainHost = host.replace(/^\\[|\\]$/g, "").toLowerCase();
  var isV6 = plainHost.indexOf(":") !== -1;
  var privateHost = plainHost === "localhost" || plainHost === "::1" ||
    (!isV6 && (/^(127\\.|10\\.|192\\.168\\.)/.test(plainHost) ||
    /^172\\.(1[6-9]|2[0-9]|3[01])\\./.test(plainHost) ||
    plainHost.endsWith(".local") || plainHost.indexOf(".") === -1));
  var targetPort = privateHost ? {LISTEN_PORT} : {int(public_port)};
  var targetProtocol = location.protocol === "https:" ? "https://" : "http://";
  var token = {encoded_token};
  location.replace(targetProtocol + host + ":" + targetPort + "/#token=" + encodeURIComponent(token));
</script></body></html>
'''


def write_launcher_file(token: str | None = None, public_port: int | None = None) -> None:
    if LAUNCHER_FILE is None:
        return
    with LAUNCHER_TOKEN_LOCK:
        port = LAUNCHER_PORT if public_port is None else normalize_launcher_port(public_port)
        temporary = LAUNCHER_FILE.with_suffix(".tmp")
        temporary.write_text(render_launcher_html(token or LAUNCHER_TOKEN, port), encoding="utf-8")
        temporary.chmod(0o644)
        temporary.replace(LAUNCHER_FILE)


def rotate_launcher_token() -> str:
    global LAUNCHER_TOKEN
    with LAUNCHER_TOKEN_LOCK:
        previous = LAUNCHER_TOKEN
        try:
            LAUNCHER_TOKEN = load_launcher_token()
            write_launcher_file(LAUNCHER_TOKEN)
        except OSError:
            LAUNCHER_TOKEN = previous
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            temporary = TOKEN_FILE.with_suffix(".tmp")
            temporary.write_text(previous + "\n", encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(TOKEN_FILE)
            raise
        return LAUNCHER_TOKEN


def refresh_launcher_safely() -> None:
    try:
        write_launcher_file()
    except OSError:
        LOGGER.exception("DSM launcher file could not be refreshed")
INSPECTION_CACHE: dict[str, tuple[float, dict]] = {}
INSPECTION_CACHE_LOCK = threading.Lock()
INSPECTION_TTL_SECONDS = 300
GOFILE_SESSION_LOCK = threading.Lock()
GOFILE_SESSION: tuple[float, str, str] | None = None
GOFILE_REQUEST_LOCK = threading.Lock()
GOFILE_LAST_REQUEST = 0.0
GOFILE_COOLDOWN_LOCK = threading.Lock()


class GofileCooldownError(ValueError):
    """Raised without making a request while GoFile is cooling down."""


class PasswordRequiredError(ValueError):
    """Raised when an encrypted archive needs a new password without redownloading."""


def _load_gofile_cooldown() -> tuple[float, str]:
    if not GOFILE_COOLDOWN_FILE.exists():
        return 0.0, ""
    try:
        data = json.loads(GOFILE_COOLDOWN_FILE.read_text(encoding="utf-8"))
        return float(data.get("until", 0)), str(data.get("reason", ""))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return 0.0, ""


GOFILE_COOLDOWN_UNTIL, GOFILE_COOLDOWN_REASON = _load_gofile_cooldown()


def _save_gofile_cooldown(until: float, reason: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp = GOFILE_COOLDOWN_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps({"until": until, "reason": reason}, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, GOFILE_COOLDOWN_FILE)


def _gofile_cooldown_status() -> dict[str, object]:
    with GOFILE_COOLDOWN_LOCK:
        remaining = max(0, int(GOFILE_COOLDOWN_UNTIL - time.time()))
        return {
            "active": remaining > 0,
            "until": GOFILE_COOLDOWN_UNTIL if remaining > 0 else 0,
            "remaining_seconds": remaining,
            "reason": GOFILE_COOLDOWN_REASON if remaining > 0 else "",
        }


def _gofile_guard() -> None:
    status = _gofile_cooldown_status()
    if not status["active"]:
        return
    until = datetime.fromtimestamp(float(status["until"])).astimezone().strftime("%H:%M")
    raise GofileCooldownError(f"GoFile 요청이 일시 중단되었습니다. {until} 이후 다시 시도해 주세요.")


def _gofile_retry_after(exc: HTTPError, fallback: float) -> float:
    try:
        value = exc.headers.get("Retry-After", "")
    except AttributeError:
        value = ""
    try:
        return max(fallback, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(str(value))
            return max(fallback, retry_at.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return fallback


def _trip_gofile_cooldown(seconds: float, reason: str) -> GofileCooldownError:
    global GOFILE_COOLDOWN_UNTIL, GOFILE_COOLDOWN_REASON
    duration = min(GOFILE_MAX_COOLDOWN_SECONDS, max(60.0, seconds))
    with GOFILE_COOLDOWN_LOCK:
        GOFILE_COOLDOWN_UNTIL = max(GOFILE_COOLDOWN_UNTIL, time.time() + duration)
        GOFILE_COOLDOWN_REASON = reason
        _save_gofile_cooldown(GOFILE_COOLDOWN_UNTIL, reason)
    until = datetime.fromtimestamp(GOFILE_COOLDOWN_UNTIL).astimezone().strftime("%H:%M")
    return GofileCooldownError(f"{reason} GoFile 요청을 {until}까지 자동 중단합니다.")


def _validate_job_password(value: object) -> str:
    password = str(value or "")
    if len(password) > 256 or any(character in password for character in {"\x00", "\r", "\n"}):
        raise ValueError("압축 암호는 줄바꿈 없이 256자 이내로 입력해 주세요.")
    return password


def _job_secret_path(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        raise ValueError("작업 ID가 올바르지 않습니다.")
    return SECRET_DIR / f"{job_id}.json"


def _load_job_secrets(job_id: str) -> dict[str, str]:
    path = _job_secret_path(job_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if isinstance(value, str)}


def _write_job_secrets(job_id: str, data: dict[str, str]) -> None:
    path = _job_secret_path(job_id)
    cleaned = {str(key): str(value) for key, value in data.items() if str(value)}
    if not cleaned:
        path.unlink(missing_ok=True)
        return
    SECRET_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(cleaned, ensure_ascii=False), encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(path)


def save_job_password(job_id: str, password: object) -> None:
    normalized = _validate_job_password(password)
    with JOB_SECRET_LOCK:
        data = _load_job_secrets(job_id)
        if normalized:
            data["password"] = normalized
        else:
            data.pop("password", None)
        _write_job_secrets(job_id, data)


def load_job_password(job_id: str) -> str:
    with JOB_SECRET_LOCK:
        try:
            return _validate_job_password(_load_job_secrets(job_id).get("password", ""))
        except ValueError:
            return ""


def delete_job_password(job_id: str) -> None:
    save_job_password(job_id, "")


def save_job_download_url(job_id: str, download_url: str) -> None:
    normalized = str(download_url).strip()
    with JOB_SECRET_LOCK:
        data = _load_job_secrets(job_id)
        if normalized:
            data["download_url"] = normalized
        else:
            data.pop("download_url", None)
        _write_job_secrets(job_id, data)


def load_job_download_url(job_id: str) -> str:
    with JOB_SECRET_LOCK:
        return _load_job_secrets(job_id).get("download_url", "")


def delete_job_secrets(job_id: str) -> None:
    with JOB_SECRET_LOCK:
        _job_secret_path(job_id).unlink(missing_ok=True)


@dataclass
class Job:
    id: str
    name: str
    source: str
    size: int
    downloaded: int
    status: str
    created_at: str
    target: str = ""
    error: str = ""
    sha256: str = ""
    not_before: float = 0
    output: str = ""
    extracted: bool = False
    extract: bool = True


ARCHIVE_SUFFIXES = (
    (".tar.gz", "tar"), (".tar.bz2", "tar"), (".tar.xz", "tar"),
    (".tgz", "tar"), (".tbz2", "tar"), (".txz", "tar"),
    (".zip", "zip"), (".tar", "tar"), (".7z", "7zip"), (".rar", "7zip"),
)


def archive_kind(name: str) -> str:
    lowered = name.lower()
    return next((kind for suffix, kind in ARCHIVE_SUFFIXES if lowered.endswith(suffix)), "")


def archive_output_name(name: str) -> str:
    lowered = name.lower()
    for suffix, _ in ARCHIVE_SUFFIXES:
        if lowered.endswith(suffix):
            return name[:-len(suffix)] or "extracted"
    return Path(name).stem or "extracted"


def _archive_relative_path(raw_name: str) -> PurePosixPath | None:
    normalized = raw_name.replace("\\", "/")
    path = PurePosixPath(normalized)
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts:
        return None
    if path.is_absolute():
        raise ValueError("압축 파일에 절대 경로가 포함되어 있습니다.")
    if any(part == ".." or "\x00" in part for part in parts):
        raise ValueError("압축 파일에 저장 폴더를 벗어나는 경로가 포함되어 있습니다.")
    return PurePosixPath(*parts)


def _checked_archive_totals(entries: int, total_size: int) -> None:
    if entries > MAX_ARCHIVE_ENTRIES:
        raise ValueError(f"압축 항목이 너무 많습니다(최대 {MAX_ARCHIVE_ENTRIES:,}개).")
    if total_size > MAX_EXTRACTED_BYTES:
        raise ValueError("압축을 풀었을 때의 전체 크기가 안전 한도를 초과합니다.")


def _password_failure(message: str) -> bool:
    lowered = message.lower()
    return any(fragment in lowered for fragment in (
        "wrong password", "password is incorrect", "password required", "enter password",
        "can not open encrypted archive", "data error in encrypted file",
    ))


def _seven_zip_records(output: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in output.splitlines() + [""]:
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        if " = " in line:
            key, value = line.split(" = ", 1)
            current[key.strip()] = value.strip()
    return records


def _curl_config_value(value: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("다운로드 요청 정보에 제어 문자를 사용할 수 없습니다.")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_seven_zip(arguments: list[str], password: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    if not SEVEN_ZIP.is_file():
        raise ValueError("패키지의 7-Zip 압축 해제 엔진을 찾을 수 없습니다.")
    environment = dict(os.environ)
    environment.update({"LANG": "C", "LC_ALL": "C"})
    command = [str(SEVEN_ZIP), *arguments]
    run_options: dict[str, object] = {
        "capture_output": True, "text": True, "errors": "replace", "env": environment, "timeout": timeout,
    }
    if password:
        command.append("-p")
        run_options["input"] = password + "\n"
    else:
        run_options["stdin"] = subprocess.DEVNULL
    result = subprocess.run(command, **run_options)
    message = "\n".join((result.stdout, result.stderr)).strip()
    if password:
        message = message.replace(password, "***")
    if result.returncode != 0:
        if _password_failure(message) or not password and "encrypted" in message.lower():
            raise PasswordRequiredError("압축 암호가 필요하거나 입력한 암호가 올바르지 않습니다.")
        raise ValueError((message or "7-Zip 압축 해제 엔진이 작업을 완료하지 못했습니다.")[-400:])
    return result


def _validate_seven_zip_listing(archive: Path, password: str) -> None:
    result = _run_seven_zip(["l", "-slt", "-ba", "-sccUTF-8", str(archive)], password, timeout=120)
    records = _seven_zip_records(result.stdout)
    total_size = 0
    entries = 0
    for record in records:
        raw_path = record.get("Path", "")
        if not raw_path:
            continue
        _archive_relative_path(raw_path)
        if record.get("Symbolic Link") or record.get("Hard Link"):
            raise ValueError("압축 파일의 링크는 안전을 위해 해제하지 않습니다.")
        attributes = record.get("Attributes", "")
        if "L" in attributes[:5]:
            raise ValueError("압축 파일의 심볼릭 링크는 안전을 위해 해제하지 않습니다.")
        try:
            total_size += max(0, int(record.get("Size", "0") or "0"))
        except ValueError as exc:
            raise ValueError("압축 항목의 크기 정보가 올바르지 않습니다.") from exc
        entries += 1
    _checked_archive_totals(entries, total_size)


def _validate_extracted_tree(destination: Path) -> None:
    entries = 0
    total_size = 0
    for root, directories, files in os.walk(destination, followlinks=False):
        root_path = Path(root)
        for name in [*directories, *files]:
            path = root_path / name
            entries += 1
            if path.is_symlink():
                raise ValueError("압축 파일의 링크는 안전을 위해 해제하지 않습니다.")
            resolved = path.resolve()
            resolved.relative_to(destination.resolve())
            if path.is_file():
                total_size += path.stat().st_size
        _checked_archive_totals(entries, total_size)


_ZIP_LEGACY_ENCODINGS = ("utf-8", "cp949", "shift_jis", "gb18030")


def _zip_name_score(value: str, encoding: str) -> int:
    score = 3 if encoding == "utf-8" else 0
    hangul = 0
    kana = 0
    cjk = 0
    for character in value:
        codepoint = ord(character)
        category = unicodedata.category(character)
        if character in "/\\._- ()[]{}" or character.isascii() and character.isalnum():
            score += 1
        elif 0xAC00 <= codepoint <= 0xD7A3 or 0x1100 <= codepoint <= 0x11FF:
            hangul += 1
            score += 3
        elif 0x3040 <= codepoint <= 0x30FF:
            kana += 1
            score += 3
        elif 0x3400 <= codepoint <= 0x9FFF:
            cjk += 1
            score += 2
        elif 0x2500 <= codepoint <= 0x259F:
            score -= 8
        elif category.startswith(("L", "N", "P", "Z")):
            score += 1
        elif category.startswith("C"):
            score -= 8
    if encoding == "cp949":
        score += hangul * 4
    elif encoding == "shift_jis":
        score += kana * 4
    elif encoding == "gb18030":
        score += cjk * 2
    return score


def _zip_legacy_encoding(infos: list[zipfile.ZipInfo]) -> str | None:
    raw_names: list[bytes] = []
    current_score = 0
    for info in infos:
        if info.flag_bits & 0x800:
            continue
        try:
            raw = info.filename.encode("cp437")
        except UnicodeEncodeError:
            continue
        if not any(byte >= 0x80 for byte in raw):
            continue
        raw_names.append(raw)
        current_score += _zip_name_score(info.filename, "cp437")
    if not raw_names:
        return None

    best_encoding: str | None = None
    best_score = current_score
    for encoding in _ZIP_LEGACY_ENCODINGS:
        try:
            decoded = [raw.decode(encoding, errors="strict") for raw in raw_names]
        except (UnicodeDecodeError, LookupError):
            continue
        candidate_score = sum(_zip_name_score(name, encoding) for name in decoded)
        if candidate_score > best_score + 3:
            best_encoding = encoding
            best_score = candidate_score
    return best_encoding


def _zip_entry_name(info: zipfile.ZipInfo, legacy_encoding: str | None) -> str:
    if not legacy_encoding or info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode(legacy_encoding, errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
        return info.filename


def _extract_with_seven_zip(archive: Path, destination: Path, password: str) -> None:
    _validate_seven_zip_listing(archive, password)
    _run_seven_zip(
        ["x", "-y", "-bd", "-bb0", "-sccUTF-8", f"-o{destination}", str(archive)],
        password,
        timeout=ARCHIVE_EXTRACT_TIMEOUT_SECONDS,
    )
    _validate_extracted_tree(destination)


def extract_archive_safely(archive: Path, destination: Path, password: str = "") -> None:
    kind = archive_kind(archive.name)
    password = _validate_job_password(password)
    if kind == "7zip" or password:
        _extract_with_seven_zip(archive, destination, password)
        return
    if kind == "zip":
        try:
            with zipfile.ZipFile(archive) as source:
                infos = source.infolist()
                legacy_encoding = _zip_legacy_encoding(infos)
                _checked_archive_totals(len(infos), sum(max(0, info.file_size) for info in infos))
                for info in infos:
                    relative = _archive_relative_path(_zip_entry_name(info, legacy_encoding))
                    if relative is None:
                        continue
                    mode = (info.external_attr >> 16) & 0xFFFF
                    if stat.S_ISLNK(mode):
                        raise ValueError("압축 파일의 심볼릭 링크는 안전을 위해 해제하지 않습니다.")
                    output = destination.joinpath(*relative.parts)
                    if info.is_dir():
                        output.mkdir(parents=True, exist_ok=True)
                        continue
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(info) as reader, output.open("xb") as writer:
                        shutil.copyfileobj(reader, writer, length=1024 * 1024)
        except (NotImplementedError, RuntimeError) as exc:
            shutil.rmtree(destination, ignore_errors=True)
            destination.mkdir(mode=0o700)
            if "password" in str(exc).lower():
                raise PasswordRequiredError("압축 암호가 필요합니다.") from exc
            _extract_with_seven_zip(archive, destination, password)
        return
    if kind == "tar":
        with tarfile.open(archive, mode="r:*") as source:
            members = source.getmembers()
            _checked_archive_totals(len(members), sum(max(0, member.size) for member in members if member.isfile()))
            for member in members:
                relative = _archive_relative_path(member.name)
                if relative is None:
                    continue
                if not (member.isdir() or member.isfile()):
                    raise ValueError("압축 파일의 링크 또는 특수 파일은 안전을 위해 해제하지 않습니다.")
                output = destination.joinpath(*relative.parts)
                if member.isdir():
                    output.mkdir(parents=True, exist_ok=True)
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                reader = source.extractfile(member)
                if reader is None:
                    raise ValueError("압축 항목을 읽을 수 없습니다.")
                with reader, output.open("xb") as writer:
                    shutil.copyfileobj(reader, writer, length=1024 * 1024)
        return
    raise ValueError("자동 압축 해제를 지원하지 않는 형식입니다.")


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    for number in range(1, 10_000):
        candidate = path.with_name(f"{path.name} ({number})") if path.is_dir() or not path.suffix else path.with_name(f"{path.stem} ({number}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError("같은 이름의 결과가 너무 많아 저장할 수 없습니다.")


def job_workspace(target_dir: str, job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        raise ValueError("작업 ID가 올바르지 않습니다.")
    target = Path(target_dir).resolve()
    workspace = (target / ".nasdrop-tmp" / job_id).resolve()
    workspace.relative_to(target)
    return workspace


def migrate_legacy_workspace(target_dir: str, name: str, job_id: str, workspace: Path) -> int:
    target = Path(target_dir).resolve()
    prefix = f".{name}.{job_id}."
    moved = 0
    for source in target.iterdir():
        if not source.is_file() or not source.name.startswith(prefix):
            continue
        remainder = source.name[len(prefix):]
        if remainder != "assembling" and not remainder.startswith("segment."):
            continue
        destination = workspace / source.name
        if destination.exists():
            if source.stat().st_size > destination.stat().st_size:
                destination.unlink()
                source.rename(destination)
            else:
                source.unlink()
        else:
            source.rename(destination)
        moved += 1
    return moved


def promote_download(artifact: Path, target_dir: str, auto_extract: bool, password: str = "") -> tuple[Path, bool]:
    target = Path(target_dir).resolve()
    if not artifact.is_file():
        raise ValueError("완성된 임시 파일을 찾을 수 없습니다.")
    kind = archive_kind(artifact.name) if auto_extract else ""
    if kind:
        extracted = artifact.parent / "extracted"
        if extracted.exists():
            shutil.rmtree(extracted)
        extracted.mkdir(mode=0o700)
        extract_archive_safely(artifact, extracted, password)
        base_name = archive_output_name(artifact.name)
        output = unique_destination(target / base_name)
        children = list(extracted.iterdir())
        if len(children) == 1 and children[0].is_dir() and children[0].name.casefold() == base_name.casefold():
            children[0].rename(output)
            extracted.rmdir()
        else:
            extracted.rename(output)
        return output, True
    output = unique_destination(target / artifact.name)
    artifact.rename(output)
    return output, False


class Controller:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.jobs: dict[str, Job] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.private_downloads: dict[str, dict[str, str]] = {}
        self.running_providers: dict[str, set[str]] = {}
        self.postprocess_waiting: list[str] = []
        self.processing_job: str | None = None
        self.load()
        threading.Thread(target=self._dispatcher, name="nasdrop-dispatcher", daemon=True).start()

    def load(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            for item in data:
                if item.get("status") in {"downloading", "waiting_processing", "verifying", "extracting", "publishing", "ready"}:
                    item["status"] = "paused"
                    item["error"] = "서비스가 재시작되어 작업을 일시정지했습니다. 다시 시작할 수 있습니다."
                job = Job(**item)
                self.jobs[job.id] = job
        except Exception:
            self.jobs = {}

    def save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        temp = STATE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps([asdict(x) for x in self.jobs.values()], ensure_ascii=False, indent=2), encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(STATE_FILE)

    def public_jobs(self) -> list[dict]:
        with self.lock:
            jobs = []
            for job in reversed(list(self.jobs.values())):
                item = asdict(job)
                item["error_code"] = public_error_code(job.error) if job.error else ""
                jobs.append(item)
            return jobs

    def active(self) -> bool:
        return any(job.status in {"ready", "downloading", "waiting_processing", "verifying", "extracting", "publishing"} for job in self.jobs.values())

    def start(self, file: dict, target: str = "", extract: bool | None = None, password: str = "") -> Job:
        return self.start_many([file], target, extract, password)[0]

    def start_many(self, files: list[dict], target: str = "", extract: bool | None = None, password: str = "") -> list[Job]:
        if not files:
            raise ValueError("다운로드할 파일이 없습니다.")
        if extract is not None and not isinstance(extract, bool):
            raise ValueError("압축 해제 선택값이 올바르지 않습니다.")
        should_extract = AUTO_EXTRACT_ARCHIVES if extract is None else extract
        normalized_password = _validate_job_password(password)
        base_destination = normalize_target(target or NAS_TARGET)
        destinations = [prepare_batch_target(base_destination, str(file.get("relative_path", ""))) for file in files]
        jobs = []
        provider_positions: dict[str, int] = {}
        queued_at = time.time()
        with self.condition:
            for file, destination in zip(files, destinations):
                provider = str(file.get("provider", "gigafile"))
                position = provider_positions.get(provider, 0)
                provider_positions[provider] = position + 1
                job = Job(
                    id=secrets.token_hex(6), name=file["name"], source=file["url"],
                    size=int(file["size"]), downloaded=0, status="queued", created_at=now(), target=destination,
                    not_before=queued_at + position * BATCH_QUEUE_STAGGER_SECONDS if len(files) > 1 else 0,
                    extract=should_extract,
                )
                self.jobs[job.id] = job
                self.private_downloads[job.id] = {
                    "provider": provider,
                    "download_url": str(file.get("download_url", "")),
                    "download_token": str(file.get("download_token", "")),
                    "download_mode": str(file.get("download_mode", "")),
                    "expected_sha256": str(file.get("expected_sha256", "")),
                    "target": destination,
                }
                if provider == "buzzheavier":
                    save_job_download_url(job.id, str(file.get("download_url", "")))
                if should_extract and normalized_password:
                    save_job_password(job.id, normalized_password)
                jobs.append(job)
            self.save()
            self.condition.notify_all()
        return jobs

    def _provider_for_job(self, job: Job) -> str:
        private = self.private_downloads.get(job.id, {})
        return private.get("provider") or provider_for_url(job.source)

    def _provider_limit(self) -> int:
        return SAME_PROVIDER_LIMIT if ALLOW_SAME_PROVIDER_PARALLEL else 1

    def _can_start(self, job: Job) -> bool:
        if DISK_PROTECTION and (self.postprocess_waiting or self.processing_job):
            return False
        provider = self._provider_for_job(job)
        running_total = sum(len(job_ids) for job_ids in self.running_providers.values())
        return running_total < MAX_PARALLEL_DOWNLOADS and len(self.running_providers.get(provider, set())) < self._provider_limit()

    def settings_changed(self) -> None:
        with self.condition:
            self.condition.notify_all()

    def _dispatcher(self) -> None:
        while True:
            with self.condition:
                current = time.time()
                queued = next(
                    (
                        job for job in self.jobs.values()
                        if job.status == "queued" and job.not_before <= current and self._can_start(job)
                    ),
                    None,
                )
                if queued is None:
                    delays = [
                        job.not_before - current for job in self.jobs.values()
                        if job.status == "queued" and job.not_before > current
                    ]
                    self.condition.wait(timeout=max(0.1, min(delays)) if delays else None)
                    continue
                provider = self._provider_for_job(queued)
                queued.status = "ready"
                queued.error = ""
                self.running_providers.setdefault(provider, set()).add(queued.id)
                self.save()
                job_id = queued.id
            threading.Thread(
                target=self._run_guarded,
                args=(job_id, provider),
                name=f"nasdrop-{provider}-{job_id}",
                daemon=True,
            ).start()

    def _run_guarded(self, job_id: str, provider: str) -> None:
        try:
            self._run(job_id)
        except Exception as exc:
            with self.lock:
                job = self.jobs.get(job_id)
                if job and job.status not in {"paused", "cancelled"}:
                    job.status = "failed"
                    job.error = (str(exc) or "다운로드 준비 중 오류가 발생했습니다.")[-400:]
                self.processes.pop(job_id, None)
                self.private_downloads.pop(job_id, None)
                self.save()
        finally:
            with self.condition:
                running = self.running_providers.get(provider)
                if running:
                    running.discard(job_id)
                    if not running:
                        self.running_providers.pop(provider, None)
                self.condition.notify_all()

    def _local_size(self, prefix: str) -> int:
        prefix_path = Path(prefix)
        total = 0
        try:
            for entry in prefix_path.parent.iterdir():
                if not entry.name.startswith(prefix_path.name):
                    continue
                if entry.is_file():
                    total += entry.stat().st_size
        except OSError:
            return total
        return total

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _assemble_artifact(self, job: Job, workspace: Path, private: dict[str, str]) -> tuple[Path, str]:
        artifact = workspace / job.name
        if artifact.is_file() and job.sha256:
            return artifact, job.sha256
        segment_count = 1 if private.get("download_mode") == "gigafile_zip" or private.get("transfer_mode") == "single" else 8
        parts = [workspace / f".{job.name}.{job.id}.segment.{index}" for index in range(segment_count)]
        if any(not part.is_file() for part in parts):
            raise ValueError("다운로드 조각이 모두 준비되지 않았습니다.")
        assembling = workspace / f".{job.name}.{job.id}.assembling"
        if segment_count == 1:
            parts[0].replace(assembling)
        else:
            with assembling.open("wb") as output:
                for part in parts:
                    with part.open("rb") as source:
                        shutil.copyfileobj(source, output, length=4 * 1024 * 1024)
        actual_size = assembling.stat().st_size
        size_valid = actual_size >= job.size if segment_count == 1 else actual_size == job.size
        if not size_valid:
            assembling.unlink(missing_ok=True)
            raise ValueError("결합된 파일 크기가 예상값과 일치하지 않습니다.")
        digest = self._file_sha256(assembling)
        expected_sha256 = private.get("expected_sha256", "").lower()
        if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) and digest != expected_sha256:
            assembling.unlink(missing_ok=True)
            for part in parts:
                part.unlink(missing_ok=True)
            raise ValueError("무결성 검사에 실패하여 손상된 다운로드 조각을 삭제했습니다.")
        assembling.replace(artifact)
        for part in parts:
            part.unlink(missing_ok=True)
            part.with_name(part.name + ".more").unlink(missing_ok=True)
        return artifact, digest

    def _apply_response_filename(self, job: Job, workspace: Path, artifact: Path, private: dict[str, str]) -> Path:
        headers_path = workspace / ".response-headers"
        try:
            if private.get("provider") not in {"gigafile", "buzzheavier"}:
                return artifact
            actual_name = response_download_name(headers_path)
            if not actual_name or actual_name == job.name:
                return artifact
            destination = workspace / actual_name
            if destination.exists() and destination != artifact:
                destination = unique_destination(destination)
            artifact.replace(destination)
            with self.lock:
                job.name = destination.name
                self.save()
            return destination
        finally:
            headers_path.unlink(missing_ok=True)

    def _enter_postprocessing(self, job_id: str) -> bool:
        with self.condition:
            self.processes.pop(job_id, None)
            if job_id not in self.postprocess_waiting:
                self.postprocess_waiting.append(job_id)
            job = self.jobs[job_id]
            job.status = "waiting_processing"
            job.error = ""
            self.save()
            self.condition.notify_all()
            while True:
                if job.status in {"paused", "cancelled"}:
                    if job_id in self.postprocess_waiting:
                        self.postprocess_waiting.remove(job_id)
                    self.condition.notify_all()
                    return False
                first = bool(self.postprocess_waiting) and self.postprocess_waiting[0] == job_id
                downloads_running = any(process.poll() is None for process in self.processes.values())
                disk_ready = not DISK_PROTECTION or not downloads_running
                if first and self.processing_job is None and disk_ready:
                    self.postprocess_waiting.pop(0)
                    self.processing_job = job_id
                    self.condition.notify_all()
                    return True
                self.condition.wait(timeout=1)

    def _leave_postprocessing(self, job_id: str) -> None:
        with self.condition:
            if self.processing_job == job_id:
                self.processing_job = None
            if job_id in self.postprocess_waiting:
                self.postprocess_waiting.remove(job_id)
            self.condition.notify_all()

    def _postprocess(self, job_id: str, workspace: Path, artifact: Path, target_dir: str, verify_artifact: bool = False) -> None:
        if not self._enter_postprocessing(job_id):
            return
        try:
            with self.lock:
                job = self.jobs[job_id]
                private = self.private_downloads.get(job_id, {})
                job.status = "verifying"
                self.save()
            if not artifact.is_file():
                artifact, digest = self._assemble_artifact(job, workspace, private)
                with self.lock:
                    job.sha256 = digest
                    self.save()
            elif verify_artifact and job.sha256 and self._file_sha256(artifact) != job.sha256:
                with self.lock:
                    artifact.unlink(missing_ok=True)
                    shutil.rmtree(workspace / "extracted", ignore_errors=True)
                    job.sha256 = ""
                    raise ValueError("임시 완성 파일이 손상되어 삭제했습니다. 작업을 재개하면 처음부터 다시 다운로드합니다.")
            artifact = self._apply_response_filename(job, workspace, artifact, private)
            with self.lock:
                job.status = "extracting" if job.extract and archive_kind(job.name) else "publishing"
                self.save()
            try:
                output, extracted = promote_download(
                    artifact, target_dir, job.extract, load_job_password(job_id),
                )
            except PasswordRequiredError as exc:
                delete_job_password(job_id)
                with self.lock:
                    job = self.jobs[job_id]
                    job.status = "password_required"
                    job.error = str(exc)
                    self.private_downloads.pop(job_id, None)
                    self.save()
                return
            shutil.rmtree(workspace, ignore_errors=True)
            try:
                workspace.parent.rmdir()
            except OSError:
                pass
            delete_job_secrets(job_id)
            with self.lock:
                job = self.jobs[job_id]
                job.status = "completed"
                job.output = str(output)
                job.extracted = extracted
                job.error = ""
                self.private_downloads.pop(job_id, None)
                self.save()
        finally:
            self._leave_postprocessing(job_id)

    def _run(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            if job.status in {"paused", "cancelled"}:
                return
            job.status = "downloading"
            self.save()
        private = self.private_downloads.get(job_id, {})
        target_dir = private.get("target") or job.target or NAS_TARGET
        safe_name = job.name
        workspace = job_workspace(target_dir, job.id)
        workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
        migrate_legacy_workspace(target_dir, safe_name, job.id, workspace)
        artifact = workspace / safe_name
        if artifact.is_file() and job.sha256:
            self._postprocess(job_id, workspace, artifact, target_dir, verify_artifact=True)
            return
        parsed = urlparse(job.source)
        provider = private.get("provider") or provider_for_url(job.source)
        if provider == "gigafile" and not private.get("download_url"):
            refreshed = inspect_gigafile(job.source)
            if refreshed["name"] != job.name or int(refreshed["size"]) != job.size:
                raise ValueError("대기 중 파일 정보가 변경되었습니다. 링크를 다시 등록해 주세요.")
            private = {
                "provider": "gigafile",
                "download_url": str(refreshed.get("download_url", "")),
                "download_mode": str(refreshed.get("download_mode", "gigafile_file")),
                "target": target_dir,
            }
            self.private_downloads[job_id] = private
        elif provider == "gofile" and not (private.get("download_url") and private.get("download_token")):
            refreshed = inspect_gofile(job.source)
            if refreshed["name"] != job.name or int(refreshed["size"]) != job.size:
                raise ValueError("대기 중 파일 정보가 변경되었습니다. 링크를 다시 등록해 주세요.")
            private = {
                "provider": "gofile",
                "download_url": str(refreshed["download_url"]),
                "download_token": str(refreshed["download_token"]),
                "target": target_dir,
            }
            self.private_downloads[job_id] = private
        elif provider == "pixeldrain" and not private.get("download_url"):
            refreshed = inspect_pixeldrain(job.source)
            if refreshed["name"] != job.name or int(refreshed["size"]) != job.size:
                raise ValueError("대기 중 파일 정보가 변경되었습니다. 링크를 다시 등록해 주세요.")
            private = {
                "provider": "pixeldrain",
                "download_url": str(refreshed["download_url"]),
                "expected_sha256": str(refreshed.get("expected_sha256", "")),
                "target": target_dir,
            }
            self.private_downloads[job_id] = private
        elif provider == "buzzheavier" and not private.get("download_url"):
            saved_url = load_job_download_url(job.id)
            if not saved_url:
                raise ValueError("Buzzheavier 직접 링크 정보가 없습니다. Copy download link를 다시 등록해 주세요.")
            direct_url, _file_id, _host = _validate_buzzheavier_download_url(saved_url)
            private = {
                "provider": "buzzheavier",
                "download_url": direct_url,
                "target": target_dir,
            }
            self.private_downloads[job_id] = private
        download_mode = DOWNLOAD_MODE
        private["transfer_mode"] = download_mode
        self.private_downloads[job_id] = private
        workspace_dir = str(workspace)
        prefix = f"{workspace_dir}/.{safe_name}.{job.id}.segment."
        if provider == "gigafile" and private.get("download_mode") == "gigafile_zip":
            script = self._download_script_gigafile_zip(
                private.get("download_url", ""), job.source, safe_name, job.id, job.size, workspace_dir,
            )
        elif provider == "gofile":
            script = self._download_script_gofile(
                private.get("download_url", ""), private.get("download_token", ""),
                job.source, safe_name, job.id, job.size, workspace_dir, mode=download_mode,
            )
        elif provider == "pixeldrain":
            script = self._download_script_direct(
                private.get("download_url", ""), job.source, safe_name, job.id, job.size, workspace_dir,
                expected_sha256=private.get("expected_sha256", ""), mode=download_mode,
            )
        elif provider == "buzzheavier":
            script = self._download_script_direct(
                private.get("download_url", ""), job.source, safe_name, job.id, job.size, workspace_dir,
                mode=download_mode, capture_headers=True,
            )
        else:
            file_id = parsed.path.strip("/")
            host = parsed.hostname or ""
            script = self._download_script(host, file_id, safe_name, job.id, job.size, workspace_dir, mode=download_mode)
        command = ["sh", "-s"]
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        with self.condition:
            self.processes[job_id] = process
            self.condition.notify_all()
        assert process.stdin is not None
        process.stdin.write(script)
        process.stdin.close()

        while process.poll() is None:
            time.sleep(2.5)
            try:
                current = self._local_size(prefix)
            except Exception:
                current = 0
            with self.lock:
                if self.jobs[job_id].status in {"paused", "cancelled"}:
                    self._terminate(process)
                    break
                self.jobs[job_id].downloaded = min(job.size, current)
                if download_mode == "segmented" and current >= job.size:
                    self.jobs[job_id].status = "verifying"
                self.save()

        stdout = process.stdout.read() if process.stdout else ""
        stderr = process.stderr.read() if process.stderr else ""
        with self.lock:
            current_job = self.jobs[job_id]
            if current_job.status in {"paused", "cancelled"}:
                self.processes.pop(job_id, None)
                self.private_downloads.pop(job_id, None)
                self.save()
                return
            if process.returncode != 0:
                current_job.status = "failed"
                if provider == "buzzheavier" and re.search(r"(?:error:\s*)?(?:401|403|404)\b", stderr, re.I):
                    current_job.error = "Buzzheavier 직접 링크가 만료됐거나 사용할 수 없습니다. Copy download link를 다시 받아 새 작업으로 등록해 주세요."
                else:
                    current_job.error = (stderr.strip() or "NAS 다운로드가 중단됐습니다.")[-400:]
                self.processes.pop(job_id, None)
                self.private_downloads.pop(job_id, None)
                self.save()
                return
            match = re.search(r"SHA256=([0-9a-f]{64})", stdout)
            current_job.downloaded = current_job.size
            current_job.status = "waiting_processing"
            current_job.sha256 = match.group(1) if match else ""
            self.save()

        self._postprocess(job_id, workspace, artifact, target_dir)

    def _download_script(self, host: str, file_id: str, name: str, job_id: str, total: int, target_dir: str, mode: str = "segmented") -> str:
        page = f"https://{host}/{file_id}"
        download = f"https://{host}/download.php?file={file_id}"
        prefix = f"{target_dir}/.{name}.{job_id}.segment"
        cookie = f"/tmp/nas_download_{job_id}.cookies"
        response_headers = f"{target_dir}/.response-headers"
        if mode == "single":
            part = f"{prefix}.0"
            return f"""#!/bin/sh
set -eu
TOTAL={total}
PART={shlex.quote(part)}
COOKIE={shlex.quote(cookie)}
PAGE_COPY=/tmp/nas_download_{job_id}.page
cleanup() {{ rm -f "$COOKIE" "$PAGE_COPY"; }}
trap cleanup EXIT HUP INT TERM
curl {CURL_HTTPS_ONLY} -L --fail --silent --show-error -c "$COOKIE" {shlex.quote(page)} -o "$PAGE_COPY"
(curl {CURL_HTTPS_ONLY} -L --fail --silent --show-error -I -b "$COOKIE" -e {shlex.quote(page)} {shlex.quote(download)} -o {shlex.quote(response_headers)} || rm -f {shlex.quote(response_headers)})
existing=0; [ -f "$PART" ] && existing=$(wc -c < "$PART" | tr -d ' ')
[ "$existing" -le "$TOTAL" ] || {{ rm -f "$PART"; existing=0; }}
if [ "$existing" -lt "$TOTAL" ]; then
  if [ "$existing" -gt 0 ]; then
    curl {CURL_HTTPS_ONLY} -L --fail --silent --show-error --retry 8 --retry-delay 5 -b "$COOKIE" -e {shlex.quote(page)} -C - -o "$PART" {shlex.quote(download)}
  else
    curl {CURL_HTTPS_ONLY} -L --fail --silent --show-error --retry 8 --retry-delay 5 -b "$COOKIE" -e {shlex.quote(page)} -o "$PART" {shlex.quote(download)}
  fi
fi
actual=$(wc -c < "$PART" | tr -d ' '); [ "$actual" -eq "$TOTAL" ]
trap - EXIT HUP INT TERM
cleanup
printf 'SEGMENTS_READY=1\n'
"""
        return f"""#!/bin/sh
set -eu
TOTAL={total}
COUNT=8
CHUNK=$(( (TOTAL + COUNT - 1) / COUNT ))
curl {CURL_HTTPS_ONLY} -L --fail --silent --show-error -c {shlex.quote(cookie)} {shlex.quote(page)} -o /tmp/nas_download_{job_id}.page
(curl {CURL_HTTPS_ONLY} -L --fail --silent --show-error -I -b {shlex.quote(cookie)} -e {shlex.quote(page)} {shlex.quote(download)} -o {shlex.quote(response_headers)} || rm -f {shlex.quote(response_headers)})
i=0
while [ "$i" -lt "$COUNT" ]; do
  start=$(( i * CHUNK )); end=$(( start + CHUNK - 1 )); [ "$end" -ge "$TOTAL" ] && end=$(( TOTAL - 1 ))
  part={shlex.quote(prefix)}.$i
  (expected=$(( end - start + 1 )); existing=0; [ -f "$part" ] && existing=$(wc -c < "$part" | tr -d ' '); [ "$existing" -le "$expected" ] || rm -f "$part"; [ -f "$part" ] && existing=$(wc -c < "$part" | tr -d ' ') || existing=0; if [ "$existing" -lt "$expected" ]; then from=$(( start + existing )); more="$part.more"; curl {CURL_HTTPS_ONLY} -L --fail --silent --show-error --retry 8 --retry-delay 5 -b {shlex.quote(cookie)} -e {shlex.quote(page)} -r "$from-$end" -o "$more" {shlex.quote(download)}; cat "$more" >> "$part"; rm -f "$more"; fi; actual=$(wc -c < "$part" | tr -d ' '); [ "$actual" -eq "$expected" ]) &
  i=$(( i + 1 ))
done
wait
printf 'SEGMENTS_READY=%s\\n' "$COUNT"
"""

    def _download_script_gofile(self, download: str, token: str, page: str, name: str, job_id: str, total: int, target_dir: str, mode: str = "segmented") -> str:
        if not download.startswith("https://") or not token:
            raise ValueError("Gofile 다운로드 인증 정보가 없습니다.")
        return self._download_script_direct(download, page, name, job_id, total, target_dir, cookie=f"accountToken={token}", mode=mode)

    def _download_script_gigafile_zip(self, download: str, page: str, name: str, job_id: str, total: int, target_dir: str, verify: bool = True) -> str:
        parsed_download = urlparse(download)
        parsed_page = urlparse(page)
        if (
            parsed_download.scheme != "https"
            or parsed_download.hostname != parsed_page.hostname
            or not GIGAFILE_HOST.fullmatch(parsed_download.hostname or "")
            or parsed_download.path != "/dl_zip.php"
        ):
            raise ValueError("GigaFile 묶음 다운로드 주소가 올바르지 않습니다.")
        part = f"{target_dir}/.{name}.{job_id}.segment.0"
        cookie = f"/tmp/nas_download_{job_id}.cookies"
        page_copy = f"/tmp/nas_download_{job_id}.page"
        return f"""#!/bin/sh
set -eu
TOTAL={total}
COOKIE={shlex.quote(cookie)}
PAGE_COPY={shlex.quote(page_copy)}
PART={shlex.quote(part)}
cleanup() {{ rm -f "$COOKIE" "$PAGE_COPY"; }}
trap cleanup EXIT HUP INT TERM
curl {CURL_HTTPS_ONLY} -L --fail --silent --show-error -c "$COOKIE" {shlex.quote(page)} -o "$PAGE_COPY"
actual=0; [ -f "$PART" ] && actual=$(wc -c < "$PART" | tr -d ' ')
if [ "$actual" -lt "$TOTAL" ]; then
  rm -f "$PART"
  curl {CURL_HTTPS_ONLY} -L --fail --silent --show-error --retry 8 --retry-delay 5 -b "$COOKIE" -e {shlex.quote(page)} -o "$PART" {shlex.quote(download)}
fi
actual=$(wc -c < "$PART" | tr -d ' '); [ "$actual" -ge "$TOTAL" ]
trap - EXIT HUP INT TERM
cleanup
printf 'SEGMENTS_READY=1\\n'
"""

    def _download_script_direct(self, download: str, page: str, name: str, job_id: str, total: int, target_dir: str, cookie: str = "", expected_sha256: str = "", mode: str = "segmented", capture_headers: bool = False) -> str:
        if not download.startswith("https://"):
            raise ValueError("직접 다운로드 주소가 올바르지 않습니다.")
        prefix = f"{target_dir}/.{name}.{job_id}.segment"
        curl_config = f"/tmp/nas_download_{job_id}.curl.conf"
        config_lines = [
            f'url = "{_curl_config_value(download)}"',
            f'referer = "{_curl_config_value(page)}"',
            'proto = "=https"',
            'proto-redir = "=https"',
        ]
        if cookie:
            config_lines.append(f'header = "{_curl_config_value("Cookie: " + cookie)}"')
        config_body = "\n".join(config_lines)
        config_setup = f'''CURL_CONFIG={shlex.quote(curl_config)}
umask 077
cat > "$CURL_CONFIG" <<'NASDROP_CURL_CONFIG'
{config_body}
NASDROP_CURL_CONFIG
cleanup() {{ rm -f "$CURL_CONFIG"; }}
trap cleanup EXIT HUP INT TERM
'''
        response_headers = f"{target_dir}/.response-headers"
        header_probe = ""
        if capture_headers:
            header_probe = f"(curl --config \"$CURL_CONFIG\" -L --fail --silent --show-error -I -o {shlex.quote(response_headers)} || rm -f {shlex.quote(response_headers)})\n"
        if mode == "single":
            part = f"{prefix}.0"
            return f"""#!/bin/sh
set -eu
TOTAL={total}
PART={shlex.quote(part)}
{config_setup}{header_probe}existing=0; [ -f "$PART" ] && existing=$(wc -c < "$PART" | tr -d ' ')
[ "$existing" -le "$TOTAL" ] || {{ rm -f "$PART"; existing=0; }}
if [ "$existing" -lt "$TOTAL" ]; then
  if [ "$existing" -gt 0 ]; then
    curl --config "$CURL_CONFIG" -L --fail --silent --show-error --retry 8 --retry-delay 5 -C - -o "$PART"
  else
    curl --config "$CURL_CONFIG" -L --fail --silent --show-error --retry 8 --retry-delay 5 -o "$PART"
  fi
fi
actual=$(wc -c < "$PART" | tr -d ' '); [ "$actual" -eq "$TOTAL" ]
trap - EXIT HUP INT TERM
cleanup
printf 'SEGMENTS_READY=1\\n'
"""
        return f"""#!/bin/sh
set -eu
TOTAL={total}
COUNT=8
CHUNK=$(( (TOTAL + COUNT - 1) / COUNT ))
{config_setup}{header_probe}i=0
while [ "$i" -lt "$COUNT" ]; do
  start=$(( i * CHUNK )); end=$(( start + CHUNK - 1 )); [ "$end" -ge "$TOTAL" ] && end=$(( TOTAL - 1 ))
  part={shlex.quote(prefix)}.$i
  (expected=$(( end - start + 1 )); existing=0; [ -f "$part" ] && existing=$(wc -c < "$part" | tr -d ' '); [ "$existing" -le "$expected" ] || rm -f "$part"; [ -f "$part" ] && existing=$(wc -c < "$part" | tr -d ' ') || existing=0; if [ "$existing" -lt "$expected" ]; then from=$(( start + existing )); more="$part.more"; curl --config "$CURL_CONFIG" -L --fail --silent --show-error --retry 8 --retry-delay 5 -r "$from-$end" -o "$more"; cat "$more" >> "$part"; rm -f "$more"; fi; actual=$(wc -c < "$part" | tr -d ' '); [ "$actual" -eq "$expected" ]) &
  i=$(( i + 1 ))
done
wait
trap - EXIT HUP INT TERM
cleanup
printf 'SEGMENTS_READY=%s\\n' "$COUNT"
"""

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            process.terminate()

    def pause(self, job_id: str) -> None:
        with self.condition:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            job = self.jobs[job_id]
            if job.status not in {"queued", "ready", "downloading", "waiting_processing", "verifying"}:
                raise ValueError("중지할 수 있는 작업이 아닙니다.")
            job.status = "paused"
            job.error = ""
            process = self.processes.get(job_id)
            if process:
                self._terminate(process)
            self.save()
            self.condition.notify_all()

    def resume(self, job_id: str) -> None:
        with self.condition:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            job = self.jobs[job_id]
            if job.status not in {"paused", "failed", "cancelled"}:
                raise ValueError("다시 시작할 수 있는 작업이 아닙니다.")
            job.status = "queued"
            job.error = ""
            job.output = ""
            job.extracted = False
            job.not_before = 0
            self.save()
            self.condition.notify_all()

    def submit_password(self, job_id: str, password: object) -> None:
        normalized = _validate_job_password(password)
        if not normalized:
            raise ValueError("압축 암호를 입력해 주세요.")
        with self.condition:
            job = self.jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            if job.status != "password_required":
                raise ValueError("현재 암호 입력이 필요한 작업이 아닙니다.")
            save_job_password(job_id, normalized)
            job.status = "queued"
            job.error = ""
            job.not_before = 0
            self.save()
            self.condition.notify_all()

    def delete(self, job_ids: list[str]) -> int:
        with self.lock:
            for job_id in job_ids:
                job = self.jobs.get(job_id)
                if not job:
                    raise KeyError(job_id)
                if job.status in {"queued", "ready", "downloading", "waiting_processing", "verifying", "extracting", "publishing"}:
                    raise ValueError("실행 중인 작업은 먼저 멈춰 주세요.")
            for job_id in job_ids:
                job = self.jobs.pop(job_id, None)
                self.private_downloads.pop(job_id, None)
                delete_job_secrets(job_id)
                if job:
                    try:
                        workspace = job_workspace(job.target or NAS_TARGET, job.id)
                        shutil.rmtree(workspace, ignore_errors=True)
                        workspace.parent.rmdir()
                    except (OSError, ValueError):
                        pass
            self.save()
            return len(job_ids)

    def clear_completed(self) -> int:
        with self.lock:
            completed = [job_id for job_id, job in self.jobs.items() if job.status == "completed"]
            for job_id in completed:
                self.jobs.pop(job_id, None)
                delete_job_secrets(job_id)
            self.save()
            return len(completed)

    def cancel(self, job_id: str) -> None:
        self.pause(job_id)


CONTROLLER = Controller()


def _clean_download_name(value: str) -> str:
    name = html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
    return re.sub(r"[\\/\x00-\x1f:]", "_", name)[:180]


def response_download_name(headers_path: Path) -> str:
    """Read the last safe Content-Disposition filename captured by curl."""
    try:
        raw = headers_path.read_bytes()[:256_000]
    except OSError:
        return ""
    values = re.findall(rb"(?im)^content-disposition\s*:\s*([^\r\n]+)", raw)
    return content_disposition_download_name(values)


def content_disposition_download_name(values: list[bytes]) -> str:
    """Resolve an authoritative filename, preferring RFC 5987 filename*."""
    for value in reversed(values):
        extended = re.search(rb"(?i)(?:^|;)\s*filename\*\s*=\s*(?:\"([^\"]*)\"|([^;\s]*))", value)
        if extended:
            encoded = (extended.group(1) or extended.group(2) or b"").decode("ascii", "replace")
            charset, separator, encoded_name = encoded.partition("'")
            if separator:
                _language, separator, encoded_name = encoded_name.partition("'")
            try:
                name = unquote(encoded_name if separator else encoded, encoding=charset or "utf-8", errors="strict")
            except (LookupError, UnicodeDecodeError):
                name = unquote(encoded_name if separator else encoded)
            cleaned = _clean_download_name(name)
            if cleaned and cleaned not in {".", ".."}:
                return cleaned
        message = Message()
        message["Content-Disposition"] = value.decode("latin-1", "replace")
        name = message.get_filename() or ""
        try:
            name = name.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        cleaned = _clean_download_name(name)
        if cleaned and cleaned not in {".", ".."}:
            return cleaned
    return ""


def service_path_id(parsed, prefix: str = "") -> str:
    parts = parsed.path.strip("/").split("/")
    expected = 2 if prefix else 1
    if len(parts) != expected or (prefix and parts[0] != prefix):
        raise ValueError("지원 서비스의 공유 링크 형식이 아닙니다.")
    value = unquote(parts[-1])
    if not SAFE_SERVICE_ID.fullmatch(value):
        raise ValueError("링크 경로에 사용할 수 없는 문자가 있습니다.")
    return value


def _is_buzzheavier_download_host(host: str) -> bool:
    return bool(BUZZHEAVIER_DOWNLOAD_HOST.fullmatch(host.lower()))


def _validate_buzzheavier_download_url(raw_url: str) -> tuple[str, str, str]:
    value = raw_url.strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Buzzheavier 직접 다운로드 주소의 포트가 올바르지 않습니다.") from exc
    if (
        parsed.scheme != "https"
        or not _is_buzzheavier_download_host(host)
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
    ):
        raise ValueError("Buzzheavier의 Copy download link로 복사한 HTTPS 주소가 아닙니다.")
    file_id = service_path_id(parsed, "d")
    query = parse_qs(parsed.query, keep_blank_values=True)
    tokens = query.get("v", [])
    if set(query) != {"v"} or len(tokens) != 1 or not BUZZHEAVIER_TOKEN.fullmatch(tokens[0]):
        raise ValueError("Buzzheavier 서명 토큰이 없거나 올바르지 않습니다. Copy download link를 다시 눌러 주세요.")
    direct_url = parsed._replace(fragment="").geturl()
    return direct_url, file_id, host


class BuzzheavierRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        parsed = urlparse(new_url)
        if parsed.scheme != "https" or not _is_buzzheavier_download_host(parsed.hostname or ""):
            raise ValueError("Buzzheavier가 허용되지 않은 서버로 이동을 요청했습니다.")
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def inspect_buzzheavier(raw_url: str) -> dict:
    direct_url, file_id, _host = _validate_buzzheavier_download_url(raw_url)
    canonical = f"https://buzzheavier.com/{file_id}"
    opener = build_opener(BuzzheavierRedirectHandler())
    request = Request(
        direct_url,
        method="HEAD",
        headers={"User-Agent": f"NASDrop/{PACKAGE_VERSION}", "Accept": "*/*"},
    )
    with opener.open(request, timeout=30) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or not _is_buzzheavier_download_host(final.hostname or ""):
            raise ValueError("Buzzheavier 최종 다운로드 서버가 올바르지 않습니다.")
        values = [
            value.encode("latin-1", "replace")
            for value in response.headers.get_all("Content-Disposition", [])
        ]
        name = content_disposition_download_name(values)
        try:
            size = int(response.headers.get("Content-Length", "0"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Buzzheavier 파일 크기를 확인하지 못했습니다.") from exc
        accepts_ranges = response.headers.get("Accept-Ranges", "").strip().lower()
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if not name or size <= 0 or size > MAX_FILE_BYTES or content_type == "text/html":
        raise ValueError("허용할 수 없는 Buzzheavier 파일 정보입니다.")
    if accepts_ranges != "bytes":
        raise ValueError("이 Buzzheavier 링크는 이어받기 가능한 직접 파일 주소가 아닙니다.")
    return {
        "url": canonical,
        "name": name,
        "size": size,
        "expires": "서명 링크",
        "provider": "buzzheavier",
        "download_url": direct_url,
    }


def parse_gigafile_page(source: str, canonical: str, host: str, file_id: str) -> dict:
    size_match = re.search(r"var\s+size\s*=\s*(\d+)", source)
    name_match = re.search(r'id="dl"[^>]*>\s*(.*?)\s*</span>', source, re.S | re.I)
    expires_match = re.search(r'class="download_term_value"[^>]*>(.*?)</span>', source, re.S | re.I)
    download_mode = "gigafile_file"
    download_url = f"https://{host}/download.php?file={file_id}"
    if size_match and name_match:
        size = int(size_match.group(1))
        name = _clean_download_name(name_match.group(1))
    else:
        files_match = re.search(r"var\s+files\s*=\s*(\[.*?\])\s*;", source, re.S)
        bundle_name_match = re.search(r'id="matomete_zip_filename"[^>]*>\s*(.*?)\s*</span>', source, re.S | re.I)
        if not files_match or not bundle_name_match:
            raise ValueError("파일 정보를 읽지 못했습니다. 링크가 만료됐는지 확인해 주세요.")
        try:
            files = json.loads(files_match.group(1))
            sizes = [int(item["size"]) for item in files if isinstance(item, dict)]
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("GigaFile 묶음 파일 정보를 읽지 못했습니다.") from exc
        if not files or len(sizes) != len(files) or any(value <= 0 for value in sizes):
            raise ValueError("GigaFile 묶음에 받을 수 있는 파일이 없습니다.")
        size = sum(sizes)
        name = _clean_download_name(bundle_name_match.group(1))
        download_mode = "gigafile_zip"
        download_url = f"https://{host}/dl_zip.php?file={file_id}"
    if not name or size <= 0 or size > MAX_FILE_BYTES:
        raise ValueError("허용할 수 없는 파일 정보입니다.")
    expires = ""
    if expires_match:
        expires = html.unescape(re.sub(r"<[^>]+>", "", expires_match.group(1))).strip()
    return {
        "url": canonical, "name": name, "size": size, "expires": expires, "provider": "gigafile",
        "download_mode": download_mode, "download_url": download_url,
    }


def inspect_gigafile(raw_url: str) -> dict:
    parsed = urlparse(raw_url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not GIGAFILE_HOST.fullmatch(host):
        raise ValueError("정식 GigaFile HTTPS 링크가 아닙니다.")
    file_id = service_path_id(parsed)
    canonical = f"https://{host}/{file_id}"
    opener = build_opener(HTTPCookieProcessor())
    request = Request(canonical, headers={"User-Agent": "Mozilla/5.0 NAS Download Portal"})
    with opener.open(request, timeout=30) as response:
        source = response.read(2_000_000).decode("utf-8", "replace")
    inspected = parse_gigafile_page(source, canonical, host, file_id)
    try:
        head_request = Request(
            str(inspected["download_url"]), method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 NAS Download Portal", "Referer": canonical},
        )
        with opener.open(head_request, timeout=30) as response:
            values = [value.encode("latin-1", "replace") for value in response.headers.get_all("Content-Disposition", [])]
        actual_name = content_disposition_download_name(values)
        if actual_name:
            inspected["name"] = actual_name
    except (HTTPError, OSError, ValueError):
        pass
    return inspected


def _retry_delay(exc: HTTPError, attempt: int) -> float:
    try:
        retry_after = float(exc.headers.get("Retry-After", ""))
    except (AttributeError, TypeError, ValueError):
        retry_after = 2 ** attempt
    return min(30.0, max(1.0, retry_after))


def _json_request(
    url: str, *, method: str = "GET", headers: dict[str, str] | None = None, retry_429: bool = True,
) -> dict:
    attempts = 4 if retry_429 else 1
    for attempt in range(attempts):
        request = Request(url, method=method, headers=headers or {})
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read(4_000_000))
        except HTTPError as exc:
            if exc.code != HTTPStatus.TOO_MANY_REQUESTS or attempt == attempts - 1:
                raise
            time.sleep(_retry_delay(exc, attempt))
    raise RuntimeError("HTTP 요청 재시도 상태가 올바르지 않습니다.")


def _gofile_json_request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None) -> dict:
    _gofile_guard()
    try:
        return _json_request(url, method=method, headers=headers, retry_429=False)
    except HTTPError as exc:
        if exc.code == HTTPStatus.TOO_MANY_REQUESTS:
            raise _trip_gofile_cooldown(
                _gofile_retry_after(exc, GOFILE_RATE_LIMIT_COOLDOWN_SECONDS),
                "GoFile 요청 제한(HTTP 429)이 감지되었습니다.",
            ) from exc
        raise
    except (TimeoutError, OSError) as exc:
        raise _trip_gofile_cooldown(
            GOFILE_NETWORK_COOLDOWN_SECONDS,
            "GoFile 연결이 응답하지 않습니다.",
        ) from exc


def _gofile_website_token(account_token: str) -> str:
    _gofile_guard()
    request = Request("https://gofile.io/js/wt.obf.js", headers={"User-Agent": GOFILE_USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            script = response.read(2_000_000).decode("utf-8")
    except HTTPError as exc:
        if exc.code == HTTPStatus.TOO_MANY_REQUESTS:
            raise _trip_gofile_cooldown(
                _gofile_retry_after(exc, GOFILE_RATE_LIMIT_COOLDOWN_SECONDS),
                "GoFile 요청 제한(HTTP 429)이 감지되었습니다.",
            ) from exc
        raise
    except (TimeoutError, OSError) as exc:
        raise _trip_gofile_cooldown(
            GOFILE_NETWORK_COOLDOWN_SECONDS,
            "GoFile 연결이 응답하지 않습니다.",
        ) from exc
    payload = json.dumps({"script": script, "token": account_token, "userAgent": GOFILE_USER_AGENT, "language": "en-US"})
    result = subprocess.run(["node", str(ROOT / "gofile_wt.mjs")], input=payload, text=True, capture_output=True, timeout=10)
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{64}", result.stdout.strip()):
        raise ValueError("Gofile 웹 인증 토큰을 만들지 못했습니다.")
    return result.stdout.strip()


def _gofile_session() -> tuple[str, str]:
    global GOFILE_SESSION
    with GOFILE_SESSION_LOCK:
        current = time.monotonic()
        if GOFILE_SESSION and current - GOFILE_SESSION[0] < 900:
            return GOFILE_SESSION[1], GOFILE_SESSION[2]
        created = _gofile_json_request("https://api.gofile.io/accounts", method="POST")
        token = str(created.get("data", {}).get("token", ""))
        if not token:
            raise ValueError("Gofile 게스트 인증을 만들지 못했습니다.")
        website_token = _gofile_website_token(token)
        GOFILE_SESSION = (current, token, website_token)
        return token, website_token


def _gofile_contents(content_id: str, token: str, website_token: str, page: int = 1) -> dict:
    global GOFILE_LAST_REQUEST
    query = urlencode({"page": page, "pageSize": 100, "sortField": "createTime", "sortDirection": -1})
    with GOFILE_REQUEST_LOCK:
        delay = GOFILE_MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - GOFILE_LAST_REQUEST)
        if delay > 0:
            time.sleep(delay)
        envelope = _gofile_json_request(
            f"https://api.gofile.io/contents/{content_id}?{query}",
            headers={"Authorization": f"Bearer {token}", "X-Website-Token": website_token, "X-BL": "en-US", "User-Agent": GOFILE_USER_AGENT},
        )
        GOFILE_LAST_REQUEST = time.monotonic()
    data = envelope.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("Gofile 파일 목록을 읽지 못했습니다.")
    if not data.get("canAccess", True):
        raise ValueError("비밀번호 또는 별도 권한이 필요한 Gofile 링크입니다.")
    return data


def _gofile_file(item: dict, token: str, fallback_code: str, relative_path: str = "") -> dict:
    size = int(item.get("size", 0))
    name = _clean_download_name(str(item.get("name", "")))
    download_url = str(item.get("link", ""))
    download_host = (urlparse(download_url).hostname or "").lower()
    code = str(item.get("code") or fallback_code)
    if not SAFE_SERVICE_ID.fullmatch(code):
        raise ValueError("Gofile 파일의 공유 식별자가 올바르지 않습니다.")
    if not name or size <= 0 or size > MAX_FILE_BYTES or not download_url.startswith("https://") or not download_host.endswith(".gofile.io"):
        raise ValueError("허용할 수 없는 Gofile 파일 정보입니다.")
    return {
        "url": f"https://gofile.io/d/{code}", "name": name, "size": size, "expires": "",
        "provider": "gofile", "download_url": download_url, "download_token": token,
        "relative_path": relative_path,
    }


def _gofile_folder_name(value: object) -> str:
    name = _clean_download_name(str(value)).strip(". ")
    return name or "Gofile 폴더"


def inspect_gofile(raw_url: str) -> dict:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {"gofile.io", "www.gofile.io"}:
        raise ValueError("정식 Gofile HTTPS 링크가 아닙니다.")
    share_id = service_path_id(parsed, "d")
    token, website_token = _gofile_session()
    root = _gofile_contents(share_id, token, website_token)
    if root.get("type") == "file":
        return _gofile_file(root, token, share_id)

    files = []
    folder_queue = [(share_id, root, "")]
    visited_folders = set()
    visited_items = set()
    while folder_queue:
        folder_ref, first_page, relative_path = folder_queue.pop(0)
        folder_key = str(first_page.get("id") or folder_ref)
        if folder_key in visited_folders:
            continue
        visited_folders.add(folder_key)
        page = 1
        while True:
            data = first_page if page == 1 else _gofile_contents(folder_ref, token, website_token, page)
            children = data.get("children", {})
            items = list(children.values()) if isinstance(children, dict) else list(children or [])
            new_items = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_key = str(item.get("id") or item.get("code") or item.get("link") or "")
                if not item_key or item_key in visited_items:
                    continue
                visited_items.add(item_key)
                new_items += 1
                if item.get("type") == "file" and item.get("link"):
                    files.append(_gofile_file(item, token, share_id, relative_path))
                elif item.get("type") == "folder":
                    child_ref = str(item.get("id") or item.get("code") or "")
                    if not child_ref:
                        continue
                    child_name = _gofile_folder_name(item.get("name"))
                    child_path = "/".join(part for part in (relative_path, child_name) if part)
                    folder_queue.append((child_ref, _gofile_contents(child_ref, token, website_token), child_path))
            if len(items) < 100 or new_items == 0:
                break
            page += 1

    if not files:
        raise ValueError("Gofile 공유 폴더에 다운로드할 파일이 없습니다.")
    if len(files) == 1:
        return files[0]
    folder_name = _gofile_folder_name(root.get("name"))
    return {
        "url": f"https://gofile.io/d/{share_id}", "name": f"{folder_name} ({len(files)}개 파일)",
        "size": sum(int(file["size"]) for file in files), "expires": "", "provider": "gofile",
        "batch": True, "file_count": len(files), "files": files,
    }


def inspect_pixeldrain(raw_url: str) -> dict:
    parsed = urlparse(raw_url.strip())
    hosts = {"pixeldrain.com", "www.pixeldrain.com", "pixeldrain.net", "pixeldra.in"}
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in hosts:
        raise ValueError("정식 Pixeldrain HTTPS 링크가 아닙니다.")
    file_id = service_path_id(parsed, "u")
    metadata = _json_request(
        f"https://pixeldrain.com/api/file/{file_id}/info",
        headers={"User-Agent": "NAS Download Portal/0.4.2"},
    )
    if not metadata.get("success") or not metadata.get("can_download", True):
        message = str(metadata.get("availability_message") or "파일을 다운로드할 수 없습니다.")
        raise ValueError(f"Pixeldrain: {message}")
    size = int(metadata.get("size", 0))
    name = re.sub(r"[\\/\x00-\x1f:]", "_", str(metadata.get("name", ""))).strip()[:180]
    expected_sha256 = str(metadata.get("hash_sha256", "")).lower()
    if not name or size <= 0 or size > MAX_FILE_BYTES or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("허용할 수 없는 Pixeldrain 파일 정보입니다.")
    canonical = f"https://pixeldrain.com/u/{file_id}"
    return {
        "url": canonical, "name": name, "size": size, "expires": "", "provider": "pixeldrain",
        "download_url": f"https://pixeldrain.com/api/file/{file_id}?download",
        "expected_sha256": expected_sha256,
    }


def provider_for_url(raw_url: str) -> str:
    host = (urlparse(raw_url).hostname or "").lower()
    if host in {"gofile.io", "www.gofile.io"}:
        return "gofile"
    if host in {"pixeldrain.com", "www.pixeldrain.com", "pixeldrain.net", "pixeldra.in"}:
        return "pixeldrain"
    if host == "buzzheavier.com" or _is_buzzheavier_download_host(host):
        return "buzzheavier"
    return "gigafile"


def inspect_download(raw_url: str) -> dict:
    host = (urlparse(raw_url.strip()).hostname or "").lower()
    try:
        if _is_buzzheavier_download_host(host):
            return inspect_buzzheavier(raw_url)
        if host in {"buzzheavier.com", "www.buzzheavier.com"}:
            raise ValueError("Buzzheavier 페이지에서 Copy download link를 누른 뒤 복사된 직접 주소를 입력해 주세요.")
        if host in {"gofile.io", "www.gofile.io"}:
            return inspect_gofile(raw_url)
        if host in {"pixeldrain.com", "www.pixeldrain.com", "pixeldrain.net", "pixeldra.in"}:
            return inspect_pixeldrain(raw_url)
        return inspect_gigafile(raw_url)
    except HTTPError as exc:
        if _is_buzzheavier_download_host(host) and exc.code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND}:
            raise ValueError("Buzzheavier 직접 링크가 만료됐거나 사용할 수 없습니다. Copy download link를 다시 눌러 주세요.") from exc
        if exc.code == HTTPStatus.TOO_MANY_REQUESTS:
            raise ValueError("Gofile 요청이 몰려 잠시 제한되었습니다. 잠시 후 다시 시도해 주세요.") from exc
        raise ValueError(f"다운로드 서비스가 HTTP {exc.code} 응답을 반환했습니다. 링크가 만료됐는지 확인해 주세요.") from exc
    except (TimeoutError, OSError) as exc:
        raise ValueError("다운로드 서비스에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc


def public_inspection(inspected: dict) -> dict:
    keys = {"url", "name", "size", "expires", "provider", "batch", "file_count", "inspection_id"}
    return {key: value for key, value in inspected.items() if key in keys}


def cache_inspection(inspected: dict) -> dict:
    inspection_id = secrets.token_urlsafe(18)
    current = time.monotonic()
    with INSPECTION_CACHE_LOCK:
        expired = [key for key, (expires, _) in INSPECTION_CACHE.items() if expires <= current]
        for key in expired:
            INSPECTION_CACHE.pop(key, None)
        INSPECTION_CACHE[inspection_id] = (current + INSPECTION_TTL_SECONDS, inspected)
    result = public_inspection(inspected)
    result["inspection_id"] = inspection_id
    return result


def consume_inspection(payload: dict) -> dict:
    inspection_id = str(payload.get("inspection_id", ""))
    if inspection_id:
        with INSPECTION_CACHE_LOCK:
            cached = INSPECTION_CACHE.pop(inspection_id, None)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        raise ValueError("링크 확인 정보가 만료되었습니다. 링크를 다시 확인해 주세요.")
    return inspect_download(str(payload.get("url", "")))


def storage_root_for(path: Path) -> Path | None:
    for root in STORAGE_ROOTS:
        try:
            path.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def normalize_target(raw_path: str) -> str:
    value = str(raw_path or "").strip()
    if not value:
        raise ValueError("저장 폴더를 선택해 주세요.")
    target = Path(value).resolve()
    normalized = str(target)
    if storage_root_for(target) is None:
        raise ValueError("허용된 저장소 마운트 안의 폴더만 선택할 수 있습니다.")
    if not target.is_dir():
        raise ValueError("선택한 저장 폴더가 없습니다.")
    if not os.access(normalized, os.W_OK | os.X_OK):
        raise ValueError("패키지 계정에 이 폴더의 쓰기 권한이 없습니다.")
    return normalized


def prepare_batch_target(base_path: str, relative_path: str) -> str:
    value = relative_path.strip("/")
    if not value:
        return base_path
    parts = value.split("/")
    if any(not part or part in {".", ".."} or _gofile_folder_name(part) != part for part in parts):
        raise ValueError("Gofile 하위 폴더 경로가 올바르지 않습니다.")
    base = Path(base_path).resolve()
    destination = base.joinpath(*parts).resolve()
    try:
        destination.relative_to(base)
    except ValueError as exc:
        raise ValueError("Gofile 하위 폴더가 저장 위치를 벗어납니다.") from exc
    destination.mkdir(parents=True, exist_ok=True)
    if not os.access(str(destination), os.W_OK | os.X_OK):
        raise ValueError("생성된 하위 폴더에 쓰기 권한이 없습니다.")
    return str(destination)


def browse_folders(raw_path: str) -> dict:
    value = str(raw_path or "/").strip() or "/"
    if value == "/":
        shares = []
        for root in STORAGE_ROOTS:
            if re.fullmatch(r"volume[0-9]+", root.name):
                try:
                    for path in root.iterdir():
                        if path.is_dir() and not path.name.startswith((".", "@")) and path.name != "lost+found":
                            shares.append(path)
                except PermissionError:
                    continue
            else:
                shares.append(root)
        return {
            "path": "/", "parent": "", "writable": False,
            "folders": [{
                "name": path.name, "path": str(path), "volume": path.parent.name,
                "readable": os.access(str(path), os.R_OK | os.X_OK),
                "writable": os.access(str(path), os.W_OK | os.X_OK),
            } for path in sorted(shares, key=lambda item: item.name.lower())],
        }
    current = Path(value).resolve()
    normalized = str(current)
    storage_root = storage_root_for(current)
    if storage_root is None or not current.is_dir():
        raise ValueError("탐색할 수 없는 폴더입니다.")
    try:
        candidates = [path for path in current.iterdir() if path.is_dir() and not path.name.startswith((".", "@")) and path.name != "lost+found"]
    except PermissionError as exc:
        raise ValueError("이 폴더를 볼 권한이 없습니다.") from exc
    parent = "/" if current == storage_root or (re.fullmatch(r"volume[0-9]+", storage_root.name) and current.parent == storage_root) else str(current.parent)
    return {
        "path": normalized,
        "parent": parent,
        "writable": os.access(normalized, os.W_OK | os.X_OK),
        "folders": [{
            "name": path.name, "path": str(path),
            "readable": os.access(str(path), os.R_OK | os.X_OK),
            "writable": os.access(str(path), os.W_OK | os.X_OK),
        } for path in sorted(candidates, key=lambda item: item.name.lower())],
    }


def set_default_target(raw_path: str) -> str:
    global NAS_TARGET, CONFIG
    normalized = normalize_target(raw_path)
    with CONFIG_LOCK:
        updated = dict(CONFIG)
        updated["NAS_PORTAL_NAS_TARGET"] = normalized
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        temp = CONFIG_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(CONFIG_FILE)
        CONFIG = updated
        NAS_TARGET = normalized
    return normalized


def set_parallel_settings(enabled: object, limit: object) -> dict:
    global ALLOW_SAME_PROVIDER_PARALLEL, SAME_PROVIDER_LIMIT, CONFIG
    if not isinstance(enabled, bool):
        raise ValueError("같은 서비스 동시 다운로드 설정이 올바르지 않습니다.")
    try:
        normalized_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("동시 작업 수를 선택해 주세요.") from exc
    if normalized_limit not in {2, 3}:
        raise ValueError("같은 서비스 동시 작업 수는 2개 또는 3개만 선택할 수 있습니다.")
    with CONFIG_LOCK:
        updated = dict(CONFIG)
        updated["NAS_PORTAL_ALLOW_SAME_PROVIDER_PARALLEL"] = enabled
        updated["NAS_PORTAL_SAME_PROVIDER_LIMIT"] = normalized_limit
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        temp = CONFIG_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(CONFIG_FILE)
        CONFIG = updated
        ALLOW_SAME_PROVIDER_PARALLEL = enabled
        SAME_PROVIDER_LIMIT = normalized_limit
    CONTROLLER.settings_changed()
    return {"same_provider_parallel": enabled, "same_provider_limit": normalized_limit}


def set_launcher_port(raw_port: object) -> int:
    global LAUNCHER_PORT, CONFIG
    normalized = normalize_launcher_port(raw_port)
    with CONFIG_LOCK:
        updated = dict(CONFIG)
        updated["NAS_PORTAL_LAUNCHER_PORT"] = normalized
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        temp = CONFIG_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(CONFIG_FILE)
        CONFIG = updated
        LAUNCHER_PORT = normalized
        write_launcher_file(public_port=normalized)
    return normalized


def set_download_mode(raw_mode: object) -> str:
    global DOWNLOAD_MODE, CONFIG
    normalized = normalize_download_mode(raw_mode)
    with CONFIG_LOCK:
        updated = dict(CONFIG)
        updated["NAS_PORTAL_DOWNLOAD_MODE"] = normalized
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        temp = CONFIG_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(CONFIG_FILE)
        CONFIG = updated
        DOWNLOAD_MODE = normalized
    return normalized


def set_processing_settings(auto_extract: object = None, disk_protection: object = None) -> dict:
    global AUTO_EXTRACT_ARCHIVES, DISK_PROTECTION, CONFIG
    if auto_extract is None and disk_protection is None:
        raise ValueError("변경할 처리 설정이 없습니다.")
    if auto_extract is not None and not isinstance(auto_extract, bool):
        raise ValueError("자동 압축 해제 설정이 올바르지 않습니다.")
    if disk_protection is not None and not isinstance(disk_protection, bool):
        raise ValueError("디스크 보호 설정이 올바르지 않습니다.")
    with CONFIG_LOCK:
        updated = dict(CONFIG)
        if auto_extract is not None:
            updated["NAS_PORTAL_AUTO_EXTRACT_ARCHIVES"] = auto_extract
        if disk_protection is not None:
            updated["NAS_PORTAL_DISK_PROTECTION"] = disk_protection
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        temp = CONFIG_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(CONFIG_FILE)
        CONFIG = updated
        if auto_extract is not None:
            AUTO_EXTRACT_ARCHIVES = auto_extract
        if disk_protection is not None:
            DISK_PROTECTION = disk_protection
    CONTROLLER.settings_changed()
    return {"auto_extract_archives": AUTO_EXTRACT_ARCHIVES, "disk_protection": DISK_PROTECTION}


class Handler(BaseHTTPRequestHandler):
    server_version = "NasDownloadPortal/1.0"
    timeout = REQUEST_TIMEOUT_SECONDS

    def log_message(self, fmt: str, *args: object) -> None:
        LOGGER.warning("%s %s", self.client_address[0], fmt % args)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        LOGGER.info(
            "peer=%s client=%s %s %s %s %s",
            self.client_address[0], self.login_client_ip(), self.command,
            urlparse(self.path).path, code, size,
        )

    def send_json(self, status: int, payload: dict) -> None:
        if payload.get("error") and not payload.get("code"):
            payload = {**payload, "code": public_error_code(payload["error"])}
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorization_token(self) -> str:
        supplied = self.headers.get("authorization", "")
        if supplied.startswith("Bearer "):
            supplied = supplied[7:]
        return supplied.strip()

    def login_client_ip(self) -> str:
        return trusted_client_ip(
            self.client_address[0], self.headers.get("x-forwarded-for", "")
        )

    def auth_kind(self) -> str:
        supplied = self.authorization_token()
        return session_kind(supplied) if supplied else ""

    def authorized(self) -> bool:
        return bool(self.auth_kind())

    def body(self) -> dict:
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length가 올바르지 않습니다.") from exc
        if length < 0:
            raise ValueError("Content-Length는 음수일 수 없습니다.")
        if length > REQUEST_BODY_LIMIT:
            raise ValueError(f"요청 본문은 {REQUEST_BODY_LIMIT}바이트를 초과할 수 없습니다.")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("allow", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        if path == "/api/auth/status":
            return self.send_json(HTTPStatus.OK, {"configured": credentials_configured()})
        if path == "/api/jobs":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "로그인이 필요합니다."})
            return self.send_json(HTTPStatus.OK, {"jobs": CONTROLLER.public_jobs()})
        if parsed_path.path == "/api/folders":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "로그인이 필요합니다."})
            try:
                requested = parse_qs(parsed_path.query).get("path", ["/"])[0]
                return self.send_json(HTTPStatus.OK, browse_folders(requested))
            except ValueError as exc:
                return self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if path == "/api/status":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "로그인이 필요합니다."})
            target = Path(NAS_TARGET) if NAS_TARGET else None
            target_exists = bool(target and target.is_dir())
            return self.send_json(HTTPStatus.OK, {
                "version": PACKAGE_VERSION,
                "target": NAS_TARGET,
                "target_exists": target_exists,
                "target_writable": target_exists and os.access(str(target), os.W_OK | os.X_OK),
                "service_user": os.environ.get("NAS_PORTAL_SERVICE_USER") or os.environ.get("USER", ""),
                "same_provider_parallel": ALLOW_SAME_PROVIDER_PARALLEL,
                "same_provider_limit": SAME_PROVIDER_LIMIT,
                "download_mode": DOWNLOAD_MODE,
                "launcher_port": LAUNCHER_PORT,
                "max_parallel_downloads": MAX_PARALLEL_DOWNLOADS,
                "auto_extract_archives": AUTO_EXTRACT_ARCHIVES,
                "disk_protection": DISK_PROTECTION,
                "temporary_folder": ".nasdrop-tmp",
                "archive_formats": ["zip", "7z", "rar", "tar", "tar.gz", "tgz", "tar.bz2", "tbz2", "tar.xz", "txz"],
                "seven_zip_available": SEVEN_ZIP.is_file(),
                "gofile_cooldown": _gofile_cooldown_status(),
            })
        if path == "/api/account":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "로그인이 필요합니다."})
            token = self.authorization_token()
            return self.send_json(HTTPStatus.OK, {
                "configured": credentials_configured(),
                "username": str(CREDENTIALS.get("username", "")),
                "launcher_session": self.auth_kind() == "launcher",
                "launcher_reset_available": launcher_account_reset_allowed(token),
            })
        if path.startswith("/api/"):
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "찾을 수 없습니다."})
        self.serve_static()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "찾을 수 없습니다."})
        if path == "/api/login":
            try:
                payload = self.body()
                if not credentials_configured():
                    raise ValueError("계정이 아직 설정되지 않았습니다. DSM 아이콘 또는 Docker 계정 설정 명령으로 ID와 비밀번호를 먼저 설정하세요.")
                client_ip = self.login_client_ip()
                remaining = login_block_remaining(client_ip)
                if remaining:
                    return self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {
                        "error": f"로그인 시도가 너무 많습니다. 약 {max(1, (remaining + 59) // 60)}분 후 다시 시도하세요."
                    })
                username = payload.get("username")
                password = payload.get("password")
                valid = verify_credentials(username, password)
                record_login_result(client_ip, valid)
                if not valid:
                    return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "ID 또는 비밀번호가 올바르지 않습니다."})
                token = create_session(str(CREDENTIALS["username"]))
                return self.send_json(HTTPStatus.OK, {"token": token, "username": str(CREDENTIALS["username"])})
            except (ValueError, json.JSONDecodeError) as exc:
                return self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if path == "/api/launcher/session":
            supplied = self.authorization_token()
            with LAUNCHER_TOKEN_LOCK:
                if not supplied or not secrets.compare_digest(
                    supplied.encode("utf-8"), LAUNCHER_TOKEN.encode("utf-8"),
                ):
                    return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "DSM 아이콘 연결이 만료되었습니다. 아이콘을 다시 열어 주세요."})
                try:
                    rotate_launcher_token()
                except OSError:
                    LOGGER.exception("DSM launcher handoff could not be rotated")
                    return self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "DSM 아이콘 연결을 갱신하지 못했습니다."})
                token = create_session(
                    str(CREDENTIALS.get("username", "")), kind="launcher", ttl=LAUNCHER_SESSION_TTL_SECONDS,
                )
            return self.send_json(HTTPStatus.OK, {"token": token})
        if not self.authorized():
            return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "로그인이 필요합니다."})
        try:
            payload = self.body()
            if path == "/api/logout":
                revoke_session(self.authorization_token())
                return self.send_json(HTTPStatus.OK, {"ok": True})
            if path == "/api/account":
                auth_kind = self.auth_kind()
                reset_allowed = launcher_account_reset_allowed(self.authorization_token())
                if credentials_configured() and not reset_allowed:
                    if not verify_credentials(str(CREDENTIALS.get("username", "")), payload.get("current_password")):
                        raise ValueError("현재 비밀번호가 올바르지 않습니다.")
                username = replace_credentials(payload.get("username"), payload.get("password"))
                try:
                    rotate_launcher_token()
                except OSError:
                    LOGGER.exception("DSM launcher handoff could not be rotated after account update")
                result = {"ok": True, "username": username}
                if auth_kind in {"session", "launcher"}:
                    result["token"] = create_session(username)
                return self.send_json(HTTPStatus.OK, result)
            if path == "/api/inspect":
                inspected = inspect_download(str(payload.get("url", "")))
                return self.send_json(HTTPStatus.OK, {"file": cache_inspection(inspected)})
            if path == "/api/start":
                inspected = consume_inspection(payload)
                if (
                    inspected["url"] != payload.get("url")
                    or inspected["name"] != payload.get("name")
                    or inspected["size"] != int(payload.get("size", 0))
                ):
                    raise ValueError("파일 정보가 변경되어 다시 확인해야 합니다.")
                files = inspected.get("files") if inspected.get("batch") else [inspected]
                extraction_choice = payload.get("extract") if "extract" in payload else None
                jobs = CONTROLLER.start_many(
                    files, str(payload.get("target", "")), extraction_choice, str(payload.get("password", "")),
                )
                return self.send_json(HTTPStatus.ACCEPTED, {"job": asdict(jobs[0]), "jobs": [asdict(job) for job in jobs], "count": len(jobs)})
            if path == "/api/settings":
                result = {"ok": True}
                if "target" in payload:
                    result["target"] = set_default_target(str(payload.get("target", "")))
                if "same_provider_parallel" in payload or "same_provider_limit" in payload:
                    result.update(set_parallel_settings(payload.get("same_provider_parallel"), payload.get("same_provider_limit")))
                if "launcher_port" in payload:
                    result["launcher_port"] = set_launcher_port(payload.get("launcher_port"))
                if "download_mode" in payload:
                    result["download_mode"] = set_download_mode(payload.get("download_mode"))
                if "auto_extract_archives" in payload or "disk_protection" in payload:
                    result.update(set_processing_settings(
                        payload.get("auto_extract_archives") if "auto_extract_archives" in payload else None,
                        payload.get("disk_protection") if "disk_protection" in payload else None,
                    ))
                if len(result) == 1:
                    raise ValueError("변경할 설정이 없습니다.")
                return self.send_json(HTTPStatus.OK, result)
            cancel_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/cancel", path)
            if cancel_match:
                CONTROLLER.cancel(cancel_match.group(1))
                return self.send_json(HTTPStatus.OK, {"ok": True})
            pause_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/pause", path)
            if pause_match:
                CONTROLLER.pause(pause_match.group(1))
                return self.send_json(HTTPStatus.OK, {"ok": True})
            resume_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/resume", path)
            if resume_match:
                CONTROLLER.resume(resume_match.group(1))
                return self.send_json(HTTPStatus.OK, {"ok": True})
            password_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/password", path)
            if password_match:
                CONTROLLER.submit_password(password_match.group(1), payload.get("password", ""))
                return self.send_json(HTTPStatus.OK, {"ok": True})
            if path == "/api/jobs/delete":
                ids = payload.get("ids", [])
                if not isinstance(ids, list) or not ids or any(not re.fullmatch(r"[a-f0-9]{12}", str(item)) for item in ids):
                    raise ValueError("삭제할 작업을 선택해 주세요.")
                deleted = CONTROLLER.delete([str(item) for item in ids])
                return self.send_json(HTTPStatus.OK, {"ok": True, "deleted": deleted})
            if path == "/api/jobs/completed/clear":
                deleted = CONTROLLER.clear_completed()
                return self.send_json(HTTPStatus.OK, {"ok": True, "deleted": deleted})
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "찾을 수 없습니다."})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            return self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "내부 처리 중 오류가 발생했습니다."})

    def serve_static(self) -> None:
        if STATIC_DIR.is_dir():
            parsed = urlparse(self.path)
            relative = unquote(parsed.path).lstrip("/") or "index.html"
            candidate = (STATIC_DIR / relative).resolve()
            try:
                candidate.relative_to(STATIC_DIR)
            except ValueError:
                return self.send_error(HTTPStatus.FORBIDDEN)
            if not candidate.is_file() and "." not in Path(relative).name:
                candidate = STATIC_DIR / "index.html"
            if candidate.is_file():
                body = candidate.read_bytes()
                content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
                self.send_response(HTTPStatus.OK)
                self.send_header("content-type", content_type + ("; charset=utf-8" if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"} else ""))
                self.send_header("cache-control", "no-store")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        self.send_error(HTTPStatus.NOT_FOUND)


if __name__ == "__main__":
    configure_logging()
    refresh_launcher_safely()
    LOGGER.info("NAS Download Portal listening on http://%s:%s", LISTEN_HOST, LISTEN_PORT)
    try:
        ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler).serve_forever()
    except BaseException:
        LOGGER.exception("NAS Download Portal stopped unexpectedly")
        raise
