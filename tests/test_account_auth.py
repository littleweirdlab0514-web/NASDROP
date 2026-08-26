import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import backend


class AccountAuthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="nasdrop-auth-test-")
        self.original_state_dir = backend.STATE_DIR
        self.original_auth_file = backend.AUTH_FILE
        self.original_credentials = backend.CREDENTIALS
        backend.STATE_DIR = Path(self.temporary.name)
        backend.AUTH_FILE = backend.STATE_DIR / "credentials.json"
        backend.CREDENTIALS = {}
        with backend.SESSIONS_LOCK:
            backend.SESSIONS.clear()
        with backend.LOGIN_FAILURES_LOCK:
            backend.LOGIN_FAILURES.clear()
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
        backend.CREDENTIALS = self.original_credentials
        with backend.SESSIONS_LOCK:
            backend.SESSIONS.clear()
        with backend.LOGIN_FAILURES_LOCK:
            backend.LOGIN_FAILURES.clear()
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

        status, account = self.request(
            "/api/account", method="POST", token=backend.LAUNCHER_TOKEN,
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

    def test_forwarded_client_ip_is_trusted_only_from_local_proxy(self):
        self.assertEqual(
            backend.trusted_client_ip("127.0.0.1", "198.51.100.23, 127.0.0.1"),
            "198.51.100.23",
        )
        self.assertEqual(
            backend.trusted_client_ip("192.168.1.10", "198.51.100.23"),
            "192.168.1.10",
        )
        self.assertEqual(
            backend.trusted_client_ip("127.0.0.1", "not-an-ip"),
            "127.0.0.1",
        )


if __name__ == "__main__":
    unittest.main()
