#!/usr/bin/env python3
"""Authenticated Synology portal and direct-to-NAS download controller."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import hashlib
import html
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import signal
import shlex
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("NAS_PORTAL_STATE_DIR", str(ROOT / "runtime"))).resolve()
STATE_FILE = STATE_DIR / "jobs.json"
TOKEN_FILE = STATE_DIR / "access_token"
CONFIG_FILE = STATE_DIR / "config.json"
GOFILE_COOLDOWN_FILE = STATE_DIR / "gofile_cooldown.json"


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
PACKAGE_VERSION = setting("NAS_PORTAL_VERSION", "0.7.7")
MAX_FILE_BYTES = 300 * 1024**3
MAX_PARALLEL_DOWNLOADS = 3
BATCH_QUEUE_STAGGER_SECONDS = 20
GOFILE_MIN_REQUEST_INTERVAL_SECONDS = 2.0
GOFILE_RATE_LIMIT_COOLDOWN_SECONDS = 30 * 60
GOFILE_NETWORK_COOLDOWN_SECONDS = 5 * 60
GOFILE_MAX_COOLDOWN_SECONDS = 6 * 60 * 60
GIGAFILE_HOST = re.compile(r"^[a-z0-9-]+\.gigafile\.nu$", re.I)
SAFE_SERVICE_ID = re.compile(r"^[A-Za-z0-9._~-]{1,256}$")
GOFILE_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36"


def bool_setting(name: str, default: bool = False) -> bool:
    return setting(name, "1" if default else "0").lower() in {"1", "true", "yes", "on"}


def parallel_limit_setting() -> int:
    try:
        value = int(setting("NAS_PORTAL_SAME_PROVIDER_LIMIT", "2"))
    except ValueError:
        value = 2
    return min(3, max(2, value))


ALLOW_SAME_PROVIDER_PARALLEL = bool_setting("NAS_PORTAL_ALLOW_SAME_PROVIDER_PARALLEL")
SAME_PROVIDER_LIMIT = parallel_limit_setting()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_token() -> str:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    return token


ACCESS_TOKEN = load_token()
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


def replace_access_token() -> str:
    global ACCESS_TOKEN
    token = secrets.token_urlsafe(32)
    temp = TOKEN_FILE.with_suffix(".tmp")
    temp.write_text(token + "\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(TOKEN_FILE)
    ACCESS_TOKEN = token
    return token


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


class Controller:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.jobs: dict[str, Job] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.private_downloads: dict[str, dict[str, str]] = {}
        self.running_providers: dict[str, set[str]] = {}
        self.load()
        threading.Thread(target=self._dispatcher, name="nasdrop-dispatcher", daemon=True).start()

    def load(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            for item in data:
                if item.get("status") in {"downloading", "verifying", "ready"}:
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
        temp.replace(STATE_FILE)

    def public_jobs(self) -> list[dict]:
        with self.lock:
            return [asdict(job) for job in reversed(list(self.jobs.values()))]

    def active(self) -> bool:
        return any(job.status in {"ready", "downloading", "verifying"} for job in self.jobs.values())

    def start(self, file: dict, target: str = "") -> Job:
        return self.start_many([file], target)[0]

    def start_many(self, files: list[dict], target: str = "") -> list[Job]:
        if not files:
            raise ValueError("다운로드할 파일이 없습니다.")
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
        import glob
        return sum(os.path.getsize(path) for path in glob.glob(prefix + "*") if os.path.isfile(path))

    def _run(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            if job.status in {"paused", "cancelled"}:
                return
            job.status = "downloading"
            self.save()
        private = self.private_downloads.get(job_id, {})
        target_dir = private.get("target") or job.target or NAS_TARGET
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
        safe_name = job.name
        prefix = f"{target_dir}/.{safe_name}.{job.id}.segment."
        if provider == "gigafile" and private.get("download_mode") == "gigafile_zip":
            script = self._download_script_gigafile_zip(
                private.get("download_url", ""), job.source, safe_name, job.id, job.size, target_dir,
            )
        elif provider == "gofile":
            script = self._download_script_gofile(
                private.get("download_url", ""), private.get("download_token", ""),
                job.source, safe_name, job.id, job.size, target_dir,
            )
        elif provider == "pixeldrain":
            script = self._download_script_direct(
                private.get("download_url", ""), job.source, safe_name, job.id, job.size, target_dir,
                expected_sha256=private.get("expected_sha256", ""),
            )
        else:
            file_id = parsed.path.strip("/")
            host = parsed.hostname or ""
            script = self._download_script(host, file_id, safe_name, job.id, job.size, target_dir)
        command = ["sh", "-s"]
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        self.processes[job_id] = process
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
                current_job.error = (stderr.strip() or "NAS 다운로드가 중단됐습니다.")[-400:]
            else:
                match = re.search(r"SHA256=([0-9a-f]{64})", stdout)
                current_job.downloaded = current_job.size
                current_job.status = "completed"
                current_job.sha256 = match.group(1) if match else ""
            self.processes.pop(job_id, None)
            self.private_downloads.pop(job_id, None)
            self.save()

    def _download_script(self, host: str, file_id: str, name: str, job_id: str, total: int, target_dir: str) -> str:
        page = f"https://{host}/{file_id}"
        download = f"https://{host}/download.php?file={file_id}"
        target = f"{target_dir}/{name}"
        assembled = f"{target_dir}/.{name}.{job_id}.assembling"
        prefix = f"{target_dir}/.{name}.{job_id}.segment"
        cookie = f"/tmp/nas_download_{job_id}.cookies"
        quoted_parts = " ".join(shlex.quote(f"{prefix}.{i}") for i in range(8))
        return f"""#!/bin/sh
set -eu
TOTAL={total}
COUNT=8
CHUNK=$(( (TOTAL + COUNT - 1) / COUNT ))
curl -L --fail --silent --show-error -c {shlex.quote(cookie)} {shlex.quote(page)} -o /tmp/nas_download_{job_id}.page
i=0
while [ "$i" -lt "$COUNT" ]; do
  start=$(( i * CHUNK )); end=$(( start + CHUNK - 1 )); [ "$end" -ge "$TOTAL" ] && end=$(( TOTAL - 1 ))
  part={shlex.quote(prefix)}.$i
  (expected=$(( end - start + 1 )); existing=0; [ -f "$part" ] && existing=$(wc -c < "$part" | tr -d ' '); [ "$existing" -le "$expected" ] || rm -f "$part"; [ -f "$part" ] && existing=$(wc -c < "$part" | tr -d ' ') || existing=0; if [ "$existing" -lt "$expected" ]; then from=$(( start + existing )); more="$part.more"; curl -L --fail --silent --show-error --retry 8 --retry-delay 5 -b {shlex.quote(cookie)} -e {shlex.quote(page)} -r "$from-$end" -o "$more" {shlex.quote(download)}; cat "$more" >> "$part"; rm -f "$more"; fi; actual=$(wc -c < "$part" | tr -d ' '); [ "$actual" -eq "$expected" ]) &
  i=$(( i + 1 ))
done
wait
cat {quoted_parts} > {shlex.quote(assembled)}
actual=$(wc -c < {shlex.quote(assembled)} | tr -d ' '); [ "$actual" -eq "$TOTAL" ]
case {shlex.quote(name.lower())} in *.zip) python3 -m zipfile -t {shlex.quote(assembled)} >/dev/null;; esac
hash=$(sha256sum {shlex.quote(assembled)} | cut -d' ' -f1)
mv {shlex.quote(assembled)} {shlex.quote(target)}
rm -f {quoted_parts}
trap - EXIT HUP INT TERM
printf 'SHA256=%s\\n' "$hash"
"""

    def _download_script_gofile(self, download: str, token: str, page: str, name: str, job_id: str, total: int, target_dir: str) -> str:
        if not download.startswith("https://") or not token:
            raise ValueError("Gofile 다운로드 인증 정보가 없습니다.")
        return self._download_script_direct(download, page, name, job_id, total, target_dir, cookie=f"accountToken={token}")

    def _download_script_gigafile_zip(self, download: str, page: str, name: str, job_id: str, total: int, target_dir: str) -> str:
        parsed_download = urlparse(download)
        parsed_page = urlparse(page)
        if (
            parsed_download.scheme != "https"
            or parsed_download.hostname != parsed_page.hostname
            or not GIGAFILE_HOST.fullmatch(parsed_download.hostname or "")
            or parsed_download.path != "/dl_zip.php"
        ):
            raise ValueError("GigaFile 묶음 다운로드 주소가 올바르지 않습니다.")
        target = f"{target_dir}/{name}"
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
curl -L --fail --silent --show-error -c "$COOKIE" {shlex.quote(page)} -o "$PAGE_COPY"
rm -f "$PART"
curl -L --fail --silent --show-error --retry 8 --retry-delay 5 -b "$COOKIE" -e {shlex.quote(page)} -o "$PART" {shlex.quote(download)}
actual=$(wc -c < "$PART" | tr -d ' '); [ "$actual" -ge "$TOTAL" ]
case {shlex.quote(name.lower())} in *.zip) python3 -m zipfile -t "$PART" >/dev/null;; esac
hash=$(sha256sum "$PART" | cut -d' ' -f1)
mv "$PART" {shlex.quote(target)}
trap - EXIT HUP INT TERM
cleanup
printf 'SHA256=%s\\n' "$hash"
"""

    def _download_script_direct(self, download: str, page: str, name: str, job_id: str, total: int, target_dir: str, cookie: str = "", expected_sha256: str = "") -> str:
        if not download.startswith("https://"):
            raise ValueError("직접 다운로드 주소가 올바르지 않습니다.")
        target = f"{target_dir}/{name}"
        assembled = f"{target_dir}/.{name}.{job_id}.assembling"
        prefix = f"{target_dir}/.{name}.{job_id}.segment"
        quoted_parts = " ".join(shlex.quote(f"{prefix}.{i}") for i in range(8))
        header_option = f"-H {shlex.quote('Cookie: ' + cookie)}" if cookie else ""
        hash_check = f"[ \"$hash\" = {shlex.quote(expected_sha256.lower())} ]" if re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256) else ":"
        return f"""#!/bin/sh
set -eu
TOTAL={total}
COUNT=8
CHUNK=$(( (TOTAL + COUNT - 1) / COUNT ))
i=0
while [ "$i" -lt "$COUNT" ]; do
  start=$(( i * CHUNK )); end=$(( start + CHUNK - 1 )); [ "$end" -ge "$TOTAL" ] && end=$(( TOTAL - 1 ))
  part={shlex.quote(prefix)}.$i
  (expected=$(( end - start + 1 )); existing=0; [ -f "$part" ] && existing=$(wc -c < "$part" | tr -d ' '); [ "$existing" -le "$expected" ] || rm -f "$part"; [ -f "$part" ] && existing=$(wc -c < "$part" | tr -d ' ') || existing=0; if [ "$existing" -lt "$expected" ]; then from=$(( start + existing )); more="$part.more"; curl -L --fail --silent --show-error --retry 8 --retry-delay 5 {header_option} -e {shlex.quote(page)} -r "$from-$end" -o "$more" {shlex.quote(download)}; cat "$more" >> "$part"; rm -f "$more"; fi; actual=$(wc -c < "$part" | tr -d ' '); [ "$actual" -eq "$expected" ]) &
  i=$(( i + 1 ))
done
wait
cat {quoted_parts} > {shlex.quote(assembled)}
actual=$(wc -c < {shlex.quote(assembled)} | tr -d ' '); [ "$actual" -eq "$TOTAL" ]
case {shlex.quote(name.lower())} in *.zip) python3 -m zipfile -t {shlex.quote(assembled)} >/dev/null;; esac
hash=$(sha256sum {shlex.quote(assembled)} | cut -d' ' -f1)
{hash_check}
mv {shlex.quote(assembled)} {shlex.quote(target)}
rm -f {quoted_parts}
trap - EXIT HUP INT TERM
printf 'SHA256=%s\\n' "$hash"
"""

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            process.terminate()

    def pause(self, job_id: str) -> None:
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            job = self.jobs[job_id]
            if job.status not in {"queued", "ready", "downloading", "verifying"}:
                raise ValueError("중지할 수 있는 작업이 아닙니다.")
            job.status = "paused"
            job.error = ""
            process = self.processes.get(job_id)
            if process:
                self._terminate(process)
            self.save()

    def resume(self, job_id: str) -> None:
        with self.condition:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            job = self.jobs[job_id]
            if job.status not in {"paused", "failed", "cancelled"}:
                raise ValueError("다시 시작할 수 있는 작업이 아닙니다.")
            job.status = "queued"
            job.error = ""
            job.sha256 = ""
            job.not_before = 0
            self.save()
            self.condition.notify_all()

    def delete(self, job_ids: list[str]) -> int:
        with self.lock:
            for job_id in job_ids:
                job = self.jobs.get(job_id)
                if not job:
                    raise KeyError(job_id)
                if job.status in {"queued", "ready", "downloading", "verifying"}:
                    raise ValueError("실행 중인 작업은 먼저 멈춰 주세요.")
            for job_id in job_ids:
                self.jobs.pop(job_id, None)
                self.private_downloads.pop(job_id, None)
            self.save()
            return len(job_ids)

    def clear_completed(self) -> int:
        with self.lock:
            completed = [job_id for job_id, job in self.jobs.items() if job.status == "completed"]
            for job_id in completed:
                self.jobs.pop(job_id, None)
            self.save()
            return len(completed)

    def cancel(self, job_id: str) -> None:
        self.pause(job_id)


CONTROLLER = Controller()


def _clean_download_name(value: str) -> str:
    name = html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
    return re.sub(r"[\\/\x00-\x1f:]", "_", name)[:180]


def service_path_id(parsed, prefix: str = "") -> str:
    parts = parsed.path.strip("/").split("/")
    expected = 2 if prefix else 1
    if len(parts) != expected or (prefix and parts[0] != prefix):
        raise ValueError("지원 서비스의 공유 링크 형식이 아닙니다.")
    value = unquote(parts[-1])
    if not SAFE_SERVICE_ID.fullmatch(value):
        raise ValueError("링크 경로에 사용할 수 없는 문자가 있습니다.")
    return value


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
    return parse_gigafile_page(source, canonical, host, file_id)


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
    return "gigafile"


def inspect_download(raw_url: str) -> dict:
    host = (urlparse(raw_url.strip()).hostname or "").lower()
    try:
        if host in {"gofile.io", "www.gofile.io"}:
            return inspect_gofile(raw_url)
        if host in {"pixeldrain.com", "www.pixeldrain.com", "pixeldrain.net", "pixeldra.in"}:
            return inspect_pixeldrain(raw_url)
        return inspect_gigafile(raw_url)
    except HTTPError as exc:
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


VOLUME_DIR = re.compile(r"^/volume[0-9]+(?:/.*)?$")


def normalize_target(raw_path: str) -> str:
    value = str(raw_path or "").strip()
    if not value:
        raise ValueError("저장 폴더를 선택해 주세요.")
    target = Path(value).resolve()
    normalized = str(target)
    if not VOLUME_DIR.fullmatch(normalized):
        raise ValueError("Synology 볼륨 안의 폴더만 선택할 수 있습니다.")
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
    if value == "/" or re.fullmatch(r"/volume[0-9]+", value.rstrip("/")):
        shares = []
        volumes = [path for path in Path("/").iterdir() if re.fullmatch(r"volume[0-9]+", path.name)]
        for volume in sorted(volumes, key=lambda item: item.name):
            try:
                candidates = volume.iterdir()
                for path in candidates:
                    if not path.is_dir() or path.name.startswith((".", "@")) or path.name == "lost+found":
                        continue
                    shares.append(path)
            except PermissionError:
                continue
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
    if not VOLUME_DIR.fullmatch(normalized) or not current.is_dir():
        raise ValueError("탐색할 수 없는 폴더입니다.")
    try:
        candidates = [path for path in current.iterdir() if path.is_dir() and not path.name.startswith((".", "@")) and path.name != "lost+found"]
    except PermissionError as exc:
        raise ValueError("이 폴더를 볼 권한이 없습니다.") from exc
    parent = "/" if re.fullmatch(r"/volume[0-9]+/[^/]+", normalized) else str(current.parent)
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


def pairing_server(host: str, forwarded_host: str = "", forwarded_proto: str = "") -> str:
    public_host = forwarded_host.split(",", 1)[0].strip() or host.strip()
    if not public_host or len(public_host) > 255 or not re.fullmatch(r"[A-Za-z0-9.\[\]:-]+", public_host):
        public_host = f"127.0.0.1:{LISTEN_PORT}"
    scheme = "https" if forwarded_proto.split(",", 1)[0].strip().lower() == "https" else "http"
    return f"{scheme}://{public_host}"


class Handler(BaseHTTPRequestHandler):
    server_version = "NasDownloadPortal/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{now()}] {self.client_address[0]} {fmt % args}", flush=True)

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self) -> bool:
        supplied = self.headers.get("authorization", "")
        if supplied.startswith("Bearer "):
            supplied = supplied[7:]
        supplied = supplied.strip()
        return bool(supplied) and secrets.compare_digest(
            supplied.encode("utf-8"), ACCESS_TOKEN.encode("utf-8")
        )

    def pairing_payload(self, token=None) -> dict:
        server = pairing_server(
            self.headers.get("host", ""),
            self.headers.get("x-forwarded-host", ""),
            self.headers.get("x-forwarded-proto", ""),
        )
        access = token or ACCESS_TOKEN
        pairing_uri = "nasdrop://pair?" + urlencode({
            "server": server,
            "token": access,
            "folder": NAS_TARGET,
        })
        return {"server": server, "token": access, "folder": NAS_TARGET, "uri": pairing_uri}

    def body(self) -> dict:
        length = min(int(self.headers.get("content-length", "0")), 16_384)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("allow", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_path = urlparse(self.path)
        if self.path == "/api/jobs":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "접근 코드가 올바르지 않습니다."})
            return self.send_json(HTTPStatus.OK, {"jobs": CONTROLLER.public_jobs()})
        if parsed_path.path == "/api/folders":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "접근 코드가 올바르지 않습니다."})
            try:
                requested = parse_qs(parsed_path.query).get("path", ["/"])[0]
                return self.send_json(HTTPStatus.OK, browse_folders(requested))
            except ValueError as exc:
                return self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if self.path == "/api/status":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "접근 코드가 올바르지 않습니다."})
            target = Path(NAS_TARGET) if NAS_TARGET else None
            target_exists = bool(target and target.is_dir())
            return self.send_json(HTTPStatus.OK, {
                "version": PACKAGE_VERSION,
                "target": NAS_TARGET,
                "target_exists": target_exists,
                "target_writable": target_exists and os.access(str(target), os.W_OK | os.X_OK),
                "service_user": os.environ.get("USER", ""),
                "same_provider_parallel": ALLOW_SAME_PROVIDER_PARALLEL,
                "same_provider_limit": SAME_PROVIDER_LIMIT,
                "max_parallel_downloads": MAX_PARALLEL_DOWNLOADS,
                "gofile_cooldown": _gofile_cooldown_status(),
            })
        if self.path == "/api/pairing":
            if not self.authorized():
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "접근 코드가 올바르지 않습니다."})
            return self.send_json(HTTPStatus.OK, self.pairing_payload())
        self.serve_static()

    def do_POST(self) -> None:
        if not self.path.startswith("/api/"):
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "찾을 수 없습니다."})
        if not self.authorized():
            return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "접근 코드가 올바르지 않습니다."})
        try:
            payload = self.body()
            if self.path == "/api/inspect":
                inspected = inspect_download(str(payload.get("url", "")))
                return self.send_json(HTTPStatus.OK, {"file": cache_inspection(inspected)})
            if self.path == "/api/start":
                inspected = consume_inspection(payload)
                if (
                    inspected["url"] != payload.get("url")
                    or inspected["name"] != payload.get("name")
                    or inspected["size"] != int(payload.get("size", 0))
                ):
                    raise ValueError("파일 정보가 변경되어 다시 확인해야 합니다.")
                files = inspected.get("files") if inspected.get("batch") else [inspected]
                jobs = CONTROLLER.start_many(files, str(payload.get("target", "")))
                return self.send_json(HTTPStatus.ACCEPTED, {"job": asdict(jobs[0]), "jobs": [asdict(job) for job in jobs], "count": len(jobs)})
            if self.path == "/api/settings":
                result = {"ok": True}
                if "target" in payload:
                    result["target"] = set_default_target(str(payload.get("target", "")))
                if "same_provider_parallel" in payload or "same_provider_limit" in payload:
                    result.update(set_parallel_settings(payload.get("same_provider_parallel"), payload.get("same_provider_limit")))
                if len(result) == 1:
                    raise ValueError("변경할 설정이 없습니다.")
                return self.send_json(HTTPStatus.OK, result)
            if self.path == "/api/token/rotate":
                token = replace_access_token()
                return self.send_json(HTTPStatus.OK, self.pairing_payload(token))
            cancel_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/cancel", self.path)
            if cancel_match:
                CONTROLLER.cancel(cancel_match.group(1))
                return self.send_json(HTTPStatus.OK, {"ok": True})
            pause_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/pause", self.path)
            if pause_match:
                CONTROLLER.pause(pause_match.group(1))
                return self.send_json(HTTPStatus.OK, {"ok": True})
            resume_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/resume", self.path)
            if resume_match:
                CONTROLLER.resume(resume_match.group(1))
                return self.send_json(HTTPStatus.OK, {"ok": True})
            if self.path == "/api/jobs/delete":
                ids = payload.get("ids", [])
                if not isinstance(ids, list) or not ids or any(not re.fullmatch(r"[a-f0-9]{12}", str(item)) for item in ids):
                    raise ValueError("삭제할 작업을 선택해 주세요.")
                deleted = CONTROLLER.delete([str(item) for item in ids])
                return self.send_json(HTTPStatus.OK, {"ok": True, "deleted": deleted})
            if self.path == "/api/jobs/completed/clear":
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
    print(f"NAS Download Portal listening on http://{LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler).serve_forever()
