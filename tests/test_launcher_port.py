from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import backend


class LauncherPortTests(unittest.TestCase):
    def test_launcher_port_validation(self):
        self.assertEqual(backend.normalize_launcher_port("8795"), 8795)
        for value in ("", "0", "65536", "not-a-port", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    backend.normalize_launcher_port(value)

    def test_custom_launcher_url_accepts_https_and_normalizes_trailing_slash(self):
        self.assertEqual(
            backend.normalize_launcher_public_url("https://NASDrop.Example.com"),
            "https://nasdrop.example.com/",
        )
        self.assertEqual(
            backend.normalize_launcher_public_url("https://nasdrop.example.com:8443/portal"),
            "https://nasdrop.example.com:8443/portal/",
        )
        self.assertEqual(backend.normalize_launcher_public_url(""), "")

    def test_custom_launcher_url_rejects_unsafe_or_ambiguous_values(self):
        for value in (
            "http://nasdrop.example.com", "//nasdrop.example.com", "javascript:alert(1)",
            "https://user:pass@nasdrop.example.com", "https://nasdrop.example.com/?next=evil",
            "https://nasdrop.example.com/#fragment", "https://nasdrop.example.com\\@evil.example",
            "https://bad..example.com", "https://-bad.example.com",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    backend.normalize_launcher_public_url(value)

    def test_rendered_launcher_keeps_lan_port_and_uses_public_port(self):
        html = backend.render_launcher_html(8795)
        self.assertIn("privateHost ? 8791 : 8795", html)
        self.assertIn('location.protocol === "https:" ? "https://" : "http://"', html)
        self.assertIn("location.replace(targetProtocol + host", html)
        self.assertNotIn('privateHost ? "http://" : "https://"', html)
        self.assertNotIn("test-token", html)
        self.assertNotIn("#token=", html)

    def test_launcher_file_is_replaced_with_selected_port(self):
        with TemporaryDirectory() as directory:
            launcher = Path(directory) / "launcher.html"
            with patch.object(backend, "LAUNCHER_FILE", launcher):
                backend.write_launcher_file(8795)
            contents = launcher.read_text(encoding="utf-8")
            self.assertIn("privateHost ? 8791 : 8795", contents)
            self.assertIn("location.replace(targetProtocol + host", contents)
            self.assertNotIn("#token=", contents)
            self.assertFalse(launcher.with_suffix(".tmp").exists())

    def test_custom_launcher_url_wins_over_adaptive_host(self):
        html = backend.render_launcher_html(8795, "https://nasdrop.example.com")
        self.assertIn('var customTarget = "https://nasdrop.example.com/";', html)
        self.assertIn("if (customTarget)", html)
        self.assertIn("location.replace(customTarget)", html)

    def test_launcher_settings_are_persisted_and_written_together(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(backend, "STATE_DIR", root), \
                 patch.object(backend, "CONFIG_FILE", root / "config.json"), \
                 patch.object(backend, "LAUNCHER_FILE", root / "launcher.html"), \
                 patch.object(backend, "CONFIG", {}), \
                 patch.object(backend, "LAUNCHER_PORT", 8791), \
                 patch.object(backend, "LAUNCHER_PUBLIC_URL", ""):
                result = backend.set_launcher_settings(9443, "https://nasdrop.example.com")
                saved = __import__("json").loads((root / "config.json").read_text(encoding="utf-8"))
                launcher = (root / "launcher.html").read_text(encoding="utf-8")
            self.assertEqual(result["launcher_public_url"], "https://nasdrop.example.com/")
            self.assertEqual(saved["NAS_PORTAL_LAUNCHER_PORT"], 9443)
            self.assertEqual(saved["NAS_PORTAL_LAUNCHER_PUBLIC_URL"], "https://nasdrop.example.com/")
            self.assertIn('var customTarget = "https://nasdrop.example.com/";', launcher)


if __name__ == "__main__":
    unittest.main()
