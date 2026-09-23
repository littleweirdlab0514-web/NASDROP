#!/usr/bin/python3
"""DSM-authenticated NASDrop launcher; never stores a bearer token in static files."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener, urlopen


AUTHENTICATE_CGIS = (
    "/usr/syno/synoman/webman/authenticate.cgi",
    "/usr/syno/synoman/webman/modules/authenticate.cgi",
)
LOGIN_CGI = "/usr/syno/synoman/webman/login.cgi"
DSM_USERNAME = re.compile(r"[\w.@-][\w .@-]{0,127}")
SYNO_TOKEN = re.compile(r"[A-Za-z0-9._~-]{1,256}")
BACKEND_CONFIG_URL = "http://127.0.0.1:8791/api/dsm/launcher-config"
LAUNCHER_SECRET_FILE = "/var/packages/nasdownloadportal/var/dsm_launcher_secret"


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


def valid_dsm_username(value: str) -> bool:
    return DSM_USERNAME.fullmatch(value) is not None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        # A DSM session cookie must never follow a redirect to another service.
        return None


def dsm_http_port() -> int:
    try:
        with open("/etc/synoinfo.conf", encoding="utf-8") as source:
            for line in source:
                key, separator, value = line.partition("=")
                if separator and key.strip() == "adminport":
                    port = int(value.strip().strip('"\''))
                    return port if 1 <= port <= 65535 else 5000
    except (OSError, ValueError):
        pass
    return 5000


def dsm_http_get(path: str, cookie: str, token: str = "", *, limit: int = 8192) -> str:
    if not cookie or len(cookie) > 8192 or any(char in cookie for char in "\r\n\x00"):
        return ""
    if token and not SYNO_TOKEN.fullmatch(token):
        return ""
    headers = {"Cookie": cookie}
    if token:
        headers["X-Syno-Token"] = token
    url = f"http://127.0.0.1:{dsm_http_port()}{path}"
    if token:
        url += "?SynoToken=" + token
    # No environment proxy, and no redirect: keep the cookie on this DSM loopback URL.
    opener = build_opener(ProxyHandler({}), HTTPHandler(), NoRedirect())
    try:
        with opener.open(Request(url, headers=headers), timeout=5) as result:
            body = result.read(limit + 1)
        return body.decode("utf-8", "replace") if len(body) <= limit else ""
    except (HTTPError, URLError, OSError, ValueError):
        return ""


def authenticate_via_http(cookie: str, token: str = "") -> str:
    username = dsm_http_get("/webman/modules/authenticate.cgi", cookie, token, limit=512).strip()
    return username if valid_dsm_username(username) else ""


def token_from_login_output(output: str) -> str:
    start = output.find("{")
    if start < 0 or len(output) > 8192:
        return ""
    try:
        payload = json.loads(output[start:])
    except (ValueError, TypeError):
        return ""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return ""
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}
    token = payload.get("SynoToken") or data.get("SynoToken") or data.get("synotoken")
    return token if isinstance(token, str) and SYNO_TOKEN.fullmatch(token) else ""


def syno_token_via_http(cookie: str) -> str:
    return token_from_login_output(dsm_http_get("/webman/login.cgi", cookie))


def authenticate_with_env(env: dict[str, str]) -> tuple[str, list[str]]:
    outcomes = []
    for authenticator in AUTHENTICATE_CGIS:
        try:
            result = subprocess.run(
                [authenticator], capture_output=True, text=True, timeout=5, check=False, env=env,
            )
        except (OSError, subprocess.SubprocessError):
            outcomes.append("unavailable")
            continue
        username = result.stdout.strip()
        if valid_dsm_username(username):
            return username, outcomes
        outcomes.append("rejected" if username else "empty")
    return "", outcomes


def dsm_syno_token(env: dict[str, str]) -> str:
    login_env = env.copy()
    login_env["QUERY_STRING"] = ""
    login_env["REQUEST_METHOD"] = "GET"
    login_env.pop("HTTP_X_SYNO_TOKEN", None)
    try:
        result = subprocess.run(
            [LOGIN_CGI], capture_output=True, text=True, timeout=5, check=False, env=login_env,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return token_from_login_output(result.stdout)


def authenticated_admin() -> str:
    env = os.environ.copy()
    username, outcomes = authenticate_with_env(env)
    if not username and "rejected" in outcomes:
        token = dsm_syno_token(env)
        if token:
            token_env = env.copy()
            token_env["QUERY_STRING"] = "SynoToken=" + token
            token_env["HTTP_X_SYNO_TOKEN"] = token
            username, retry_outcomes = authenticate_with_env(token_env)
            outcomes.extend(retry_outcomes)
        else:
            outcomes.append("token-unavailable")
    if not username and outcomes and all(outcome in {"empty", "unavailable"} for outcome in outcomes):
        cookie = env.get("HTTP_COOKIE", "")
        username = authenticate_via_http(cookie)
        outcomes.append("http-ok" if username else "http-empty")
        if not username:
            token = syno_token_via_http(cookie)
            if token:
                username = authenticate_via_http(cookie, token)
                outcomes.append("http-token-ok" if username else "http-token-empty")
            else:
                outcomes.append("token-unavailable")
    # Synology documents stdout (username vs. no output) as the authentication
    # contract.  Its reference CGI intentionally does not use the child exit
    # status, which is not stable across DSM releases.
    if not username:
        has_id_cookie = re.search(r"(?:^|;)\s*id=", os.environ.get("HTTP_COOKIE", "")) is not None
        category = "cookie-present" if has_id_cookie else "cookie-missing"
        category += "," + "/".join(outcomes)
        fail("401 Unauthorized", f"DSM 로그인 확인에 실패했습니다 ({category}). DSM에서 다시 로그인한 뒤 NASDrop을 열어 주세요.")
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
