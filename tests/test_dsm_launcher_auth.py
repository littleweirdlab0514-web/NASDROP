import importlib.machinery
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
from contextlib import redirect_stdout


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

    def test_rejects_empty_authentication_output(self):
        auth = SimpleNamespace(stdout="", returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", return_value=auth), mock.patch.object(
            self.launcher, "manual_login_if_configured"
        ), mock.patch.object(
            self.launcher, "fail", side_effect=RuntimeError("rejected")
        ) as fail:
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                self.launcher.authenticated_admin()
        fail.assert_called_once_with("401 Unauthorized", "DSM에 로그인한 뒤 NASDrop을 다시 열어 주세요.")

    def test_rejects_control_characters_before_group_lookup(self):
        auth = SimpleNamespace(stdout="admin\x00name\n", returncode=0)
        with mock.patch.object(self.launcher.subprocess, "run", return_value=auth), mock.patch.object(
            self.launcher, "manual_login_if_configured"
        ), mock.patch.object(
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

    def test_configured_package_falls_back_to_tokenless_manual_login(self):
        auth = SimpleNamespace(stdout="", returncode=0)
        reply = io.BytesIO(b'{"configured":true,"password_change_required":false}')
        output = io.StringIO()
        with mock.patch.object(self.launcher.subprocess, "run", return_value=auth), mock.patch.object(
            self.launcher, "urlopen", return_value=reply
        ), redirect_stdout(output):
            with self.assertRaises(SystemExit):
                self.launcher.authenticated_admin()
        self.assertIn("Status: 302 Found", output.getvalue())
        self.assertIn("Location: /webman/3rdparty/nasdownloadportal/launcher.html", output.getvalue())
        self.assertNotIn("token", output.getvalue().lower())

    def test_unconfigured_package_keeps_dsm_authentication_required(self):
        auth = SimpleNamespace(stdout="", returncode=0)
        reply = io.BytesIO(b'{"configured":false}')
        with mock.patch.object(self.launcher.subprocess, "run", return_value=auth), mock.patch.object(
            self.launcher, "urlopen", return_value=reply
        ), mock.patch.object(self.launcher, "fail", side_effect=RuntimeError("rejected")) as fail:
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                self.launcher.authenticated_admin()
        fail.assert_called_once_with("401 Unauthorized", "DSM에 로그인한 뒤 NASDrop을 다시 열어 주세요.")


if __name__ == "__main__":
    unittest.main()
