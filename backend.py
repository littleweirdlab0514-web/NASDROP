#!/usr/bin/env python3
"""Authenticated Synology portal and direct-to-NAS download controller."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
import base64
from email.message import Message
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from http.client import HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from http.cookiejar import CookieJar
import hashlib
import hmac
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
import socket
import stat
import subprocess
import sys
import tarfile
import threading
import time
import unicodedata
import zipfile
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, HTTPCookieProcessor, ProxyHandler, Request, build_opener
from transfer_parts import commit_fragment, segment_count, segment_chunk, initial_transfer_mode


ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("NAS_PORTAL_STATE_DIR", str(ROOT / "runtime"))).resolve()
STATE_FILE = STATE_DIR / "jobs.json"
AUTH_FILE = STATE_DIR / "credentials.json"
CONFIG_FILE = STATE_DIR / "config.json"
GOFILE_COOLDOWN_FILE = STATE_DIR / "gofile_cooldown.json"
SECRET_DIR = STATE_DIR / "job-secrets"
DSM_LAUNCHER_SECRET_FILE = Path(
    os.environ.get("NAS_PORTAL_DSM_LAUNCHER_SECRET_FILE", str(STATE_DIR / "dsm_launcher_secret")),
).resolve()


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
PACKAGE_VERSION = setting("NAS_PORTAL_VERSION", "0.9.26")
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
MAX_INSPECTION_CACHE_ENTRIES = 64
LOGIN_FAILURE_LIMIT = 5
LOGIN_BLOCK_SECONDS = 15 * 60
LOGIN_FAILURE_RETENTION_SECONDS = 15 * 60
MAX_LOGIN_FAILURE_ENTRIES = 4096
GLOBAL_LOGIN_FAILURE_WINDOW_SECONDS = 60
GLOBAL_LOGIN_FAILURE_LIMIT = 30
GLOBAL_LOGIN_COOLDOWN_SECONDS = 5
REQUEST_BODY_LIMIT = 16_384
REQUEST_TIMEOUT_SECONDS = 30
DSM_LAUNCHER_HANDOFF_TTL_SECONDS = 30
MAX_DSM_LAUNCHER_HANDOFFS = 32
ARCHIVE_EXTRACT_TIMEOUT_SECONDS = 6 * 60 * 60
CURL_HTTPS_ONLY = "--proto '=https' --proto-redir '=https'"
CURL_NO_REDIRECTS = "--location --max-redirs 0"
CURL_PAGE_TIMEOUT = "--connect-timeout 15 --max-time 60"
CURL_PROBE_TIMEOUT = "--connect-timeout 10 --max-time 30"
CURL_STALL_GUARD = "--connect-timeout 15 --speed-limit 1024 --speed-time 120"
GIGAFILE_NAME_PROBE_TIMEOUT_SECONDS = 30
GIGAFILE_NAME_PROBE_WORKERS = 3
LOGGER = logging.getLogger("nasdrop")
LOGGER.addHandler(logging.NullHandler())
JOB_SECRET_LOCK = threading.RLock()
CONFIG_LOCK = threading.RLock()
DSM_LAUNCHER_HANDOFFS: dict[str, float] = {}
DSM_LAUNCHER_HANDOFFS_LOCK = threading.Lock()
FORWARDED_HEADER_LOCK = threading.Lock()
SHUTDOWN_EVENT = threading.Event()
UNTRUSTED_FORWARDED_HEADER_SEEN = False
UNTRUSTED_FORWARDED_HEADER_WARNED = False


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
        (("ID는 영문, 숫자",), "invalid_username"),
        (("비밀번호는 10~128자", "비밀번호에는 제어 문자"), "invalid_password"),
        (("로그인 시도가 너무 많",), "too_many_attempts"),
        (("계정이 아직 설정",), "account_not_configured"),
        (("현재 비밀번호",), "current_password_invalid"),
        (("DSM 아이콘 연결",), "launcher_expired"),
        (("권한", "쓰기 권한", "볼 권한"), "permission_denied"),
        (("GigaFile 다운로드 키",), "download_key_required"),
        (("암호가 필요", "암호를 입력", "Wrong password", "password"), "password_required"),
        (("Gofile 요청이 몰려", "429", "제한되었"), "rate_limited"),
        (("연결하지 못", "HTTP ", "응답을 반환", "응답이 일정 시간 멈춰"), "network_error"),
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
    if "must_change_password" in data and not isinstance(data["must_change_password"], bool):
        return {}
    return data


CREDENTIALS = load_credentials()
SESSIONS: dict[str, tuple[str, float, str, float]] = {}
SESSIONS_LOCK = threading.Lock()
LOGIN_FAILURES: dict[str, tuple[int, float, float]] = {}
LOGIN_FAILURES_LOCK = threading.Lock()
GLOBAL_LOGIN_FAILURES: list[float] = []
GLOBAL_LOGIN_BLOCKED_UNTIL = 0.0
GLOBAL_LOGIN_FAILURES_LOCK = threading.Lock()


def credentials_configured() -> bool:
    return bool(CREDENTIALS)


def password_change_required() -> bool:
    return CREDENTIALS.get("must_change_password") is True


def password_hash(password: str, salt: bytes, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def create_docker_bootstrap_credentials() -> bool:
    """Create the documented one-time Docker login without weakening normal password validation."""
    global CREDENTIALS
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_bytes(16)
    updated = {
        "algorithm": "pbkdf2_sha256",
        "iterations": PASSWORD_HASH_ITERATIONS,
        "username": "nasdrop",
        "salt": salt.hex(),
        "password_hash": password_hash("nasdrop", salt),
        "must_change_password": True,
    }
    encoded = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        descriptor = os.open(AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        try:
            AUTH_FILE.unlink()
        except OSError:
            pass
        raise
    CREDENTIALS = updated
    return True


def enforce_docker_default_password_change() -> bool:
    """Keep the documented Docker bootstrap login confined until it is replaced."""
    global CREDENTIALS
    if (
        not CREDENTIALS
        or password_change_required()
        or str(CREDENTIALS.get("username", "")).casefold() != "nasdrop"
        or not verify_credentials("nasdrop", "nasdrop")
    ):
        return False
    updated = dict(CREDENTIALS)
    updated["must_change_password"] = True
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = AUTH_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(AUTH_FILE)
    CREDENTIALS = updated
    with SESSIONS_LOCK:
        SESSIONS.clear()
    return True


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


def load_dsm_launcher_secret() -> bytes:
    try:
        encoded = DSM_LAUNCHER_SECRET_FILE.read_text(encoding="ascii").strip()
        secret = bytes.fromhex(encoded)
        if len(secret) == 32:
            return secret
    except (OSError, UnicodeError, ValueError):
        pass
    # The signed DSM handoff exists only for the installed Synology package.
    # Development and Docker runs do not configure a launcher path, so avoid an
    # import-time filesystem mutation and use a process-local secret instead.
    if LAUNCHER_FILE is None:
        return secrets.token_bytes(32)
    DSM_LAUNCHER_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_bytes(32)
    temporary = DSM_LAUNCHER_SECRET_FILE.with_suffix(".tmp")
    temporary.write_text(secret.hex() + "\n", encoding="ascii")
    temporary.chmod(0o600)
    temporary.replace(DSM_LAUNCHER_SECRET_FILE)
    return secret


DSM_LAUNCHER_SECRET = load_dsm_launcher_secret()


def create_dsm_launcher_handoff(username: str, current: int | None = None) -> str:
    """Create a signed short-lived handoff after DSM authenticated the CGI."""
    if not username or len(username) > 128 or any(ord(character) < 32 or ord(character) == 127 for character in username):
        raise ValueError("DSM 사용자 정보가 올바르지 않습니다.")
    issued = int(time.time()) if current is None else int(current)
    payload = json.dumps(
        {"u": username, "e": issued + DSM_LAUNCHER_HANDOFF_TTL_SECONDS, "n": secrets.token_hex(8)},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(DSM_LAUNCHER_SECRET, encoded, hashlib.sha256).digest()
    return encoded.decode("ascii") + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def validate_dsm_launcher_handoff(token: str, *, consume: bool) -> str:
    if not token or len(token) > 1024 or token.count(".") != 1:
        return ""
    encoded, supplied_signature = token.split(".", 1)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", encoded) or not re.fullmatch(r"[A-Za-z0-9_-]+", supplied_signature):
        return ""
    try:
        signature = base64.urlsafe_b64decode(supplied_signature + "=" * (-len(supplied_signature) % 4))
        payload_bytes = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        # Reject non-canonical encodings. Otherwise unused trailing Base64 bits
        # can create multiple token strings for one signature and bypass the
        # one-use fingerprint registry.
        canonical_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        canonical_payload = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
        if canonical_signature != supplied_signature or canonical_payload != encoded:
            return ""
        expected = hmac.new(DSM_LAUNCHER_SECRET, encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return ""
        payload = json.loads(payload_bytes)
        username = str(payload.get("u", ""))
        expiry = int(payload.get("e", 0))
        nonce = str(payload.get("n", ""))
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return ""
    current = time.time()
    if expiry <= current or expiry > current + DSM_LAUNCHER_HANDOFF_TTL_SECONDS + 5:
        return ""
    if not username or len(username) > 128 or not re.fullmatch(r"[0-9a-f]{16}", nonce):
        return ""
    fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
    with DSM_LAUNCHER_HANDOFFS_LOCK:
        expired = [value for value, saved_expiry in DSM_LAUNCHER_HANDOFFS.items() if saved_expiry <= current]
        for value in expired:
            DSM_LAUNCHER_HANDOFFS.pop(value, None)
        if fingerprint in DSM_LAUNCHER_HANDOFFS:
            return ""
        if consume:
            overflow = len(DSM_LAUNCHER_HANDOFFS) - MAX_DSM_LAUNCHER_HANDOFFS + 1
            if overflow > 0:
                for value in list(DSM_LAUNCHER_HANDOFFS)[:overflow]:
                    DSM_LAUNCHER_HANDOFFS.pop(value, None)
            DSM_LAUNCHER_HANDOFFS[fingerprint] = float(expiry)
    return username


def consume_dsm_launcher_handoff(token: str) -> str:
    return validate_dsm_launcher_handoff(token, consume=True)


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


def global_login_retry_after() -> int:
    with GLOBAL_LOGIN_FAILURES_LOCK:
        current = time.time()
        GLOBAL_LOGIN_FAILURES[:] = [
            value for value in GLOBAL_LOGIN_FAILURES
            if current - value < GLOBAL_LOGIN_FAILURE_WINDOW_SECONDS
        ]
        if GLOBAL_LOGIN_BLOCKED_UNTIL <= current:
            return 0
        return max(1, int(GLOBAL_LOGIN_BLOCKED_UNTIL - current + 0.999))


def record_global_login_failure() -> None:
    global GLOBAL_LOGIN_BLOCKED_UNTIL
    with GLOBAL_LOGIN_FAILURES_LOCK:
        current = time.time()
        GLOBAL_LOGIN_FAILURES[:] = [
            value for value in GLOBAL_LOGIN_FAILURES
            if current - value < GLOBAL_LOGIN_FAILURE_WINDOW_SECONDS
        ]
        GLOBAL_LOGIN_FAILURES.append(current)
        if len(GLOBAL_LOGIN_FAILURES) >= GLOBAL_LOGIN_FAILURE_LIMIT:
            GLOBAL_LOGIN_BLOCKED_UNTIL = current + GLOBAL_LOGIN_COOLDOWN_SECONDS
            GLOBAL_LOGIN_FAILURES.clear()


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


def note_forwarded_header(peer_ip: str, forwarded_for: str) -> None:
    """Warn once when a local reverse proxy is present but proxy mode is disabled."""
    global UNTRUSTED_FORWARDED_HEADER_SEEN, UNTRUSTED_FORWARDED_HEADER_WARNED
    if TRUST_FORWARDED_FOR or not forwarded_for:
        return
    try:
        if not ipaddress.ip_address(peer_ip).is_loopback:
            return
    except ValueError:
        return
    with FORWARDED_HEADER_LOCK:
        UNTRUSTED_FORWARDED_HEADER_SEEN = True
        if UNTRUSTED_FORWARDED_HEADER_WARNED:
            return
        UNTRUSTED_FORWARDED_HEADER_WARNED = True
    LOGGER.warning(
        "reverse proxy header detected from loopback while NAS_PORTAL_TRUST_FORWARDED_FOR is disabled; "
        "clients share one login-throttle bucket"
    )


def render_launcher_html(public_port: int) -> str:
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
  if (privateHost) targetProtocol = "http://";
  location.replace(targetProtocol + host + ":" + targetPort + "/");
</script></body></html>
'''


def write_launcher_file(public_port: int | None = None) -> None:
    if LAUNCHER_FILE is None:
        return
    port = LAUNCHER_PORT if public_port is None else normalize_launcher_port(public_port)
    temporary = LAUNCHER_FILE.with_suffix(".tmp")
    temporary.write_text(render_launcher_html(port), encoding="utf-8")
    temporary.chmod(0o644)
    temporary.replace(LAUNCHER_FILE)


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


class GigaFileDownloadKeyRequiredError(ValueError):
    """Raised when GigaFile requires a source-side download key."""


class GigaFileDownloadKeyInvalidError(GigaFileDownloadKeyRequiredError):
    """Raised only after the user supplied a key and GigaFile rejected it."""


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


def _validate_gigafile_download_key(value: object) -> str:
    key = str(value or "")
    if len(key) > 4 or any(ord(character) < 0x20 or ord(character) == 0x7f for character in key):
        raise ValueError("GigaFile 다운로드 키는 제어 문자 없이 4자 이내로 입력해 주세요.")
    return key


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


def save_job_download_key(job_id: str, download_key: object) -> None:
    normalized = _validate_gigafile_download_key(download_key)
    with JOB_SECRET_LOCK:
        data = _load_job_secrets(job_id)
        if normalized:
            data["download_key"] = normalized
        else:
            data.pop("download_key", None)
        _write_job_secrets(job_id, data)


def load_job_download_key(job_id: str) -> str:
    with JOB_SECRET_LOCK:
        try:
            return _validate_gigafile_download_key(_load_job_secrets(job_id).get("download_key", ""))
        except ValueError:
            return ""


def delete_job_download_key(job_id: str) -> None:
    save_job_download_key(job_id, "")


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
    transfer_mode: str = ""
    inspection_pending: bool = False
    delete_requested: bool = False


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


def _run_seven_zip(arguments: list[str], password: str, timeout: float | None = None, cancelled=None, process_callback=None) -> subprocess.CompletedProcess[str]:
    if not SEVEN_ZIP.is_file():
        raise ValueError("패키지의 7-Zip 압축 해제 엔진을 찾을 수 없습니다.")
    environment = dict(os.environ)
    environment.update({"LANG": "C", "LC_ALL": "C"})
    command = [str(SEVEN_ZIP), *arguments]
    run_options: dict[str, object] = {
        "capture_output": True, "text": True, "errors": "replace", "env": environment, "timeout": timeout,
    }
    if password:
        # A bare -p selects an empty password in 7-Zip. Omit it so the
        # password prompt reads stdin; never expose the password in argv.
        run_options["input"] = password + "\n"
    else:
        run_options["stdin"] = subprocess.DEVNULL
    result = _run_interruptible(command, cancelled=cancelled, process_callback=process_callback, **run_options)
    message = "\n".join((result.stdout, result.stderr)).strip()
    if password:
        message = message.replace(password, "***")
    if result.returncode != 0:
        if _password_failure(message) or not password and "encrypted" in message.lower():
            raise PasswordRequiredError("압축 암호가 필요하거나 입력한 암호가 올바르지 않습니다.")
        raise ValueError((message or "7-Zip 압축 해제 엔진이 작업을 완료하지 못했습니다.")[-400:])
    return result


def _run_interruptible(command, *, input=None, timeout=None, capture_output=True, cancelled=None, process_callback=None, **options):
    options.pop("stdin", None)
    process = subprocess.Popen(command, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, **options)
    deadline = time.monotonic() + timeout if timeout else float("inf")
    try:
        if process_callback:
            process_callback(process)
        while True:
            if SHUTDOWN_EVENT.is_set() or (cancelled and cancelled()):
                raise InterruptedError("서비스 중지로 압축 해제를 일시정지했습니다.")
            if time.monotonic() >= deadline:
                raise TimeoutError("압축 해제 제한시간을 초과했습니다.")
            try:
                out, err = process.communicate(input=input, timeout=0.25)
                return subprocess.CompletedProcess(command, process.returncode, out, err)
            except subprocess.TimeoutExpired:
                input = None
    finally:
        if process.poll() is None:
            Controller._stop_process(process)
        if process_callback:
            process_callback(None)


def _copy_checked(source, output, length, cancelled=None):
    while True:
        if SHUTDOWN_EVENT.is_set() or (cancelled and cancelled()):
            raise InterruptedError("서비스 중지로 후처리를 일시정지했습니다.")
        block = source.read(length)
        if not block:
            return
        output.write(block)


def _validate_seven_zip_listing(archive: Path, password: str, cancelled=None, process_callback=None) -> None:
    result = _run_seven_zip(["l", "-slt", "-ba", "-sccUTF-8", str(archive)], password, timeout=120, cancelled=cancelled, process_callback=process_callback)
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


def _extract_with_seven_zip(archive: Path, destination: Path, password: str, cancelled=None, process_callback=None) -> None:
    _validate_seven_zip_listing(archive, password, cancelled=cancelled, process_callback=process_callback)
    _run_seven_zip(
        ["x", "-y", "-bd", "-bb0", "-sccUTF-8", f"-o{destination}", str(archive)],
        password,
        timeout=ARCHIVE_EXTRACT_TIMEOUT_SECONDS,
        cancelled=cancelled,
        process_callback=process_callback,
    )
    _validate_extracted_tree(destination)


def extract_archive_safely(archive: Path, destination: Path, password: str = "", cancelled=None, process_callback=None) -> None:
    kind = archive_kind(archive.name)
    password = _validate_job_password(password)
    if kind == "7zip" or password:
        _extract_with_seven_zip(archive, destination, password, cancelled=cancelled, process_callback=process_callback)
        return
    if kind == "zip":
        try:
            with zipfile.ZipFile(archive) as source:
                infos = source.infolist()
                legacy_encoding = _zip_legacy_encoding(infos)
                _checked_archive_totals(len(infos), sum(max(0, info.file_size) for info in infos))
                for info in infos:
                    if SHUTDOWN_EVENT.is_set() or (cancelled and cancelled()):
                        raise InterruptedError("Archive processing stopped")
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
                        _copy_checked(reader, writer, length=1024 * 1024, cancelled=cancelled)
        except (NotImplementedError, RuntimeError) as exc:
            shutil.rmtree(destination, ignore_errors=True)
            destination.mkdir(mode=0o700)
            if "password" in str(exc).lower():
                raise PasswordRequiredError("압축 암호가 필요합니다.") from exc
            _extract_with_seven_zip(archive, destination, password, cancelled=cancelled, process_callback=process_callback)
        return
    if kind == "tar":
        with tarfile.open(archive, mode="r:*") as source:
            members = source.getmembers()
            _checked_archive_totals(len(members), sum(max(0, member.size) for member in members if member.isfile()))
            for member in members:
                if SHUTDOWN_EVENT.is_set() or (cancelled and cancelled()):
                    raise InterruptedError("Archive processing stopped")
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
                    _copy_checked(reader, writer, length=1024 * 1024, cancelled=cancelled)
        return
    raise ValueError("자동 압축 해제를 지원하지 않는 형식입니다.")


def fit_download_name(name: str, limit: int = 240) -> str:
    """Bound a filename component in UTF-8 bytes, retaining a useful suffix."""
    if len(name.encode("utf-8")) <= limit:
        return name
    suffix = next((s for s, _ in ARCHIVE_SUFFIXES if name.lower().endswith(s)), "")
    if not suffix:
        candidate = Path(name).suffix
        suffix = candidate if re.fullmatch(r"\.[A-Za-z0-9]{1,16}", candidate) else ""
    if suffix:
        suffix = name[-len(suffix):]
    tag = "~" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]
    budget = limit - len((tag + suffix).encode("utf-8"))
    stem = name[:-len(suffix)] if suffix else name
    return stem.encode("utf-8")[:budget].decode("utf-8", "ignore").rstrip(". ") + tag + suffix


def unique_destination(path: Path) -> Path:
    path = path.with_name(fit_download_name(path.name))
    if not path.exists():
        return path
    for number in range(1, 10_000):
        candidate = path.with_name(f"{path.name} ({number})") if path.is_dir() or not path.suffix else path.with_name(f"{path.stem} ({number}){path.suffix}")
        candidate = candidate.with_name(fit_download_name(candidate.name))
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
    for source in list(target.iterdir()) + list(workspace.iterdir()):
        if not source.is_file() or not source.name.startswith(prefix):
            continue
        remainder = source.name[len(prefix):]
        if remainder != "assembling" and not re.fullmatch(r"segment\.[0-7](?:\.(?:more|headers))?", remainder):
            continue
        destination = workspace / f".{job_id}.{remainder}"
        if destination.exists():
            raise ValueError("이전 다운로드 조각과 새 조각이 충돌합니다. 기존 데이터를 보존했습니다.")
        else:
            source.rename(destination)
        moved += 1
    return moved


def promote_download(artifact: Path, target_dir: str, auto_extract: bool, password: str = "", *, cancelled=None, publication_lock=None, process_callback=None) -> tuple[Path, bool]:
    target = Path(target_dir).resolve()
    if not artifact.is_file():
        raise ValueError("완성된 임시 파일을 찾을 수 없습니다.")
    kind = archive_kind(artifact.name) if auto_extract else ""
    if kind:
        extracted = artifact.parent / "extracted"
        if extracted.exists():
            shutil.rmtree(extracted)
        extracted.mkdir(mode=0o700)
        extract_archive_safely(artifact, extracted, password, cancelled=cancelled, process_callback=process_callback)
        if SHUTDOWN_EVENT.is_set() or (cancelled and cancelled()):
            raise InterruptedError("서비스 중지로 후처리를 일시정지했습니다.")
        base_name = archive_output_name(artifact.name)
        children = list(extracted.iterdir())
        with publication_lock or threading.RLock():
            if SHUTDOWN_EVENT.is_set() or (cancelled and cancelled()):
                raise InterruptedError("Publication stopped")
            output = unique_destination(target / base_name)
            if len(children) == 1 and children[0].is_dir() and children[0].name.casefold() == base_name.casefold():
                children[0].rename(output)
                extracted.rmdir()
            else:
                extracted.rename(output)
        return output, True
    with publication_lock or threading.RLock():
        if SHUTDOWN_EVENT.is_set() or (cancelled and cancelled()):
            raise InterruptedError("Publication stopped")
        output = unique_destination(target / artifact.name)
        artifact.rename(output)
    return output, False


class Controller:
    def __init__(self) -> None:
        self.stopping = False
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
                if item.get("delete_requested"):
                    # Do not replay a destructive request automatically after a crash.
                    item["delete_requested"] = False
                    item["status"] = "stopping"
                if item.get("status") in {"inspecting", "downloading", "waiting_processing", "verifying", "extracting", "publishing", "ready", "stopping"}:
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
        return any(job.status in {"inspecting", "ready", "downloading", "waiting_processing", "verifying", "extracting", "publishing"} for job in self.jobs.values())

    def start(self, file: dict, target: str = "", extract: bool | None = None, password: str = "") -> Job:
        return self.start_many([file], target, extract, password)[0]

    def enqueue_gigafile(self, url: str, target: str = "", extract: bool | None = None, password: str = "", download_key: str = "") -> Job:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not GIGAFILE_HOST.fullmatch(host) or parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise ValueError("정식 GigaFile HTTPS 링크가 아닙니다.")
        file_id = service_path_id(parsed)
        if extract is not None and not isinstance(extract, bool):
            raise ValueError("압축 해제 선택값이 올바르지 않습니다.")
        secret = _validate_job_password(password)
        source_key = _validate_gigafile_download_key(download_key)
        destination = normalize_target(target or NAS_TARGET)
        with self.condition:
            if self.stopping:
                raise ValueError("서비스가 종료 중입니다.")
            if sum(j.inspection_pending for j in self.jobs.values()) >= 100:
                raise ValueError("정보 확인 대기 작업이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
            job = Job(secrets.token_hex(6), f"GigaFile {file_id}", f"https://{host}/{file_id}",
                      0, 0, "inspecting", now(), target=destination,
                      extract=AUTO_EXTRACT_ARCHIVES if extract is None else extract, inspection_pending=True)
            if job.extract and secret:
                save_job_password(job.id, secret)
            if source_key:
                save_job_download_key(job.id, source_key)
            self.jobs[job.id] = job
            try:
                self.save()
            except Exception:
                self.jobs.pop(job.id, None)
                delete_job_secrets(job.id)
                raise
            self.condition.notify_all()
            return job

    def _resolve_queued_link(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            source = job.source
        download_key = load_job_download_key(job_id)
        inspected = inspect_gigafile(source, download_key) if download_key else inspect_gigafile(source)
        files = inspected.get("files") if inspected.get("batch") else [inspected]
        with self.condition:
            if self.stopping or SHUTDOWN_EVENT.is_set() or self.jobs.get(job_id) is not job or job.status != "inspecting":
                return
            # Replace the placeholder and persist children in one state-file write.
            saved_jobs, saved_private = dict(self.jobs), dict(self.private_downloads)
            try:
                self.start_many(
                    files, job.target, job.extract, load_job_password(job_id),
                    download_key=download_key, replace_id=job_id,
                )
            except Exception:
                self.jobs, self.private_downloads = saved_jobs, saved_private
                raise


    def start_many(self, files: list[dict], target: str = "", extract: bool | None = None, password: str = "", *, download_key: str = "", replace_id: str | None = None) -> list[Job]:
        if not files:
            raise ValueError("다운로드할 파일이 없습니다.")
        if extract is not None and not isinstance(extract, bool):
            raise ValueError("압축 해제 선택값이 올바르지 않습니다.")
        should_extract = AUTO_EXTRACT_ARCHIVES if extract is None else extract
        normalized_password = _validate_job_password(password)
        normalized_download_key = _validate_gigafile_download_key(download_key)
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
                if provider in {"buzzheavier", "akirabox", "vikingfile", "sendnow"}:
                    save_job_download_url(job.id, str(file.get("download_url", "")))
                if should_extract and normalized_password:
                    save_job_password(job.id, normalized_password)
                if provider == "gigafile" and normalized_download_key:
                    save_job_download_key(job.id, normalized_download_key)
                jobs.append(job)
            replaced = self.jobs.pop(replace_id, None) if replace_id else None
            try:
                self.save()
            except Exception:
                for added in jobs:
                    self.jobs.pop(added.id, None)
                    self.private_downloads.pop(added.id, None)
                if replaced:
                    self.jobs[replaced.id] = replaced
                raise
            if replaced:
                try:
                    delete_job_secrets(replaced.id)
                except OSError:
                    LOGGER.warning("Could not remove retired inspection secret")
            self.condition.notify_all()
        return jobs

    def _provider_for_job(self, job: Job) -> str:
        private = self.private_downloads.get(job.id, {})
        return private.get("provider") or provider_for_url(job.source)

    def _provider_limit(self) -> int:
        return SAME_PROVIDER_LIMIT if ALLOW_SAME_PROVIDER_PARALLEL else 1

    def _can_start(self, job: Job) -> bool:
        if getattr(self, "stopping", False) or any(job.id in ids for ids in self.running_providers.values()):
            return False
        if DISK_PROTECTION and (self.postprocess_waiting or self.processing_job):
            return False
        provider = self._provider_for_job(job)
        if job.inspection_pending and any(
            self.jobs.get(running_id) and self.jobs[running_id].inspection_pending
            for ids in self.running_providers.values() for running_id in ids
        ):
            return False
        if provider == "gofile" and _gofile_cooldown_status()["active"]:
            return False
        running_total = sum(len(job_ids) for job_ids in self.running_providers.values())
        return running_total < MAX_PARALLEL_DOWNLOADS and len(self.running_providers.get(provider, set())) < self._provider_limit()

    def settings_changed(self) -> None:
        with self.condition:
            self.condition.notify_all()

    def _dispatcher(self) -> None:
        while True:
            with self.condition:
                if getattr(self, "stopping", False):
                    return
                current = time.time()
                queued = next(
                    (
                        job for job in self.jobs.values()
                        if job.status in {"queued", "inspecting"} and job.not_before <= current and self._can_start(job)
                    ),
                    None,
                )
                if queued is None:
                    delays = [
                        job.not_before - current for job in self.jobs.values()
                        if job.status == "queued" and job.not_before > current
                    ]
                    self.condition.wait(timeout=max(0.1, min([*delays, 1.0])))
                    continue
                provider = self._provider_for_job(queued)
                queued.status = "inspecting" if queued.inspection_pending else "ready"
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
            if self.jobs[job_id].inspection_pending:
                self._resolve_queued_link(job_id)
            else:
                self._run(job_id)
        except Exception as exc:
            process = self.processes.get(job_id)
            if process is not None:
                self._stop_process(process)
            with self.lock:
                job = self.jobs.get(job_id)
                if job and job.status not in {"paused", "cancelled", "stopping"}:
                    if isinstance(exc, GofileCooldownError):
                        job.status = "queued"
                        job.not_before = _gofile_cooldown_status()["until"]
                    elif isinstance(exc, GigaFileDownloadKeyRequiredError):
                        if isinstance(exc, GigaFileDownloadKeyInvalidError):
                            delete_job_download_key(job_id)
                        job.status = "download_key_required"
                        job.not_before = 0
                    else:
                        job.status = "paused" if SHUTDOWN_EVENT.is_set() else "failed"
                    job.error = (str(exc) or "다운로드 준비 중 오류가 발생했습니다.")[-400:]
                self.processes.pop(job_id, None)
                self.private_downloads.pop(job_id, None)
                self.save()
        finally:
            # Keep ownership if termination cannot be confirmed. Deletion must not
            # race a surviving transfer/extraction process even on an error path.
            process = self.processes.get(job_id)
            if process is not None:
                try:
                    self._stop_process(process)
                except Exception:
                    LOGGER.warning("Worker process stop unconfirmed; preserving job and workspace")
                    return
                self.processes.pop(job_id, None)
            with self.condition:
                running = self.running_providers.get(provider)
                if running:
                    running.discard(job_id)
                    if not running:
                        self.running_providers.pop(provider, None)
                job = self.jobs.get(job_id)
                if job and job.status == "stopping" and not job.delete_requested:
                    job.status = "paused"
                    self.save()
                self.condition.notify_all()

    def _local_size(self, prefix: str, size: int, mode: str) -> int:
        prefix_path = Path(prefix)
        total = 0
        chunk = segment_chunk(size, mode)
        def length(path):
            try:
                return path.stat().st_size if path.is_file() else 0
            except OSError:
                return 0
        for index in range(segment_count(size, mode)):
            part = prefix_path.with_name(prefix_path.name + str(index))
            start, end = index * chunk, min(size - 1, (index + 1) * chunk - 1)
            existing = length(part)
            covered = existing
            try:
                with part.with_name(part.name + '.headers').open('rb') as stream:
                    raw = stream.read(65536)
                blocks = [b for b in re.split(rb'\r?\n\r?\n', raw) if re.match(rb'HTTP/\S+ \d{3}', b)]
                block = blocks[-1] if blocks else b''
                status = int(block.split(None, 2)[1]) if block else 0
                more = length(part.with_name(part.name + '.more'))
                match = re.search(rb'(?im)^content-range:\s*bytes (\d+)-(\d+)/(\d+)\s*$', block)
                if status == 206 and match:
                    first, last, response_size = map(int, match.groups())
                    offset = first - start
                    if response_size == size and last == end and 0 <= offset <= existing and more <= end - first + 1:
                        covered = max(existing, offset + more)
                elif status == 200 and start == 0 and end == size - 1:
                    covered = max(existing, min(more, size))
            except (OSError, ValueError, IndexError):
                pass
            # The merger may have removed .more/headers since the first stat.
            total += min(end - start + 1, max(covered, length(part)))
        return total

    @staticmethod
    def _file_sha256(path: Path, cancelled=None) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
                if SHUTDOWN_EVENT.is_set() or (cancelled and cancelled()):
                    raise InterruptedError("서비스 중지로 후처리를 일시정지했습니다.")
                digest.update(block)
        return digest.hexdigest()

    def _assemble_artifact(self, job: Job, workspace: Path, private: dict[str, str]) -> tuple[Path, str]:
        cancelled = lambda: job.status in {"paused", "cancelled", "stopping"}
        artifact = workspace / job.name
        if artifact.is_file() and job.sha256:
            return artifact, job.sha256
        count = segment_count(job.size, "single" if private.get("download_mode") == "gigafile_zip" else private.get("transfer_mode") or job.transfer_mode or "segmented")
        parts = [workspace / f".{job.id}.segment.{index}" for index in range(count)]
        if any(not part.is_file() for part in parts):
            raise ValueError("다운로드 조각이 모두 준비되지 않았습니다.")
        assembling = workspace / f".{job.id}.assembling"
        if count == 1:
            assembling = parts[0]
        else:
            with assembling.open("wb") as output:
                for part in parts:
                    with part.open("rb") as source:
                        _copy_checked(source, output, length=4 * 1024 * 1024, cancelled=cancelled)
        actual_size = assembling.stat().st_size
        size_valid = actual_size >= job.size if private.get("download_mode") == "gigafile_zip" else actual_size == job.size
        if not size_valid:
            assembling.unlink(missing_ok=True)
            raise ValueError("결합된 파일 크기가 예상값과 일치하지 않습니다.")
        digest = self._file_sha256(assembling, cancelled=cancelled)
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
            if private.get("provider") not in {"gigafile", "buzzheavier", "akirabox", "vikingfile", "sendnow"}:
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
            if job.status in {"paused", "cancelled", "stopping"}:
                self.postprocess_waiting.remove(job_id)
                return False
            job.status = "waiting_processing"
            job.error = ""
            self.save()
            self.condition.notify_all()
            while True:
                if job.status in {"paused", "cancelled", "stopping"} or SHUTDOWN_EVENT.is_set():
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

    def _track_processing_process(self, job_id: str, process) -> None:
        with self.condition:
            if process is None:
                self.processes.pop(job_id, None)
            else:
                self.processes[job_id] = process
            self.condition.notify_all()

    def _postprocess(self, job_id: str, workspace: Path, artifact: Path, target_dir: str, verify_artifact: bool = False) -> None:
        if not self._enter_postprocessing(job_id):
            return
        try:
            with self.lock:
                job = self.jobs[job_id]
                private = self.private_downloads.get(job_id, {})
                if job.status in {"paused", "cancelled", "stopping"} or SHUTDOWN_EVENT.is_set():
                    return
                job.status = "verifying"
                self.save()
            if not artifact.is_file():
                artifact, digest = self._assemble_artifact(job, workspace, private)
                with self.lock:
                    job.sha256 = digest
                    self.save()
            elif verify_artifact and job.sha256 and self._file_sha256(artifact, cancelled=lambda: job.status in {"paused", "cancelled", "stopping"}) != job.sha256:
                with self.lock:
                    artifact.unlink(missing_ok=True)
                    shutil.rmtree(workspace / "extracted", ignore_errors=True)
                    job.sha256 = ""
                    raise ValueError("임시 완성 파일이 손상되어 삭제했습니다. 작업을 재개하면 처음부터 다시 다운로드합니다.")
            artifact = self._apply_response_filename(job, workspace, artifact, private)
            # The provider key is no longer needed once the complete artifact is
            # verified locally. Do not retain it during extraction or publishing.
            delete_job_download_key(job_id)
            with self.lock:
                if job.status in {"paused", "cancelled", "stopping"}:
                    return
                job.status = "extracting" if job.extract and archive_kind(job.name) else "publishing"
                self.save()
            try:
                output, extracted = promote_download(
                    artifact, target_dir, job.extract, load_job_password(job_id),
                    cancelled=lambda: job.delete_requested or job.status in {"paused", "cancelled", "stopping"},
                    publication_lock=self.lock,
                    process_callback=lambda process: self._track_processing_process(job_id, process),
                )
            except PasswordRequiredError as exc:
                delete_job_password(job_id)
                with self.lock:
                    job = self.jobs[job_id]
                    job.status = "stopping" if job.delete_requested else "password_required"
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
                job.status = "stopping" if job.delete_requested else "completed"
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
            if job.status in {"paused", "cancelled", "stopping"}:
                return
            job.status = "downloading"
            self.save()
        private = self.private_downloads.get(job_id, {})
        private.pop("rate_limited", None)
        target_dir = private.get("target") or job.target or NAS_TARGET
        safe_name = job.name
        workspace = job_workspace(target_dir, job.id)
        workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
        migrate_legacy_workspace(target_dir, safe_name, job.id, workspace)
        safe_name = _clean_download_name(safe_name)
        if safe_name != job.name:
            # Enumerate instead of stat-ing a too-long legacy name.
            for entry in workspace.iterdir():
                if entry.name == job.name:
                    destination = workspace / safe_name
                    if destination.exists():
                        raise ValueError("파일명 변경 대상이 이미 존재합니다. 기존 파일을 보존했습니다.")
                    entry.rename(destination)
            with self.lock:
                job.name = safe_name
                self.save()
        artifact = workspace / safe_name
        if artifact.is_file() and job.sha256:
            self._postprocess(job_id, workspace, artifact, target_dir, verify_artifact=True)
            return
        parsed = urlparse(job.source)
        provider = private.get("provider") or provider_for_url(job.source)
        if provider == "gigafile" and not private.get("download_url"):
            download_key = load_job_download_key(job.id)
            refreshed = inspect_gigafile(job.source, download_key) if download_key else inspect_gigafile(job.source)
            name_changed = refreshed["name"] != job.name
            if int(refreshed["size"]) != job.size or (
                name_changed and not is_gigafile_fallback_name(job.name, job.source)
            ):
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
        if provider in {"akirabox", "vikingfile", "sendnow"}:
            signed = private.get("download_url") or load_job_download_url(job.id)
            validator = {"akirabox": _validate_akira_url, "vikingfile": _validate_viking_url, "sendnow": _validate_sendnow_url}[provider]
            validator(job.source, direct=False)
            _validate_handoff_transfer_url(signed, provider)
            private.update(provider=provider, download_url=signed, target=target_dir)
            if provider == "sendnow":
                resolve_host = (urlparse(signed).hostname or "").lower()
                resolved = _resolve_public_addresses(resolve_host)
                if not resolved:
                    raise ValueError("Send.now가 전달한 다운로드 서버를 안전하게 확인하지 못했습니다.")
                private.update(resolve_host=resolve_host, resolve_address=resolved[0])
        # Persist layout so a later settings change cannot reinterpret fragments.
        if not job.transfer_mode:
            has_legacy_parts = any(workspace.glob(f".{job.id}.segment.*"))
            job.transfer_mode = "single" if provider in {"akirabox", "vikingfile", "sendnow"} else ("segmented" if has_legacy_parts else initial_transfer_mode(provider, DOWNLOAD_MODE))
            self.save()
        download_mode = job.transfer_mode
        private["transfer_mode"] = download_mode
        self.private_downloads[job_id] = private
        workspace_dir = str(workspace)
        prefix = f"{workspace_dir}/.{job.id}.segment."
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
        elif provider in {"buzzheavier", "akirabox", "vikingfile", "sendnow"}:
            script = self._download_script_direct(
                private.get("download_url", ""), job.source, safe_name, job.id, job.size, workspace_dir,
                mode=download_mode, capture_headers=True, transient_retries=3 if provider == "akirabox" else 0,
                resolve_host=private.get("resolve_host", ""), resolve_address=private.get("resolve_address", ""),
            )
        else:
            file_id = parsed.path.strip("/")
            host = parsed.hostname or ""
            script = self._download_script(
                host, file_id, safe_name, job.id, job.size, workspace_dir,
                mode=download_mode, download_url=private.get("download_url", ""),
            )
        command = ["sh", "-s"]
        with self.condition:
            if SHUTDOWN_EVENT.is_set() or job.status in {"paused", "cancelled", "stopping"}:
                return
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True,
            )
            self.processes[job_id] = process
            self.condition.notify_all()
        assert process.stdin is not None
        process.stdin.write(script)
        process.stdin.close()

        while process.poll() is None:
            time.sleep(2.5)
            if provider == "gofile" and (workspace / ".rate-limit").exists():
                with self.condition:
                    self._defer_gofile(job, workspace, active=True)
            try:
                current = self._local_size(prefix, job.size, "single" if private.get("download_mode") == "gigafile_zip" else download_mode)
            except Exception:
                current = 0
            with self.lock:
                if self.jobs[job_id].status in {"paused", "cancelled", "stopping"}:
                    self._stop_process(process)
                    break
                self.jobs[job_id].downloaded = min(job.size, current)
                if download_mode == "segmented" and current >= job.size:
                    self.jobs[job_id].status = "verifying"
                self.save()

        stdout = process.stdout.read() if process.stdout else ""
        stderr = process.stderr.read() if process.stderr else ""
        process.wait()
        self._recover_fragments(job, workspace, download_mode)
        with self.lock:
            current_job = self.jobs[job_id]
            if current_job.status in {"paused", "cancelled", "stopping"}:
                self.processes.pop(job_id, None)
                self.private_downloads.pop(job_id, None)
                self.save()
                return
            if process.returncode != 0:
                current_job.status = "failed"
                if provider == "gofile" and ((workspace / ".rate-limit").exists() or private.get("rate_limited")):
                    self._defer_gofile(job, workspace)
                elif provider in {"akirabox", "vikingfile", "sendnow"}:
                    current_job.error = handoff_transfer_error(stderr)
                elif provider == "buzzheavier" and re.search(r"(?:error:\s*)?(?:401|403|404)\b", stderr, re.I):
                    current_job.error = "Buzzheavier 직접 링크가 만료됐거나 사용할 수 없습니다. Copy download link를 다시 받아 새 작업으로 등록해 주세요."
                elif re.search(r"maximum \(0\) redirects|too many redirects", stderr, re.I):
                    current_job.error = "다운로드 서버가 다른 주소로 이동을 요청해 보안을 위해 중단했습니다. 링크를 다시 확인해 주세요."
                elif re.search(r"operation timed out|speed below|timed out", stderr, re.I):
                    current_job.error = "다운로드 서버 응답이 일정 시간 멈춰 작업을 중단했습니다. 다시 시작하면 이어받기를 시도합니다."
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

    def _recover_fragments(self, job: Job, workspace: Path, mode: str) -> None:
        chunk = segment_chunk(job.size, mode)
        for i in range(segment_count(job.size, mode)):
            part = workspace / f".{job.id}.segment.{i}"
            if part.with_name(part.name + ".headers").exists():
                commit_fragment(part, i * chunk, min(job.size - 1, (i + 1) * chunk - 1), job.size)
        for name in (".cookies", ".page", ".curl.conf"):
            (workspace / name).unlink(missing_ok=True)

    def _defer_gofile(self, job: Job, workspace: Path, active: bool = False) -> None:
        status = _gofile_cooldown_status()
        if not status["active"]:
            seconds = GOFILE_RATE_LIMIT_COOLDOWN_SECONDS
            try:
                raw = json.loads((workspace / ".rate-limit").read_text(encoding="utf-8")).get("retry_after", "")
                seconds = float(raw) if str(raw).isdigit() else parsedate_to_datetime(raw).timestamp() - time.time()
            except (OSError, ValueError, TypeError, OverflowError):
                pass
            _trip_gofile_cooldown(max(5, min(seconds, GOFILE_MAX_COOLDOWN_SECONDS)), "GoFile 요청 제한(HTTP 429)이 감지되었습니다.")
        until = _gofile_cooldown_status()["until"]
        (workspace / ".rate-limit").unlink(missing_ok=True)
        for other in self.jobs.values():
            if self._provider_for_job(other) != "gofile":
                continue
            if other.status in {"queued", "ready", "downloading"}:
                other.not_before = until
                self.private_downloads.setdefault(other.id, {})["rate_limited"] = "1"
                process = self.processes.get(other.id)
                if process:
                    self._terminate(process)
        if not active:
            job.status = "queued"
            job.not_before = until
            job.error = "GoFile 요청 제한으로 잠시 대기합니다."

    def shutdown(self, timeout: float = 10) -> None:
        SHUTDOWN_EVENT.set()
        with self.condition:
            self.stopping = True
            for job in self.jobs.values():
                if job.status in {"inspecting", "ready", "downloading", "waiting_processing", "verifying"}:
                    job.status = "stopping"
            processes = list(self.processes.values())
            self.condition.notify_all()
        for process in processes:
            self._terminate(process)
        deadline = time.monotonic() + timeout
        with self.condition:
            while self.running_providers and time.monotonic() < deadline:
                self.condition.wait(timeout=0.1)
            remaining = list(self.processes.values())
        for process in remaining:
            self._stop_process(process)
        with self.condition:
            for job in self.jobs.values():
                if job.status in {"stopping", "extracting", "publishing"}:
                    job.status = "paused"
            self.save()

    @staticmethod
    def _transfer_loop(prefix: str, total: int, mode: str, curl: str, max_parallel: int = 8, transient_retries: int = 0) -> str:
        count = segment_count(total, mode)
        chunk = segment_chunk(total, mode)
        merger = f"{shlex.quote(sys.executable)} {shlex.quote(str(ROOT / 'transfer_parts.py'))}"
        return f'''TOTAL={total}
COUNT={count}
CHUNK={chunk}
PREFIX={shlex.quote(prefix)}
pids=""
i=0
while [ "$i" -lt "$COUNT" ]; do
  start=$(( i * CHUNK )); end=$(( start + CHUNK - 1 ))
  [ "$end" -lt "$TOTAL" ] || end=$(( TOTAL - 1 ))
  part="$PREFIX.$i"
  (
    expected=$(( end - start + 1 ))
    if [ -f "$part.more" ]; then
      {merger} "$part" "$start" "$end" "$TOTAL" || true
    fi
    existing=0; [ ! -f "$part" ] || existing=$(wc -c < "$part" | tr -d ' ')
    [ "$existing" -le "$expected" ] || {{ rm -f "$part"; existing=0; }}
    attempt=0
    while [ "$existing" -lt "$expected" ]; do
      from=$(( start + existing )); more="$part.more"
      rc=0
      {curl} --retry 0 -r "$from-$end" --dump-header "$part.headers" -o "$more" || rc=$?
      merged=0
      {merger} "$part" "$start" "$end" "$TOTAL" || merged=$?
      if [ "$rc" -eq 0 ] && [ "$merged" -eq 0 ]; then break; fi
      printf 'NASDROP_TRANSFER curl=%s merge=%s attempt=%s\\n' "$rc" "$merged" "$attempt" >&2
      # Retry only validated partial responses after transient transport failures.
      # Never retry HTTP rejection, redirect, invalid range or local write failure.
      [ "$merged" -eq 0 ] && [ "$attempt" -lt {transient_retries} ] || exit 1
      case "$rc" in 18|28|52|56|92) ;; *) exit 1 ;; esac
      existing=$(wc -c < "$part" | tr -d ' ')
      [ "$existing" -lt "$expected" ] || break
      attempt=$(( attempt + 1 ))
      sleep $(( attempt * 10 ))
    done
    actual=$(wc -c < "$part" | tr -d ' ')
    [ "$actual" -eq "$expected" ]
  ) &
  pids="$pids $!"
  i=$(( i + 1 ))
  if [ $(( i % {max_parallel} )) -eq 0 ]; then
    failed=0
    for child in $pids; do wait "$child" || failed=1; done
    [ "$failed" -eq 0 ] || exit 1
    pids=""
  fi
done
failed=0
for child in $pids; do wait "$child" || failed=1; done
[ "$failed" -eq 0 ] || exit 1
printf 'SEGMENTS_READY=%s\\n' "$COUNT"
'''

    def _download_script(self, host: str, file_id: str, name: str, job_id: str, total: int, target_dir: str, mode: str = "segmented", download_url: str = "") -> str:
        page = f"https://{host}/{file_id}"
        download = download_url or f"https://{host}/download.php?file={file_id}"
        parsed_download = urlparse(download)
        query = parse_qs(parsed_download.query, keep_blank_values=True)
        if (
            parsed_download.scheme != "https" or (parsed_download.hostname or "").lower() != host.lower()
            or parsed_download.path != "/download.php" or query.get("file") != [file_id]
            or any(key not in {"file", "dlkey"} for key in query)
        ):
            raise ValueError("GigaFile 다운로드 주소가 올바르지 않습니다.")
        prefix = f"{target_dir}/.{job_id}.segment"
        cookie = f"{target_dir}/.cookies"
        page_copy = f"{target_dir}/.page"
        curl_config = f"{target_dir}/.curl.conf"
        config_body = "\n".join((
            f'url = "{_curl_config_value(download)}"',
            f'referer = "{_curl_config_value(page)}"',
            'proto = "=https"', 'proto-redir = "=https"',
        ))
        curl = f'curl --config "$CURL_CONFIG" {CURL_HTTPS_ONLY} {CURL_STALL_GUARD} {CURL_NO_REDIRECTS} --fail --silent --show-error -b "$COOKIE"'
        setup = f'''#!/bin/sh
set -eu
umask 077
COOKIE={shlex.quote(cookie)}
PAGE_COPY={shlex.quote(page_copy)}
CURL_CONFIG={shlex.quote(curl_config)}
cat > "$CURL_CONFIG" <<'NASDROP_CURL_CONFIG'
{config_body}
NASDROP_CURL_CONFIG
cleanup() {{ rm -f "$COOKIE" "$PAGE_COPY" "$CURL_CONFIG"; }}
trap cleanup EXIT
trap 'exit 143' HUP INT TERM
curl {CURL_HTTPS_ONLY} {CURL_PAGE_TIMEOUT} {CURL_NO_REDIRECTS} --fail --silent --show-error -c "$COOKIE" {shlex.quote(page)} -o "$PAGE_COPY"
'''
        # Names are probed during inspection. The actual GET headers are the
        # authoritative fallback, captured by transfer_parts in the workspace.
        return setup + self._transfer_loop(prefix, total, mode, curl)

    def _download_script_gofile(self, download: str, token: str, page: str, name: str, job_id: str, total: int, target_dir: str, mode: str = "segmented2") -> str:
        if not download.startswith("https://") or not token:
            raise ValueError("Gofile 다운로드 인증 정보가 없습니다.")
        return self._download_script_direct(download, page, name, job_id, total, target_dir, cookie=f"accountToken={token}", mode=mode, max_parallel=2)

    def _download_script_direct(self, download: str, page: str, name: str, job_id: str, total: int, target_dir: str, cookie: str = "", expected_sha256: str = "", mode: str = "segmented", capture_headers: bool = False, max_parallel: int = 8, transient_retries: int = 0, resolve_host: str = "", resolve_address: str = "") -> str:
        if not download.startswith("https://"):
            raise ValueError("직접 다운로드 주소가 올바르지 않습니다.")
        config_lines = [
            f'url = "{_curl_config_value(download)}"',
            f'referer = "{_curl_config_value(page)}"',
            'proto = "=https"', 'proto-redir = "=https"',
        ]
        if cookie:
            config_lines.append(f'header = "{_curl_config_value("Cookie: " + cookie)}"')
        if resolve_host or resolve_address:
            parsed_host = (urlparse(download).hostname or "").lower()
            if parsed_host != resolve_host or not _resolve_public_addresses(resolve_address):
                raise ValueError("고정할 다운로드 서버 주소가 올바르지 않습니다.")
            pinned = f"[{resolve_address}]" if ":" in resolve_address else resolve_address
            config_lines.append(f'resolve = "{_curl_config_value(resolve_host + ":443:" + pinned)}"')
        config_body = "\n".join(config_lines)
        setup = f'''#!/bin/sh
set -eu
umask 077
CURL_CONFIG={shlex.quote(f"{target_dir}/.curl.conf")}
cat > "$CURL_CONFIG" <<'NASDROP_CURL_CONFIG'
{config_body}
NASDROP_CURL_CONFIG
cleanup() {{ rm -f "$CURL_CONFIG"; }}
trap cleanup EXIT
trap 'exit 143' HUP INT TERM
'''
        curl = f'curl --config "$CURL_CONFIG" {CURL_STALL_GUARD} {CURL_NO_REDIRECTS} --fail --silent --show-error'
        return setup + self._transfer_loop(f"{target_dir}/.{job_id}.segment", total, mode, curl, max_parallel=max_parallel, transient_retries=transient_retries)


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
        part = f"{target_dir}/.{job_id}.segment.0"
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
curl {CURL_HTTPS_ONLY} {CURL_PAGE_TIMEOUT} {CURL_NO_REDIRECTS} --fail --silent --show-error -c "$COOKIE" {shlex.quote(page)} -o "$PAGE_COPY"
actual=0; [ -f "$PART" ] && actual=$(wc -c < "$PART" | tr -d ' ')
if [ "$actual" -lt "$TOTAL" ]; then
  rm -f "$PART"
  curl {CURL_HTTPS_ONLY} {CURL_STALL_GUARD} {CURL_NO_REDIRECTS} --fail --silent --show-error --retry 8 --retry-delay 5 -b "$COOKIE" -e {shlex.quote(page)} -o "$PART" {shlex.quote(download)}
fi
actual=$(wc -c < "$PART" | tr -d ' '); [ "$actual" -ge "$TOTAL" ]
trap - EXIT HUP INT TERM
cleanup
printf 'SEGMENTS_READY=1\\n'
"""

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError, AttributeError):
            if process.poll() is None:
                process.terminate()

    @classmethod
    def _stop_process(cls, process: subprocess.Popen[str]) -> None:
        cls._terminate(process)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        # The shell may have exited while one of its curl children still lives.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError, AttributeError):
            if process.poll() is None:
                process.kill()
        process.wait(timeout=2)

    def pause(self, job_id: str) -> None:
        with self.condition:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            job = self.jobs[job_id]
            if job.status not in {"inspecting", "queued", "ready", "downloading", "waiting_processing", "verifying"}:
                raise ValueError("중지할 수 있는 작업이 아닙니다.")
            running = any(job_id in ids for ids in self.running_providers.values())
            job.status = "stopping" if running or self.processing_job == job_id else "paused"
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
            if job.delete_requested or any(job_id in ids for ids in self.running_providers.values()) or job.status not in {"paused", "failed", "cancelled"}:
                raise ValueError("다시 시작할 수 있는 작업이 아닙니다.")
            job.status = "inspecting" if job.inspection_pending else "queued"
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
            if job.delete_requested or job.status != "password_required":
                raise ValueError("현재 암호 입력이 필요한 작업이 아닙니다.")
            save_job_password(job_id, normalized)
            job.status = "queued"
            job.error = ""
            job.not_before = 0
            self.save()
            self.condition.notify_all()

    def submit_download_key(self, job_id: str, download_key: object) -> None:
        normalized = _validate_gigafile_download_key(download_key)
        if not normalized:
            raise ValueError("GigaFile 다운로드 키를 입력해 주세요.")
        with self.condition:
            job = self.jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            if job.delete_requested or job.status != "download_key_required" or self._provider_for_job(job) != "gigafile":
                raise ValueError("현재 GigaFile 다운로드 키 입력이 필요한 작업이 아닙니다.")
            save_job_download_key(job_id, normalized)
            job.status = "inspecting" if job.inspection_pending else "queued"
            job.error = ""
            job.not_before = 0
            self.save()
            self.condition.notify_all()

    def update_processing(self, job_id: str, extract: object, password: object = None) -> dict:
        if not isinstance(extract, bool):
            raise ValueError("압축 해제 선택값이 올바르지 않습니다.")
        if password is not None and not isinstance(password, str):
            raise ValueError("압축 암호 형식이 올바르지 않습니다.")
        normalized = _validate_job_password(password)
        with self.condition:
            job = self.jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            allowed = {"queued", "ready", "inspecting", "paused", "downloading", "password_required"}
            running = any(job_id in ids for ids in self.running_providers.values())
            if self.stopping or job.delete_requested or job.status not in allowed or self.processing_job == job_id or (job.status in {"paused", "password_required"} and running):
                raise ValueError("현재 상태에서는 압축 해제 설정을 변경할 수 없습니다. 작업을 일시정지한 뒤 다시 시도해 주세요.")
            previous_password = load_job_password(job_id)
            if job.status == "password_required":
                if extract and not (normalized or previous_password):
                    raise ValueError("압축 암호를 입력해 주세요.")
                if not extract:
                    artifact = job_workspace(job.target or NAS_TARGET, job.id) / _clean_download_name(job.name)
                    if not job.sha256 or not artifact.is_file():
                        raise ValueError("보존된 원본 파일이 없어 압축 해제를 건너뛸 수 없습니다.")
            previous = (job.extract, job.status, job.error, job.not_before)
            try:
                if not extract:
                    delete_job_password(job_id)
                elif normalized:
                    save_job_password(job_id, normalized)
                job.extract = extract
                if job.status == "password_required":
                    job.status, job.error, job.not_before = "queued", "", 0
                self.save()
            except Exception:
                job.extract, job.status, job.error, job.not_before = previous
                save_job_password(job_id, previous_password)
                raise
            self.condition.notify_all()
            return asdict(job)

    def request_delete(self, job_ids: list[str]) -> dict:
        """Opt-in stop-and-delete; never remove data while a worker owns the job."""
        with self.condition:
            if self.stopping:
                raise ValueError("서비스가 종료 중입니다.")
            ids = list(dict.fromkeys(job_ids))
            for job_id in ids:
                if job_id not in self.jobs:
                    raise KeyError(job_id)
            busy = any(self.jobs[i].delete_requested or i in self.processes or self.processing_job == i
                       or any(i in running for running in self.running_providers.values()) for i in ids)
            if not busy:
                previous = {i: self.jobs[i].status for i in ids}
                for i in ids:
                    if self.jobs[i].status != "completed":
                        self.jobs[i].status = "paused"
                try:
                    return {"ok": True, "deleted": self.delete(ids), "pending": []}
                except Exception:
                    for i, status in previous.items():
                        if i in self.jobs:
                            self.jobs[i].status = status
                    raise
            pending, scheduled, previous = [], [], {}
            for job_id in ids:
                job = self.jobs[job_id]
                if job.delete_requested:
                    pending.append(job_id)
                    continue
                previous[job_id] = (job.status, job.error)
                job.delete_requested = True
                job.status, job.error = "stopping", ""
                pending.append(job_id)
                scheduled.append(job_id)
            try:
                self.save()
            except Exception:
                for job_id in scheduled:
                    self.jobs[job_id].delete_requested = False
                    self.jobs[job_id].status, self.jobs[job_id].error = previous[job_id]
                self.condition.notify_all()
                raise
            for job_id in scheduled:
                threading.Thread(target=self._finish_delete, args=(job_id,),
                                 name=f"nasdrop-delete-{job_id}", daemon=True).start()
            self.condition.notify_all()
            return {"ok": True, "deleted": 0, "pending": pending}

    def _finish_delete(self, job_id: str) -> None:
        with self.condition:
            if self.stopping or SHUTDOWN_EVENT.is_set():
                return
            while any(job_id in ids for ids in self.running_providers.values()) or self.processing_job == job_id:
                if self.stopping or SHUTDOWN_EVENT.is_set():
                    return  # Restart preserves the record and requires a fresh request.
                self.condition.wait(timeout=0.25)
            job = self.jobs.get(job_id)
            if not job or not job.delete_requested:
                return
            try:
                process = self.processes.get(job_id)
                if process is not None:
                    self._stop_process(process)
                    self.processes.pop(job_id, None)
                job.status = "paused"
                self.delete([job_id], _pending=True)
            except Exception:
                job.delete_requested = False
                job.status = "failed"
                job.error = "임시 다운로드 파일을 삭제하지 못해 작업 기록을 보존했습니다. 폴더 권한을 확인한 뒤 다시 삭제해 주세요."
                self.save()
            finally:
                self.condition.notify_all()

    def delete(self, job_ids: list[str], *, _pending: bool = False) -> int:
        with self.lock:
            job_ids = list(dict.fromkeys(job_ids))
            for job_id in job_ids:
                job = self.jobs.get(job_id)
                if not job:
                    raise KeyError(job_id)
                if job.delete_requested and not _pending:
                    raise ValueError("삭제를 위해 작업을 중지 중입니다.")
                if job_id in getattr(self, "processes", {}) or getattr(self, "processing_job", None) == job_id:
                    raise ValueError("실행 중인 작업은 먼저 멈춰 주세요.")
                if job.status in {"inspecting", "queued", "ready", "downloading", "waiting_processing", "verifying", "extracting", "publishing", "stopping"} or any(job_id in ids for ids in self.running_providers.values()):
                    raise ValueError("실행 중인 작업은 먼저 멈춰 주세요.")
            # Delete only the exact private workspace, never published output or symlink targets.
            # Keep every record if any workspace cannot be cleaned up.
            for job_id in job_ids:
                job = self.jobs[job_id]
                try:
                    target = Path(job.target or NAS_TARGET).resolve()
                    expected = target / ".nasdrop-tmp" / job.id
                    if expected.parent.is_symlink() or expected.is_symlink() or job_workspace(str(target), job.id) != expected:
                        raise ValueError("Unsafe workspace")
                    if expected.exists():
                        shutil.rmtree(expected)
                    if expected.exists():
                        raise OSError("Workspace remains")
                except (OSError, ValueError):
                    raise ValueError("임시 다운로드 파일을 삭제하지 못해 작업 기록을 보존했습니다. 폴더 권한을 확인한 뒤 다시 삭제해 주세요.") from None
            for job_id in job_ids:
                delete_job_secrets(job_id)
            saved_jobs = self.jobs.copy()
            saved_private = self.private_downloads.copy()
            for job_id in job_ids:
                self.jobs.pop(job_id, None)
                self.private_downloads.pop(job_id, None)
            try:
                self.save()
            except Exception:
                self.jobs, self.private_downloads = saved_jobs, saved_private
                raise
            return len(job_ids)

    def clear_completed(self) -> int:
        with self.lock:
            completed = [job_id for job_id, job in self.jobs.items() if job.status == "completed" and not job.delete_requested
                         and not any(job_id in ids for ids in self.running_providers.values())]
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
    return fit_download_name(re.sub(r"[\\/\x00-\x1f:]", "_", name))


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


def _validate_akira_url(value: str, *, direct: bool) -> str:
    error = "AkiraBox 주소가 올바르지 않거나 만료됐습니다. 브라우저에서 다운로드 버튼을 다시 준비해 주세요."
    if not isinstance(value, str) or not value or len(value) > 16384 or any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError(error)
    try:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443} or parsed.fragment:
            raise ValueError(error)
        if direct:
            if parsed.hostname != "akirabox.com" or not re.fullmatch(r"/download/[^/]+/[^/]+", parsed.path):
                raise ValueError(error)
            query = parse_qs(parsed.query, keep_blank_values=True)
            if set(query) != {"expiration", "signature"} or any(len(v) != 1 for v in query.values()):
                raise ValueError(error)
            if not re.fullmatch(r"[0-9]{10,11}", query["expiration"][0]) or int(query["expiration"][0]) <= time.time():
                raise ValueError(error)
            if not re.fullmatch(r"[a-fA-F0-9]{32,128}", query["signature"][0]):
                raise ValueError(error)
        elif parsed.hostname not in {"akirabox.to", "akirabox.com"} or not re.fullmatch(r"/[a-zA-Z0-9]+/file", parsed.path) or parsed.query:
            raise ValueError(error)
    except (ValueError, KeyError):
        raise ValueError(error) from None
    return value


def _validate_viking_url(value: str, *, direct: bool) -> str:
    error = "VikingFile 주소가 올바르지 않습니다. 브라우저에서 다운로드 버튼을 다시 준비해 주세요."
    if not isinstance(value, str) or not value or len(value) > 16384 or any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError(error)
    try:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443} or parsed.query or parsed.fragment:
            raise ValueError(error)
        if direct:
            if parsed.hostname != "vikingfile.com" or not re.fullmatch(r"/d/[a-zA-Z0-9_-]+/[^/]+", parsed.path):
                raise ValueError(error)
        elif parsed.hostname not in {"vik1ngfile.site", "vikingfile.com"} or not re.fullmatch(r"/f/[a-zA-Z0-9]+", parsed.path):
            raise ValueError(error)
    except ValueError:
        raise ValueError(error) from None
    return value


SENDNOW_SHARE_HOSTS = {"send.now", "www.send.now"}
SENDNOW_PROVIDER_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*send\.now\Z")


def _validate_sendnow_url(value: str, *, direct: bool) -> str:
    error = "Send.now 주소가 올바르지 않습니다. 브라우저에서 인증을 마치고 마지막 다운로드 링크를 다시 눌러 주세요."
    if not isinstance(value, str) or not value or len(value) > 16384 or any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError(error)
    try:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443} or parsed.fragment:
            raise ValueError(error)
        if direct:
            return _validate_handoff_transfer_url(value, "sendnow")
        if parsed.hostname not in SENDNOW_SHARE_HOSTS or parsed.query or not re.fullmatch(r"/[a-zA-Z0-9_-]{6,64}", parsed.path.rstrip("/")):
            raise ValueError(error)
    except ValueError:
        raise ValueError(error) from None
    return value.rstrip("/")


def _resolve_public_addresses(host: str) -> tuple[str, ...]:
    """Resolve once and return only an all-public address set suitable for pinning."""
    candidate = host.rstrip(".").lower()
    if not candidate or candidate == "localhost" or candidate.endswith(".local"):
        return ()
    try:
        literal = ipaddress.ip_address(candidate)
        return (str(literal),) if literal.is_global else ()
    except ValueError:
        pass
    try:
        answers = socket.getaddrinfo(candidate, 443, type=socket.SOCK_STREAM)
        addresses = {ipaddress.ip_address(answer[4][0].split("%", 1)[0]) for answer in answers}
    except (OSError, ValueError):
        return ()
    if not addresses or not all(address.is_global for address in addresses):
        return ()
    return tuple(str(address) for address in sorted(addresses, key=lambda item: (item.version, int(item))))


def _public_download_host(host: str) -> bool:
    return bool(_resolve_public_addresses(host))


def handoff_transfer_error(stderr: str) -> str:
    """Translate internal transfer status into safe, plain-language errors."""
    markers = re.findall(r"NASDROP_TRANSFER curl=(\d+) merge=(\d+) attempt=(\d+)", stderr)
    if not markers:
        return "다운로드가 중단됐습니다. 받은 데이터는 보존됩니다."
    rc, merged, _attempt = map(int, markers[-1])
    if rc in {18, 28, 52, 56, 92} and merged == 0:
        return "일시적인 연결 끊김 또는 응답 지연으로 중단됐습니다. 재개하면 검증된 데이터부터 이어받습니다."
    if rc == 22:
        return "다운로드 서버가 요청을 거부했습니다. 링크 만료 또는 요청 제한 여부를 확인해 주세요."
    if rc == 47:
        return "다운로드 서버가 주소 이동을 요청해 중단했습니다. 브라우저에서 새 링크를 등록해 주세요."
    if rc == 23:
        return "NAS 파일 쓰기에 실패했습니다. 저장 공간과 폴더 권한을 확인해 주세요."
    if merged:
        return "이어받기 응답을 검증하거나 저장하지 못했습니다. 기존에 검증된 데이터는 보존됩니다."
    return "다운로드가 중단됐습니다. 받은 데이터는 보존됩니다."


class HandoffError(ValueError):
    """Constructed exclusively with fixed, non-secret user-facing messages."""


HANDOFF_FILE_HOSTS = {
    "akirabox": {"us1.akirabox.com"},
    "vikingfile": {"vikingfile.04b3d96d52475741e6b10f97f0a84a16.r2.cloudflarestorage.com"},
}

# Official Viking redirects observed on both the original and west-eu-upload
# buckets. Permit one bucket label only within this pinned R2 account, not
# arbitrary Cloudflare tenants or nested/lookalike domains.
VIKING_R2_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.04b3d96d52475741e6b10f97f0a84a16\.r2\.cloudflarestorage\.com\Z")
VIKING_FILE_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.vikingfile\.com\Z")


def _validate_handoff_transfer_url(value: str, provider: str) -> str:
    error = "허용되지 않거나 만료된 다운로드 서버 주소입니다."
    if not isinstance(value, str) or not value or len(value) > 16384 or any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError(error)
    try:
        parsed = urlparse(value)
        if provider == "akirabox" and parsed.hostname == "akirabox.com":
            return _validate_akira_url(value, direct=True)
        if provider == "vikingfile" and parsed.hostname == "vikingfile.com":
            return _validate_viking_url(value, direct=True)
        if provider == "sendnow":
            host = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443} or parsed.fragment:
                raise ValueError(error)
            if not parsed.path.startswith("/") or parsed.path == "/" or not _public_download_host(host):
                raise HandoffError("Send.now가 전달한 다운로드 서버를 안전하게 확인하지 못했습니다.")
            if host in SENDNOW_SHARE_HOSTS and not parsed.query and re.fullmatch(r"/[a-zA-Z0-9_-]{6,64}/?", parsed.path):
                raise HandoffError("Send.now 공유 페이지는 직접 다운로드 주소가 아닙니다.")
            return value
        regional = provider == "vikingfile" and bool(VIKING_FILE_HOST.fullmatch(parsed.hostname or ""))
        if parsed.hostname not in HANDOFF_FILE_HOSTS.get(provider, set()) and not (provider == "vikingfile" and (regional or VIKING_R2_HOST.fullmatch(parsed.hostname or ""))):
            raise HandoffError("허용 목록에 없는 다운로드 서버입니다.")
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443} or parsed.fragment:
            raise ValueError(error)
        if not parsed.path.startswith("/") or parsed.path == "/":
            raise ValueError(error)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if any(len(values) != 1 for values in query.values()):
            raise ValueError(error)
        if provider == "akirabox":
            if set(query) != {"access"} or not query["access"][0]:
                raise ValueError(error)
        elif regional:
            if not query.get("md5", [""])[0] or not query.get("expires", [""])[0]:
                raise ValueError(error)
            if not query["expires"][0].isascii() or not query["expires"][0].isdigit():
                raise ValueError(error)
            if int(query["expires"][0]) <= time.time():
                raise HandoffError("다운로드 링크가 만료됐습니다.")
        else:
            if not query.get("X-Amz-Signature", [""])[0] or not query.get("X-Amz-Date", [""])[0] or not query.get("X-Amz-Expires", [""])[0]:
                raise ValueError(error)
            from datetime import datetime, timezone
            signed_at = datetime.strptime(query["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
            lifetime = int(query["X-Amz-Expires"][0])
            if not 0 < lifetime <= 604800:
                raise ValueError(error)
            if signed_at + lifetime <= time.time():
                raise HandoffError("다운로드 링크가 만료됐습니다.")
    except HandoffError:
        raise
    except (ValueError, KeyError, OverflowError):
        raise HandoffError(error) from None
    return value


class AkiraNoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        # Handled explicitly below, before contacting each validated destination.
        return None


class PinnedHTTPSConnection(HTTPSConnection):
    """Connect to a validated IP while retaining the URL host for TLS SNI."""

    def __init__(self, host: str, *, pinned_ip: str, **kwargs):
        self.pinned_ip = pinned_ip
        super().__init__(host, **kwargs)

    def connect(self) -> None:
        self.sock = self._create_connection(
            (self.pinned_ip, self.port), self.timeout, self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class PinnedHTTPSHandler(HTTPSHandler):
    def __init__(self, hostname: str, address: str):
        super().__init__()
        self.hostname = hostname.rstrip(".").lower()
        self.address = address

    def https_open(self, request):
        if (urlparse(request.full_url).hostname or "").rstrip(".").lower() != self.hostname:
            raise HandoffError("다운로드 서버 주소가 확인한 호스트와 달라졌습니다.")
        return self.do_open(
            lambda host, **kwargs: PinnedHTTPSConnection(host, pinned_ip=self.address, **kwargs),
            request,
        )


def _open_sendnow_pinned(url: str, method: str, headers: dict):
    host = (urlparse(url).hostname or "").lower()
    addresses = _resolve_public_addresses(host)
    if not addresses:
        raise HandoffError("Send.now가 전달한 다운로드 서버를 안전하게 확인하지 못했습니다.")
    last_error: OSError | None = None
    for address in addresses:
        # Ignore ambient proxy variables: going through a proxy would make the
        # proxy resolve the hostname again and defeat DNS pinning.
        opener = build_opener(ProxyHandler({}), AkiraNoRedirectHandler(), PinnedHTTPSHandler(host, address))
        try:
            return opener.open(Request(url, method=method, headers=headers), timeout=20)
        except HTTPError:
            raise
        except OSError as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise HandoffError("Send.now 다운로드 서버에 연결하지 못했습니다.")


def _open_handoff_response(opener, url: str, method: str, headers: dict, provider: str):
    from urllib.parse import urljoin
    visited = set()
    for _ in range(4):
        _validate_handoff_transfer_url(url, provider)
        if url in visited:
            raise HandoffError("다운로드 서버 이동이 반복됩니다.")
        visited.add(url)
        try:
            response = (
                _open_sendnow_pinned(url, method, headers)
                if provider == "sendnow"
                else opener.open(Request(url, method=method, headers=headers), timeout=20)
            )
            if response.geturl() != url:
                response.close()
                raise HandoffError("예상하지 못한 다운로드 서버 이동입니다.")
            return response
        except HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise
            location = exc.headers.get("Location", "")
            exc.close()
            if not location or any(ord(c) < 33 or ord(c) == 127 for c in location) or "\\" in location:
                raise HandoffError("다운로드 서버 이동 주소가 올바르지 않습니다.") from None
            url = urljoin(url, location)
    raise HandoffError("다운로드 서버 이동 횟수를 초과했습니다.")


def _handoff_metadata(response, method: str):
    name = content_disposition_download_name([
        v.encode("latin-1", "replace") for v in response.headers.get_all("Content-Disposition", [])
    ])
    if not name:
        name = _clean_download_name(unquote(urlparse(response.geturl()).path.rsplit("/", 1)[-1]))
    try:
        size = int(response.headers.get("Content-Length", "0"))
    except ValueError:
        raise HandoffError("파일 크기 응답이 올바르지 않습니다.") from None
    ranges = response.headers.get("Accept-Ranges", "").strip().lower() == "bytes"
    if response.status == 206:
        match = re.fullmatch(r"bytes 0-0/(\d+)", response.headers.get("Content-Range", ""))
        if not match or size != 1:
            raise HandoffError("다운로드 서버의 범위 응답이 올바르지 않습니다.")
        size, ranges = int(match.group(1)), True
    elif response.status != 200 or method == "GET":
        raise HandoffError("다운로드 서버가 최소 범위 요청을 지원하지 않습니다.")
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if not name or content_type in {"text/html", "application/json", "application/xhtml+xml"}:
        raise HandoffError("다운로드 서버가 파일 대신 오류 페이지를 반환했습니다.")
    if not 0 < size <= MAX_FILE_BYTES or not ranges:
        if method == "HEAD":
            return None
        raise HandoffError("파일 크기 또는 이어받기 정보를 확인하지 못했습니다.")
    return name, size


def inspect_browser_handoff(share_url: str, signed_url: str, provider: str) -> dict:
    if provider not in {"akirabox", "vikingfile", "sendnow"}:
        raise ValueError("지원하지 않는 브라우저 다운로드 전달입니다.")
    validator = {"akirabox": _validate_akira_url, "vikingfile": _validate_viking_url, "sendnow": _validate_sendnow_url}[provider]
    canonical = validator(share_url, direct=False)
    direct = validator(signed_url, direct=True)
    opener = build_opener(AkiraNoRedirectHandler())
    headers = {"User-Agent": f"NASDrop/{PACKAGE_VERSION}", "Accept": "*/*", "Accept-Encoding": "identity", "Referer": canonical}
    try:
        metadata = None
        final_url = direct
        try:
            with _open_handoff_response(opener, direct, "HEAD", headers, provider) as response:
                final_url = response.geturl()
                metadata = _handoff_metadata(response, "HEAD")
        except HTTPError as exc:
            if exc.code not in {403, 405, 501}:
                raise
            final_url = _validate_handoff_transfer_url(exc.geturl(), provider)
            exc.close()
        if metadata is None:
            # Never read the body, even if a server ignores Range and sends a whole file.
            with _open_handoff_response(opener, final_url, "GET", {**headers, "Range": "bytes=0-0"}, provider) as response:
                final_url = response.geturl()
                metadata = _handoff_metadata(response, "GET")
        name, size = metadata
    except HTTPError as exc:
        code = exc.code
        exc.close()
        raise ValueError(f"다운로드 서버가 HTTP {code} 응답을 반환했습니다. 브라우저에서 새 링크를 받아 주세요.") from None
    except OSError:
        raise ValueError("NAS에서 다운로드 서버에 연결하지 못했습니다. 연결 또는 링크 만료 여부를 확인해 주세요.") from None
    except HandoffError as exc:
        raise ValueError(str(exc)) from None
    except ValueError:
        # Never include a signed URL, token, remote error page or headers in public errors.
        raise ValueError("NAS에서 브라우저 다운로드 파일 정보를 확인하지 못했습니다. 링크 만료·접속 제한·이어받기 지원 여부를 확인하고 브라우저에서 다시 등록해 주세요.") from None
    return {"url": canonical, "name": name, "size": size, "expires": "브라우저 링크", "provider": provider, "download_url": final_url}


def inspect_payload(payload: dict) -> dict:
    if "resolved_url" in payload:
        return inspect_browser_handoff(payload.get("url", ""), payload.get("resolved_url", ""), payload.get("provider", ""))
    return inspect_download(str(payload.get("url", "")))


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


class GigaFileRedirectHandler(HTTPRedirectHandler):
    def __init__(self, expected_host: str):
        super().__init__()
        self.expected_host = expected_host.lower()

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        parsed = urlparse(new_url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("GigaFile이 올바르지 않은 주소로 이동을 요청했습니다.") from exc
        if (
            parsed.scheme != "https"
            or (parsed.hostname or "").lower() != self.expected_host
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
        ):
            raise ValueError("GigaFile이 허용되지 않은 서버로 이동을 요청했습니다.")
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


def _gigafile_page_requires_download_key(source: str) -> bool:
    return bool(
        re.search(r'\bid\s*=\s*["\']dlkey["\']', source, re.I)
        and re.search(r'\bdownload\s*\([^)]*,\s*true\s*,', source, re.I)
    )


def _check_gigafile_download_key(opener, host: str, file_id: str, download_key: str, canonical: str) -> None:
    query = urlencode({"file": file_id, "dlkey": download_key, "is_zip": "0"})
    request = Request(
        f"https://{host}/check_dlkey.php?{query}",
        headers={"User-Agent": "Mozilla/5.0 NAS Download Portal", "Referer": canonical},
    )
    with opener.open(request, timeout=30) as response:
        raw = response.read(4096)
    try:
        result = json.loads(raw.decode("utf-8", "replace"))
        status = int(result.get("status", -1))
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("GigaFile 다운로드 키 확인 응답을 읽지 못했습니다.") from exc
    if status == 0:
        return
    if status == 1:
        raise GigaFileDownloadKeyInvalidError("GigaFile 다운로드 키가 올바르지 않습니다. 키를 확인해 다시 입력해 주세요.")
    if status == 3:
        raise GigaFileDownloadKeyRequiredError("GigaFile 다운로드 키 확인이 일시 잠겼습니다. 잠시 후 키를 다시 입력해 주세요.")
    raise GigaFileDownloadKeyRequiredError("GigaFile 다운로드 키를 확인하지 못했습니다. 키를 다시 입력해 주세요.")


def _apply_gigafile_download_key(inspected: dict, host: str, download_key: str) -> dict:
    candidates = inspected.get("files") if inspected.get("batch") else [inspected]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        individual_id = service_path_id(urlparse(str(item.get("url", ""))))
        item["download_url"] = f"https://{host}/download.php?{urlencode({'file': individual_id, 'dlkey': download_key})}"
    return inspected


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
        individual_name_matches = re.findall(
            r'<span\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bmatomete_file_name\b)'
            r'[^>]*>\s*(.*?)\s*</span>',
            source,
            re.S | re.I,
        )
        if not files_match:
            raise ValueError("파일 정보를 읽지 못했습니다. 링크가 만료됐는지 확인해 주세요.")
        try:
            files = json.loads(files_match.group(1))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("GigaFile 개별 파일 정보를 읽지 못했습니다.") from exc
        names = [_clean_download_name(value) for value in individual_name_matches]
        if not files or len(names) != len(files) or any(not name for name in names):
            raise ValueError("GigaFile 개별 파일 이름을 읽지 못했습니다.")
        expires = ""
        if expires_match:
            expires = html.unescape(re.sub(r"<[^>]+>", "", expires_match.group(1))).strip()
        individual_files = []
        try:
            for item, individual_name in zip(files, names):
                if not isinstance(item, dict):
                    raise ValueError
                individual_id = str(item.get("file", ""))
                individual_size = int(item.get("size", 0))
                if not SAFE_SERVICE_ID.fullmatch(individual_id):
                    raise ValueError
                if individual_size <= 0 or individual_size > MAX_FILE_BYTES:
                    raise ValueError
                individual_files.append({
                    "url": f"https://{host}/{individual_id}",
                    "name": individual_name,
                    "size": individual_size,
                    "expires": expires,
                    "provider": "gigafile",
                    "download_mode": "gigafile_file",
                    "download_url": f"https://{host}/download.php?file={individual_id}",
                })
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError("GigaFile 개별 파일 정보가 올바르지 않습니다.") from exc
        if len(individual_files) == 1:
            result = individual_files[0]
            return result
        size = sum(int(item["size"]) for item in individual_files)
        return {
            "url": canonical,
            "name": f"GigaFile ×{len(individual_files)}",
            "size": size,
            "expires": expires,
            "provider": "gigafile",
            "batch": True,
            "file_count": len(individual_files),
            "files": individual_files,
        }
    if not name or size <= 0 or size > MAX_FILE_BYTES:
        raise ValueError("허용할 수 없는 파일 정보입니다.")
    expires = ""
    if expires_match:
        expires = html.unescape(re.sub(r"<[^>]+>", "", expires_match.group(1))).strip()
    return {
        "url": canonical, "name": name, "size": size, "expires": expires, "provider": "gigafile",
        "download_mode": download_mode, "download_url": download_url,
    }


def _gigafile_cookie_header(cookie_jar: CookieJar, url: str) -> str:
    request = Request(url)
    cookie_jar.add_cookie_header(request)
    return request.get_header("Cookie", "")


def _probe_gigafile_file(file_info: dict, host: str, cookie_header: str) -> tuple[str, int | None]:
    headers = {
        "User-Agent": "Mozilla/5.0 NAS Download Portal",
        "Referer": str(file_info["url"]),
        "Range": "bytes=0-0",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    request = Request(str(file_info["download_url"]), headers=headers)
    opener = build_opener(GigaFileRedirectHandler(host))
    with opener.open(request, timeout=GIGAFILE_NAME_PROBE_TIMEOUT_SECONDS) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or (final.hostname or "").lower() != host:
            raise ValueError("GigaFile 최종 다운로드 서버가 올바르지 않습니다.")
        values = [
            value.encode("latin-1", "replace")
            for value in response.headers.get_all("Content-Disposition", [])
        ]
        actual_name = content_disposition_download_name(values)
        content_range = response.headers.get("Content-Range", "")
        range_match = re.search(r"/(\d+)$", content_range)
        actual_size = int(range_match.group(1)) if range_match else None
        response.read(1)
    return actual_name, actual_size


def resolve_gigafile_batch_names(inspected: dict, host: str, cookie_jar: CookieJar) -> dict:
    files = inspected.get("files")
    if not isinstance(files, list):
        return inspected
    cookie_headers = {
        str(item.get("download_url", "")): _gigafile_cookie_header(cookie_jar, str(item.get("download_url", "")))
        for item in files
        if isinstance(item, dict)
    }
    with ThreadPoolExecutor(max_workers=min(GIGAFILE_NAME_PROBE_WORKERS, len(files))) as executor:
        futures = {
            executor.submit(
                _probe_gigafile_file,
                item,
                host,
                cookie_headers.get(str(item.get("download_url", "")), ""),
            ): item
            for item in files
            if isinstance(item, dict)
        }
        for future in as_completed(futures):
            item = futures[future]
            try:
                actual_name, actual_size = future.result()
            except (HTTPError, OSError, TimeoutError, ValueError):
                continue
            if actual_name:
                item["name"] = actual_name
            if actual_size is not None and actual_size != int(item["size"]):
                raise ValueError("GigaFile 개별 파일 크기가 페이지 정보와 일치하지 않습니다.")
    for item in files:
        if "ファイル名が置換されました" not in str(item.get("name", "")):
            continue
        try:
            individual_id = service_path_id(urlparse(str(item["url"])))
        except (KeyError, ValueError):
            individual_id = "file"
        item["name"] = f"GigaFile {individual_id}"
    return inspected


def is_gigafile_fallback_name(name: str, source: str) -> bool:
    try:
        individual_id = service_path_id(urlparse(source))
    except ValueError:
        return False
    return name == f"GigaFile {individual_id}"


def inspect_gigafile(raw_url: str, download_key: str = "") -> dict:
    parsed = urlparse(raw_url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not GIGAFILE_HOST.fullmatch(host):
        raise ValueError("정식 GigaFile HTTPS 링크가 아닙니다.")
    file_id = service_path_id(parsed)
    canonical = f"https://{host}/{file_id}"
    cookie_jar = CookieJar()
    opener = build_opener(GigaFileRedirectHandler(host), HTTPCookieProcessor(cookie_jar))
    request = Request(canonical, headers={"User-Agent": "Mozilla/5.0 NAS Download Portal"})
    with opener.open(request, timeout=30) as response:
        source = response.read(2_000_000).decode("utf-8", "replace")
    requires_download_key = _gigafile_page_requires_download_key(source)
    normalized_download_key = _validate_gigafile_download_key(download_key)
    if requires_download_key:
        if not normalized_download_key:
            raise GigaFileDownloadKeyRequiredError("GigaFile 다운로드 키가 필요합니다. 키를 입력하면 받던 위치에서 계속합니다.")
        _check_gigafile_download_key(opener, host, file_id, normalized_download_key, canonical)
    inspected = parse_gigafile_page(source, canonical, host, file_id)
    if requires_download_key:
        inspected = _apply_gigafile_download_key(inspected, host, normalized_download_key)
    if inspected.get("batch"):
        return resolve_gigafile_batch_names(inspected, host, cookie_jar)
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


class SameHostHTTPSRedirectHandler(HTTPRedirectHandler):
    def __init__(self, expected_host: str):
        super().__init__()
        self.expected_host = expected_host.lower()

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        parsed = urlparse(new_url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("외부 서비스가 올바르지 않은 주소로 이동을 요청했습니다.") from exc
        if (
            parsed.scheme != "https"
            or (parsed.hostname or "").lower() != self.expected_host
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
        ):
            raise ValueError("외부 서비스가 허용되지 않은 서버로 이동을 요청했습니다.")
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def _json_request(
    url: str, *, method: str = "GET", headers: dict[str, str] | None = None, retry_429: bool = True,
) -> dict:
    attempts = 4 if retry_429 else 1
    for attempt in range(attempts):
        request = Request(url, method=method, headers=headers or {})
        try:
            host = (urlparse(url).hostname or "").lower()
            opener = build_opener(SameHostHTTPSRedirectHandler(host))
            with opener.open(request, timeout=30) as response:
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
        opener = build_opener(SameHostHTTPSRedirectHandler("gofile.io"))
        with opener.open(request, timeout=30) as response:
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
    helper = (ROOT / "gofile_wt.mjs").resolve()
    result = subprocess.run(
        ["node", "--permission", f"--allow-fs-read={helper}", str(helper)],
        input=payload, text=True, capture_output=True, timeout=10,
    )
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
        headers={"User-Agent": f"NASDrop/{PACKAGE_VERSION}"},
    )
    if not metadata.get("success") or not metadata.get("can_download", True):
        message = str(metadata.get("availability_message") or "파일을 다운로드할 수 없습니다.")
        raise ValueError(f"Pixeldrain: {message}")
    size = int(metadata.get("size", 0))
    name = _clean_download_name(str(metadata.get("name", "")))
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
    if host in {"akirabox.to", "akirabox.com"}:
        return "akirabox"
    if host in {"vik1ngfile.site", "vikingfile.com"}:
        return "vikingfile"
    if host in SENDNOW_SHARE_HOSTS or SENDNOW_PROVIDER_HOST.fullmatch(host):
        return "sendnow"
    if host in {"gofile.io", "www.gofile.io"}:
        return "gofile"
    if host in {"pixeldrain.com", "www.pixeldrain.com", "pixeldrain.net", "pixeldra.in"}:
        return "pixeldrain"
    if host == "buzzheavier.com" or _is_buzzheavier_download_host(host):
        return "buzzheavier"
    return "gigafile"


def inspect_download(raw_url: str) -> dict:
    host = (urlparse(raw_url.strip()).hostname or "").lower()
    if host in {"akirabox.to", "akirabox.com", "vik1ngfile.site", "vikingfile.com", *SENDNOW_SHARE_HOSTS}:
        raise ValueError("이 서비스는 크롬 확장에서 다운로드 버튼이 준비된 뒤 NAS로 보내 주세요.")
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
        while len(INSPECTION_CACHE) >= MAX_INSPECTION_CACHE_ENTRIES:
            INSPECTION_CACHE.pop(next(iter(INSPECTION_CACHE)))
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


def set_reverse_proxy_setting(enabled: object) -> bool:
    global CONFIG, TRUST_FORWARDED_FOR, UNTRUSTED_FORWARDED_HEADER_SEEN, UNTRUSTED_FORWARDED_HEADER_WARNED
    if not isinstance(enabled, bool):
        raise ValueError("DSM 역방향 프록시 설정이 올바르지 않습니다.")
    with CONFIG_LOCK:
        updated = dict(CONFIG)
        updated["NAS_PORTAL_TRUST_FORWARDED_FOR"] = enabled
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        temp = CONFIG_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(CONFIG_FILE)
        CONFIG = updated
        TRUST_FORWARDED_FOR = enabled
    with FORWARDED_HEADER_LOCK:
        UNTRUSTED_FORWARDED_HEADER_SEEN = False
        UNTRUSTED_FORWARDED_HEADER_WARNED = False
    LOGGER.warning("DSM reverse proxy mode %s", "enabled" if enabled else "disabled")
    return enabled


class Handler(BaseHTTPRequestHandler):
    server_version = "NASDrop"
    sys_version = ""
    timeout = REQUEST_TIMEOUT_SECONDS

    def end_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'none'; connect-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; "
            "object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'",
        )
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        super().end_headers()

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
        forwarded_for = self.headers.get("x-forwarded-for", "")
        note_forwarded_header(self.client_address[0], forwarded_for)
        return trusted_client_ip(self.client_address[0], forwarded_for)

    def auth_kind(self) -> str:
        supplied = self.authorization_token()
        return session_kind(supplied) if supplied else ""

    def authorized(self) -> bool:
        return bool(self.auth_kind())

    def require_completed_password_change(self) -> bool:
        if not password_change_required():
            return True
        self.send_json(HTTPStatus.FORBIDDEN, {
            "error": "초기 ID와 비밀번호를 변경해야 계속할 수 있습니다.",
            "code": "password_change_required",
        })
        return False

    def body(self) -> dict:
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length가 올바르지 않습니다.") from exc
        if length < 0:
            raise ValueError("Content-Length는 음수일 수 없습니다.")
        if length > REQUEST_BODY_LIMIT:
            raise ValueError(f"요청 본문은 {REQUEST_BODY_LIMIT}바이트를 초과할 수 없습니다.")
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("요청 본문은 JSON 객체여야 합니다.")
        return payload

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("allow", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        if path == "/api/auth/status":
            return self.send_json(HTTPStatus.OK, {
                "configured": credentials_configured(),
                "password_change_required": password_change_required(),
            })
        if path == "/api/jobs":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "로그인이 필요합니다."})
            if not self.require_completed_password_change():
                return
            return self.send_json(HTTPStatus.OK, {"jobs": CONTROLLER.public_jobs()})
        if parsed_path.path == "/api/folders":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "로그인이 필요합니다."})
            if not self.require_completed_password_change():
                return
            try:
                requested = parse_qs(parsed_path.query).get("path", ["/"])[0]
                return self.send_json(HTTPStatus.OK, browse_folders(requested))
            except ValueError as exc:
                return self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if path == "/api/status":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "로그인이 필요합니다."})
            if password_change_required():
                return self.send_json(HTTPStatus.OK, {
                    "version": PACKAGE_VERSION,
                    "password_change_required": True,
                })
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
                "password_change_required": password_change_required(),
                "job_processing_options": True,
                "job_safe_delete": True,
                "gigafile_download_key": True,
                "browser_handoff_providers": ["akirabox", "vikingfile", "sendnow"],
                "disk_protection": DISK_PROTECTION,
                "temporary_folder": ".nasdrop-tmp",
                "archive_formats": ["zip", "7z", "rar", "tar", "tar.gz", "tgz", "tar.bz2", "tbz2", "tar.xz", "txz"],
                "seven_zip_available": SEVEN_ZIP.is_file(),
                "gofile_cooldown": _gofile_cooldown_status(),
                "reverse_proxy_mode": TRUST_FORWARDED_FOR,
                "untrusted_forwarded_header_seen": UNTRUSTED_FORWARDED_HEADER_SEEN,
            })
        if path == "/api/account":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "로그인이 필요합니다."})
            return self.send_json(HTTPStatus.OK, {
                "configured": credentials_configured(),
                "username": str(CREDENTIALS.get("username", "")),
                "launcher_session": False,
                "launcher_reset_available": False,
                "password_change_required": password_change_required(),
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
                global_retry = global_login_retry_after()
                if global_retry:
                    return self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {
                        "error": f"로그인 요청이 잠시 제한되었습니다. {global_retry}초 후 다시 시도하세요.",
                        "code": "login_temporarily_limited",
                        "params": {"seconds": global_retry},
                    })
                remaining = login_block_remaining(client_ip)
                if remaining:
                    minutes = max(1, (remaining + 59) // 60)
                    return self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {
                        "error": f"로그인 시도가 너무 많습니다. 약 {minutes}분 후 다시 시도하세요.",
                        "code": "too_many_attempts",
                        "params": {"minutes": minutes},
                    })
                username = payload.get("username")
                password = payload.get("password")
                valid = verify_credentials(username, password)
                record_login_result(client_ip, valid)
                if not valid:
                    record_global_login_failure()
                    return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "ID 또는 비밀번호가 올바르지 않습니다."})
                token = create_session(str(CREDENTIALS["username"]))
                return self.send_json(HTTPStatus.OK, {
                    "token": token,
                    "username": str(CREDENTIALS["username"]),
                    "password_change_required": password_change_required(),
                })
            except (ValueError, json.JSONDecodeError) as exc:
                return self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if path == "/api/dsm/launcher-config":
            if not validate_dsm_launcher_handoff(self.authorization_token(), consume=False):
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "DSM 아이콘 연결이 올바르지 않습니다."})
            return self.send_json(HTTPStatus.OK, {"launcher_port": LAUNCHER_PORT})
        if path == "/api/launcher/session":
            username = consume_dsm_launcher_handoff(self.authorization_token())
            if not username:
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "DSM 아이콘 연결이 만료되었습니다. 아이콘을 다시 열어 주세요."})
            token = create_session(username)
            return self.send_json(HTTPStatus.OK, {"token": token})
        if not self.authorized():
            return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "로그인이 필요합니다."})
        if path not in {"/api/logout", "/api/account"} and not self.require_completed_password_change():
            return
        try:
            payload = self.body()
            if path == "/api/logout":
                revoke_session(self.authorization_token())
                return self.send_json(HTTPStatus.OK, {"ok": True})
            if path == "/api/account":
                auth_kind = self.auth_kind()
                if credentials_configured():
                    if not verify_credentials(str(CREDENTIALS.get("username", "")), payload.get("current_password")):
                        raise ValueError("현재 비밀번호가 올바르지 않습니다.")
                username = replace_credentials(payload.get("username"), payload.get("password"))
                result = {"ok": True, "username": username, "password_change_required": False}
                if auth_kind in {"session", "launcher"}:
                    result["token"] = create_session(username)
                return self.send_json(HTTPStatus.OK, result)
            if path == "/api/inspect":
                inspected = inspect_payload(payload)
                return self.send_json(HTTPStatus.OK, {"file": cache_inspection(inspected)})
            if path == "/api/enqueue":
                job = CONTROLLER.enqueue_gigafile(str(payload.get("url", "")), str(payload.get("target", "")),
                                                  payload.get("extract"), str(payload.get("password", "")),
                                                  str(payload.get("download_key", "")))
                return self.send_json(HTTPStatus.ACCEPTED, {"job": asdict(job), "count": 1})
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
                    download_key=str(payload.get("download_key", "")),
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
                if "reverse_proxy_mode" in payload:
                    result["reverse_proxy_mode"] = set_reverse_proxy_setting(payload.get("reverse_proxy_mode"))
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
            processing_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/processing", path)
            if processing_match:
                result = CONTROLLER.update_processing(processing_match.group(1), payload.get("extract"), payload.get("password"))
                return self.send_json(HTTPStatus.OK, {"job": result})
            password_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/password", path)
            if password_match:
                CONTROLLER.submit_password(password_match.group(1), payload.get("password", ""))
                return self.send_json(HTTPStatus.OK, {"ok": True})
            download_key_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/download-key", path)
            if download_key_match:
                CONTROLLER.submit_download_key(download_key_match.group(1), payload.get("download_key", ""))
                return self.send_json(HTTPStatus.OK, {"ok": True})
            if path == "/api/jobs/delete":
                ids = payload.get("ids", [])
                if not isinstance(ids, list) or not ids or any(not re.fullmatch(r"[a-f0-9]{12}", str(item)) for item in ids):
                    raise ValueError("삭제할 작업을 선택해 주세요.")
                stop_active = payload.get("stop_active", False)
                if not isinstance(stop_active, bool):
                    raise ValueError("stop_active must be a boolean")
                if stop_active:
                    result = CONTROLLER.request_delete([str(item) for item in ids])
                    return self.send_json(HTTPStatus.ACCEPTED if result["pending"] else HTTPStatus.OK, result)
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
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    def stop_service(_signum, _frame):
        SHUTDOWN_EVENT.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)
    try:
        server.serve_forever()
    finally:
        CONTROLLER.shutdown()
        server.server_close()
