import json
import http.client
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import backend


class AccountAuthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="nasdrop-auth-test-")
        self.original_state_dir = backend.STATE_DIR
        self.original_auth_file = backend.AUTH_FILE
        self.original_token_file = backend.TOKEN_FILE
        self.original_launcher_file = backend.LAUNCHER_FILE
        self.original_launcher_token = backend.LAUNCHER_TOKEN
        self.original_credentials = backend.CREDENTIALS
        backend.STATE_DIR = Path(self.temporary.name)
        backend.AUTH_FILE = backend.STATE_DIR / "credentials.json"
        backend.TOKEN_FILE = backend.STATE_DIR / "access_token"
        backend.LAUNCHER_FILE = backend.STATE_DIR / "launcher.html"
        backend.LAUNCHER_TOKEN = backend.load_launcher_token()
        backend.CREDENTIALS = {}
        with backend.SESSIONS_LOCK:
            backend.SESSIONS.clear()
        with backend.LOGIN_FAILURES_LOCK:
            backend.LOGIN_FAILURES.clear()
        with backend.GLOBAL_LOGIN_FAILURES_LOCK:
            backend.GLOBAL_LOGIN_FAILURES.clear()
            backend.GLOBAL_LOGIN_BLOCKED_UNTIL = 0.0
        self.server = backend.ThreadingHTTPServer(("127.0.0.1", 0), backend.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        backend.STATE_DIR = self.original_state_dir
        backend.AUTH_FILE = self.original_auth_file
        backend.TOKEN_FILE = self.original_token_file
        backend.LAUNCHER_FILE = self.original_launcher_file
        backend.LAUNCHER_TOKEN = self.original_launcher_token
        backend.CREDENTIALS = self.original_credentials
        with backend.SESSIONS_LOCK:
            backend.SESSIONS.clear()
        with backend.LOGIN_FAILURES_LOCK:
            backend.LOGIN_FAILURES.clear()
        with backend.GLOBAL_LOGIN_FAILURES_LOCK:
            backend.GLOBAL_LOGIN_FAILURES.clear()
            backend.GLOBAL_LOGIN_BLOCKED_UNTIL = 0.0
        self.temporary.cleanup()

    def request(self, path, *, method="GET", payload=None, token=""):
        headers = {"content-type": "application/json"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.base + path, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_launcher_creates_account_and_direct_login_receives_session(self):
        status, payload = self.request("/api/auth/status")
        self.assertEqual((status, payload), (200, {"configured": False}))

        launcher_token = backend.LAUNCHER_TOKEN
        self.assertEqual(
            self.request("/api/account", method="POST", token=launcher_token, payload={})[0],
            401,
        )
        status, handoff = self.request(
            "/api/launcher/session", method="POST", token=launcher_token, payload={},
        )
        self.assertEqual(status, 200)
        self.assertTrue(handoff["token"])
        self.assertNotEqual(backend.LAUNCHER_TOKEN, launcher_token)
        self.assertEqual(
            self.request("/api/launcher/session", method="POST", token=launcher_token, payload={})[0],
            401,
        )

        status, account = self.request(
            "/api/account", method="POST", token=handoff["token"],
            payload={"username": "nas-owner", "password": "a strong password", "current_password": ""},
        )
        self.assertEqual(status, 200)
        self.assertEqual(account["username"], "nas-owner")
        stored = backend.AUTH_FILE.read_text(encoding="utf-8")
        self.assertNotIn("a strong password", stored)
        self.assertIn('"algorithm": "pbkdf2_sha256"', stored)

        status, logged_in = self.request(
            "/api/login", method="POST", payload={"username": "NAS-OWNER", "password": "a strong password"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(logged_in["token"])

        status, account_status = self.request("/api/account", token=logged_in["token"])
        self.assertEqual(status, 200)
        self.assertEqual(account_status["username"], "nas-owner")
        self.assertFalse(account_status["launcher_session"])
        self.assertFalse(account_status["launcher_reset_available"])

    def test_launcher_account_reset_window_expires_without_expiring_session(self):
        backend.replace_credentials("owner", "original password")
        launcher_token = backend.create_session(
            "owner", kind="launcher", ttl=backend.LAUNCHER_SESSION_TTL_SECONDS,
        )
        current = time.time()
        with backend.SESSIONS_LOCK:
            backend.SESSIONS[launcher_token] = (
                "owner", current + backend.LAUNCHER_SESSION_TTL_SECONDS, "launcher",
                current - backend.LAUNCHER_ACCOUNT_RESET_WINDOW_SECONDS - 1,
            )
        self.assertEqual(backend.session_kind(launcher_token), "launcher")
        self.assertFalse(backend.launcher_account_reset_allowed(launcher_token))
        status, account = self.request("/api/account", token=launcher_token)
        self.assertEqual(status, 200)
        self.assertFalse(account["launcher_reset_available"])
        status, _ = self.request(
            "/api/account", method="POST", token=launcher_token,
            payload={"username": "owner", "password": "replacement password", "current_password": ""},
        )
        self.assertEqual(status, 400)

    def test_session_registry_is_bounded_and_oldest_session_is_evicted(self):
        with mock.patch.object(backend.time, "time", side_effect=range(1, backend.MAX_SESSION_ENTRIES + 3)):
            first = backend.create_session("owner")
            for _ in range(backend.MAX_SESSION_ENTRIES):
                backend.create_session("owner")
        self.assertLessEqual(len(backend.SESSIONS), backend.MAX_SESSION_ENTRIES)
        self.assertNotIn(first, backend.SESSIONS)

    def test_session_password_change_requires_current_password_and_revokes_old_session(self):
        backend.replace_credentials("owner", "original password")
        old_token = backend.create_session("owner")

        status, _ = self.request(
            "/api/account", method="POST", token=old_token,
            payload={"username": "owner", "password": "replacement password", "current_password": "wrong password"},
        )
        self.assertEqual(status, 400)

        status, changed = self.request(
            "/api/account", method="POST", token=old_token,
            payload={"username": "owner", "password": "replacement password", "current_password": "original password"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(changed["token"])
        self.assertNotEqual(changed["token"], old_token)
        self.assertEqual(self.request("/api/account", token=old_token)[0], 401)
        self.assertEqual(self.request("/api/account", token=changed["token"])[0], 200)

    def test_validation_and_login_rate_limit(self):
        for username in ("ab", "spaces are invalid", "x" * 33):
            with self.subTest(username=username):
                with self.assertRaises(ValueError):
                    backend.normalize_username(username)
        for password in ("short", "contains\nnewline", "x" * 129):
            with self.subTest(password=password):
                with self.assertRaises(ValueError):
                    backend.validate_password(password)

        for _ in range(backend.LOGIN_FAILURE_LIMIT):
            backend.record_login_result("192.0.2.1", False)
        self.assertGreater(backend.login_block_remaining("192.0.2.1"), 0)
        backend.record_login_result("192.0.2.1", True)
        self.assertEqual(backend.login_block_remaining("192.0.2.1"), 0)

        self.assertFalse(backend.verify_credentials("테스트", "irrelevant password"))

    def test_login_failure_entries_are_bounded_and_expire(self):
        for index in range(backend.MAX_LOGIN_FAILURE_ENTRIES + 20):
            backend.record_login_result(f"198.51.{index // 256}.{index % 256}", False)
        self.assertLessEqual(len(backend.LOGIN_FAILURES), backend.MAX_LOGIN_FAILURE_ENTRIES)
        with backend.LOGIN_FAILURES_LOCK:
            backend.LOGIN_FAILURES["192.0.2.44"] = (
                1, 0, time.time() - backend.LOGIN_FAILURE_RETENTION_SECONDS - 1,
            )
        backend.login_block_remaining("192.0.2.45")
        self.assertNotIn("192.0.2.44", backend.LOGIN_FAILURES)

    def test_distributed_failures_trigger_only_short_global_throttle(self):
        with mock.patch.object(backend.time, "time", return_value=1000.0):
            for _ in range(backend.GLOBAL_LOGIN_FAILURE_LIMIT):
                backend.record_global_login_failure()
            self.assertEqual(
                backend.global_login_retry_after(),
                backend.GLOBAL_LOGIN_COOLDOWN_SECONDS,
            )

        with mock.patch.object(
            backend.time,
            "time",
            return_value=1000.0 + backend.GLOBAL_LOGIN_COOLDOWN_SECONDS + 1,
        ):
            self.assertEqual(backend.global_login_retry_after(), 0)

    def test_forwarded_client_ip_is_trusted_only_from_local_proxy(self):
        self.assertEqual(
            backend.trusted_client_ip("127.0.0.1", "198.51.100.23, 127.0.0.1"),
            "127.0.0.1",
        )
        self.assertEqual(
            backend.trusted_client_ip(
                "127.0.0.1", "198.51.100.23, 203.0.113.9", trust_forwarded=True,
            ),
            "203.0.113.9",
        )
        self.assertEqual(
            backend.trusted_client_ip("192.168.1.10", "198.51.100.23"),
            "192.168.1.10",
        )
        self.assertEqual(
            backend.trusted_client_ip("127.0.0.1", "not-an-ip", trust_forwarded=True),
            "127.0.0.1",
        )

    def test_disabled_proxy_mode_warns_once_when_loopback_forwards_clients(self):
        with mock.patch.object(backend, "TRUST_FORWARDED_FOR", False), \
             mock.patch.object(backend, "UNTRUSTED_FORWARDED_HEADER_SEEN", False), \
             mock.patch.object(backend, "UNTRUSTED_FORWARDED_HEADER_WARNED", False), \
             self.assertLogs(backend.LOGGER, level="WARNING") as logs:
            backend.note_forwarded_header("127.0.0.1", "198.51.100.7")
            backend.note_forwarded_header("127.0.0.1", "198.51.100.8")
            self.assertTrue(backend.UNTRUSTED_FORWARDED_HEADER_SEEN)
        self.assertEqual(sum("share one login-throttle bucket" in line for line in logs.output), 1)

    def test_reverse_proxy_setting_is_persisted_and_applies_immediately(self):
        config_file = backend.STATE_DIR / "proxy-config.json"
        with mock.patch.object(backend, "CONFIG_FILE", config_file), \
             mock.patch.object(backend, "CONFIG", {}), \
             mock.patch.object(backend, "TRUST_FORWARDED_FOR", False), \
             mock.patch.object(backend, "UNTRUSTED_FORWARDED_HEADER_SEEN", True), \
             mock.patch.object(backend, "UNTRUSTED_FORWARDED_HEADER_WARNED", True):
            self.assertTrue(backend.set_reverse_proxy_setting(True))
            self.assertTrue(backend.TRUST_FORWARDED_FOR)
            self.assertFalse(backend.UNTRUSTED_FORWARDED_HEADER_SEEN)
            self.assertEqual(
                backend.trusted_client_ip("127.0.0.1", "203.0.113.1, 198.51.100.9"),
                "198.51.100.9",
            )
            self.assertTrue(json.loads(config_file.read_text(encoding="utf-8"))["NAS_PORTAL_TRUST_FORWARDED_FOR"])
        with self.assertRaises(ValueError):
            backend.set_reverse_proxy_setting("true")

    def test_query_strings_route_to_json_api(self):
        backend.replace_credentials("owner", "original password")
        token = backend.create_session("owner")
        status, payload = self.request("/api/status?cache=1", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(payload["version"], backend.PACKAGE_VERSION)
        self.assertEqual(self.request("/api/missing?cache=1", token=token)[0], 404)

    def test_api_errors_include_stable_localization_codes(self):
        status, payload = self.request("/api/status")
        self.assertEqual(status, 401)
        self.assertEqual(payload["code"], "auth_required")
        self.assertEqual(backend.public_error_code("정식 GigaFile HTTPS 링크가 아닙니다."), "invalid_link")
        self.assertEqual(
            backend.public_error_code("ID는 영문, 숫자, 마침표, 밑줄, 하이픈을 사용해 3~32자로 입력하세요."),
            "invalid_username",
        )
        self.assertEqual(backend.public_error_code("비밀번호는 10~128자로 입력하세요."), "invalid_password")

    def test_login_throttle_error_includes_localizable_remaining_minutes(self):
        backend.replace_credentials("owner", "original password")
        for _ in range(backend.LOGIN_FAILURE_LIMIT):
            backend.record_login_result("127.0.0.1", False)
        status, payload = self.request(
            "/api/login", method="POST",
            payload={"username": "owner", "password": "original password"},
        )
        self.assertEqual(status, 429)
        self.assertEqual(payload["code"], "too_many_attempts")
        self.assertGreaterEqual(payload["params"]["minutes"], 1)

    def test_negative_and_oversized_content_lengths_are_rejected(self):
        for length in (-1, backend.REQUEST_BODY_LIMIT + 1):
            with self.subTest(length=length):
                connection = http.client.HTTPConnection(
                    "127.0.0.1", self.server.server_port, timeout=3,
                )
                connection.putrequest("POST", "/api/login")
                connection.putheader("Content-Type", "application/json")
                connection.putheader("Content-Length", str(length))
                connection.endheaders()
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
                connection.close()


if __name__ == "__main__":
    unittest.main()
