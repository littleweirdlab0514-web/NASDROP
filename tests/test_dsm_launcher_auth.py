import importlib.machinery
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "synology" / "package-inner" / "ui" / "launcher.cgi"


def load_launcher():
    loader = importlib.machinery.SourceFileLoader("nasdrop_dsm_launcher", str(LAUNCHER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class DsmLauncherAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.launcher = load_launcher()

    def test_accepts_authenticated_admin_even_when_synology_exit_status_is_nonzero(self):
        auth = SimpleNamespace(stdout="admin-user\n", returncode=255)
        groups = SimpleNamespace(stdout="users administrators\n", returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", side_effect=[auth, groups]):
            self.assertEqual(self.launcher.authenticated_admin(), "admin-user")

    def test_tries_legacy_authenticator_when_primary_has_no_session(self):
        no_session = SimpleNamespace(stdout="", returncode=1)
        auth = SimpleNamespace(stdout="admin-user\n", returncode=0)
        groups = SimpleNamespace(stdout="users administrators\n", returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", side_effect=[no_session, auth, groups]) as run:
            self.assertEqual(self.launcher.authenticated_admin(), "admin-user")
        self.assertEqual(run.call_args_list[0].args[0], [self.launcher.AUTHENTICATE_CGIS[0]])
        self.assertEqual(run.call_args_list[1].args[0], [self.launcher.AUTHENTICATE_CGIS[1]])

    def test_retries_json_119_with_dsm_synotoken(self):
        rejected = SimpleNamespace(stdout='{"error":{"code":119},"success":false}', returncode=0)
        login = SimpleNamespace(stdout='Content-Type: application/json\r\n\r\n{"SynoToken":"token-123","result":"success","success":true}', returncode=0)
        auth = SimpleNamespace(stdout="admin-user\n", returncode=0)
        groups = SimpleNamespace(stdout="users administrators\n", returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", side_effect=[rejected, rejected, login, auth, groups]) as run:
            self.assertEqual(self.launcher.authenticated_admin(), "admin-user")
        self.assertEqual(run.call_args_list[2].args[0], [self.launcher.LOGIN_CGI])
        self.assertEqual(run.call_args_list[3].kwargs["env"]["QUERY_STRING"], "SynoToken=token-123")
        self.assertEqual(run.call_args_list[3].kwargs["env"]["HTTP_X_SYNO_TOKEN"], "token-123")

    def test_login_cgi_error_cannot_be_used_as_token(self):
        error = SimpleNamespace(stdout='{"error":{"code":119},"success":false}', returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", return_value=error):
            self.assertEqual(self.launcher.dsm_syno_token({"HTTP_COOKIE": "id=secret"}), "")

    def test_rejects_empty_authentication_output(self):
        auth = SimpleNamespace(stdout="", returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", return_value=auth), mock.patch.object(
            self.launcher, "fail", side_effect=RuntimeError("rejected")
        ) as fail:
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                self.launcher.authenticated_admin()
        self.assertEqual(fail.call_args.args[0], "401 Unauthorized")
        self.assertIn("cookie-missing,empty/empty/http-empty/token-unavailable", fail.call_args.args[1])

    def test_rejects_control_characters_before_group_lookup(self):
        auth = SimpleNamespace(stdout="admin\x00name\n", returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", return_value=auth), mock.patch.object(
            self.launcher, "fail", side_effect=RuntimeError("rejected")
        ):
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                self.launcher.authenticated_admin()

    def test_still_requires_dsm_administrators_group(self):
        auth = SimpleNamespace(stdout="ordinary-user\n", returncode=0)
        groups = SimpleNamespace(stdout="users\n", returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", side_effect=[auth, groups]), mock.patch.object(
            self.launcher, "fail", side_effect=RuntimeError("forbidden")
        ) as fail:
            with self.assertRaisesRegex(RuntimeError, "forbidden"):
                self.launcher.authenticated_admin()
        fail.assert_called_once_with("403 Forbidden", "DSM 관리자만 NASDrop을 열 수 있습니다.")

    def test_missing_dsm_session_never_falls_back_to_nasdrop_login(self):
        auth = SimpleNamespace(stdout="", returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", return_value=auth), mock.patch.object(
            self.launcher, "fail", side_effect=RuntimeError("rejected")
        ) as fail:
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                self.launcher.authenticated_admin()
        self.assertEqual(fail.call_args.args[0], "401 Unauthorized")
        self.assertIn("cookie-missing,empty/empty/http-empty/token-unavailable", fail.call_args.args[1])

    def test_diagnostic_reports_cookie_presence_without_disclosing_its_value(self):
        auth = SimpleNamespace(stdout="", returncode=1)
        with mock.patch.dict(self.launcher.os.environ, {"HTTP_COOKIE": "id=secret-session; other=1"}), mock.patch.object(
            self.launcher.subprocess, "run", return_value=auth
        ), mock.patch.object(self.launcher, "fail", side_effect=RuntimeError("rejected")) as fail:
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                self.launcher.authenticated_admin()
        message = fail.call_args.args[1]
        self.assertIn("cookie-present,empty/empty/http-empty/token-unavailable", message)
        self.assertNotIn("secret-session", message)

    def test_empty_subprocess_uses_http_token_and_still_checks_admin_group(self):
        empty = SimpleNamespace(stdout="", returncode=0)
        groups = SimpleNamespace(stdout="users administrators\n", returncode=0)
        with mock.patch.dict(self.launcher.os.environ, {"HTTP_COOKIE": "id=session-secret"}), mock.patch.object(
            self.launcher.subprocess, "run", side_effect=[empty, empty, groups]
        ), mock.patch.object(self.launcher, "authenticate_via_http", side_effect=["", "admin-user"]) as auth, mock.patch.object(
            self.launcher, "syno_token_via_http", return_value="safe-token"
        ):
            self.assertEqual(self.launcher.authenticated_admin(), "admin-user")
        self.assertEqual(auth.call_args_list[0].args, ("id=session-secret",))
        self.assertEqual(auth.call_args_list[1].args, ("id=session-secret", "safe-token"))

    def test_http_login_requires_success_and_supports_nested_synotoken(self):
        self.assertEqual(self.launcher.token_from_login_output('{"success":false,"data":{"SynoToken":"x"}}'), "")
        self.assertEqual(self.launcher.token_from_login_output('{"success":true,"data":{"SynoToken":"token-123"}}'), "token-123")
        self.assertEqual(self.launcher.token_from_login_output('{"success":true,"data":{"synotoken":"token-456"}}'), "token-456")

    def test_http_request_disables_proxy_and_redirect_before_forwarding_cookie(self):
        result = mock.MagicMock()
        result.__enter__.return_value.read.return_value = b"admin-user\n"
        opener = mock.Mock()
        opener.open.return_value = result
        with mock.patch.object(self.launcher, "build_opener", return_value=opener) as build, mock.patch.object(
            self.launcher, "dsm_http_port", return_value=5000
        ):
            self.assertEqual(self.launcher.authenticate_via_http("id=secret-session"), "admin-user")
        self.assertEqual(build.call_args.args[0].proxies, {})
        self.assertIsInstance(build.call_args.args[2], self.launcher.NoRedirect)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:5000/webman/modules/authenticate.cgi")
        self.assertEqual(request.get_header("Cookie"), "id=secret-session")
        self.assertIsNone(build.call_args.args[2].redirect_request(request, None, 302, "Moved", {}, "https://example.com/"))

    def test_http_request_rejects_header_injection_and_overlong_response(self):
        with mock.patch.object(self.launcher, "build_opener") as build:
            self.assertEqual(self.launcher.dsm_http_get("/webman/login.cgi", "id=bad\r\nX:evil"), "")
            build.assert_not_called()
        result = mock.MagicMock()
        result.__enter__.return_value.read.return_value = b"x" * 513
        opener = mock.Mock()
        opener.open.return_value = result
        with mock.patch.object(self.launcher, "build_opener", return_value=opener):
            self.assertEqual(self.launcher.authenticate_via_http("id=session"), "")


if __name__ == "__main__":
    unittest.main()
