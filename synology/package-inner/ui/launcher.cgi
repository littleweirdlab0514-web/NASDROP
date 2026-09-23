#!/usr/bin/python3
"""DSM-authenticated NASDrop launcher; never stores a bearer token in static files."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


AUTHENTICATE_CGI = "/usr/syno/synoman/webman/modules/authenticate.cgi"
BACKEND_CONFIG_URL = "http://127.0.0.1:8791/api/dsm/launcher-config"
LAUNCHER_SECRET_FILE = "/var/packages/nasdownloadportal/var/dsm_launcher_secret"
AUTH_STATUS_URL = "http://127.0.0.1:8791/api/auth/status"
MANUAL_LAUNCHER_URL = "/webman/3rdparty/nasdownloadportal/launcher.html"


def response(status: str, body: str, *, nonce: str = "") -> None:
    print(f"Status: {status}")
    print("Content-Type: text/html; charset=utf-8")
    print("Cache-Control: no-store, max-age=0")
    print("Pragma: no-cache")
    print("Referrer-Policy: no-referrer")
    print("X-Content-Type-Options: nosniff")
    print("X-Frame-Options: SAMEORIGIN")
    policy = "default-src 'none'; base-uri 'none'; frame-ancestors 'self'"
    if nonce:
        policy += f"; script-src 'nonce-{nonce}'"
    print(f"Content-Security-Policy: {policy}")
    print()
    print(body)


def fail(status: str, message: str) -> None:
    response(status, "<!doctype html><meta charset=utf-8><title>NASDrop</title><p>" + html.escape(message) + "</p>")
    raise SystemExit(0)


def manual_login_if_configured() -> None:
    """Use the ordinary NASDrop login when DSM's cookie CGI cannot see this session."""
    try:
        with urlopen(AUTH_STATUS_URL, timeout=3) as result:
            configured = json.loads(result.read(4096)).get("configured") is True
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
        configured = False
    if configured:
        print("Status: 302 Found")
        print(f"Location: {MANUAL_LAUNCHER_URL}")
        print("Cache-Control: no-store, max-age=0")
        print("Referrer-Policy: no-referrer")
        print("Content-Type: text/html; charset=utf-8")
        print()
        raise SystemExit(0)


def authenticated_admin() -> str:
    try:
        result = subprocess.run(
            [AUTHENTICATE_CGI], capture_output=True, text=True, timeout=5, check=False, env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError):
        fail("503 Service Unavailable", "DSM 로그인을 확인하지 못했습니다.")
    username = result.stdout.strip()
    # Synology documents stdout (username vs. no output) as the authentication
    # contract.  Its reference CGI intentionally does not use the child exit
    # status, which is not stable across DSM releases.
    if not username or len(username) > 128 or any(ord(c) < 32 or ord(c) == 127 for c in username):
        manual_login_if_configured()
        fail("401 Unauthorized", "DSM에 로그인한 뒤 NASDrop을 다시 열어 주세요.")
    try:
        groups = subprocess.run(
            ["/usr/bin/id", "-Gn", username], capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        fail("403 Forbidden", "DSM 관리자 권한을 확인하지 못했습니다.")
    if groups.returncode != 0 or "administrators" not in groups.stdout.split():
        fail("403 Forbidden", "DSM 관리자만 NASDrop을 열 수 있습니다.")
    return username


def create_handoff(username: str) -> str:
    try:
        with open(LAUNCHER_SECRET_FILE, "r", encoding="ascii") as source:
            encoded_secret = source.read().strip()
        secret = bytes.fromhex(encoded_secret)
    except (OSError, UnicodeError, ValueError):
        fail("503 Service Unavailable", "NASDrop DSM 연결 키를 읽지 못했습니다.")
    if len(secret) != 32:
        fail("503 Service Unavailable", "NASDrop DSM 연결 키가 올바르지 않습니다.")
    payload = json.dumps(
        {"u": username, "e": int(time.time()) + 30, "n": secrets.token_hex(8)},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(secret, encoded, hashlib.sha256).digest()
    return encoded.decode("ascii") + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def request_launcher_port(token: str) -> int:
    request = Request(
        BACKEND_CONFIG_URL,
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
    )
    try:
        with urlopen(request, timeout=5) as result:
            payload = json.loads(result.read(4096))
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
        fail("503 Service Unavailable", "NASDrop 서비스에 연결하지 못했습니다.")
    port = payload.get("launcher_port", 8791)
    if not isinstance(port, int) or not 1 <= port <= 65535:
        fail("503 Service Unavailable", "NASDrop 연결 정보를 만들지 못했습니다.")
    return port


def main() -> None:
    username = authenticated_admin()
    token = create_handoff(username)
    public_port = request_launcher_port(token)
    nonce = secrets.token_urlsafe(18)
    token_json = json.dumps(token)
    script = f"""
var host = location.hostname;
var plainHost = host.replace(/^\\[|\\]$/g, "").toLowerCase();
var isV6 = plainHost.indexOf(":") !== -1;
var privateHost = plainHost === "localhost" || plainHost === "::1" ||
  (!isV6 && (/^(127\\.|10\\.|192\\.168\\.)/.test(plainHost) ||
  /^172\\.(1[6-9]|2[0-9]|3[01])\\./.test(plainHost) ||
  plainHost.endsWith(".local") || plainHost.indexOf(".") === -1));
var targetProtocol = location.protocol === "https:" ? "https://" : "http://";
if (privateHost) targetProtocol = "http://";
var targetPort = privateHost ? 8791 : {public_port};
location.replace(targetProtocol + host + ":" + targetPort + "/#token=" + encodeURIComponent({token_json}));
"""
    response(
        "200 OK",
        f'<!doctype html><html><head><meta charset="utf-8"><title>NASDrop</title></head><body><script nonce="{nonce}">{script}</script></body></html>',
        nonce=nonce,
    )


if __name__ == "__main__":
    main()
