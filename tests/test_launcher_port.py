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

    def test_rendered_launcher_keeps_lan_port_and_uses_public_port(self):
        html = backend.render_launcher_html("test-token", 8795)
        self.assertIn("privateHost ? 8791 : 8795", html)
        self.assertIn('location.protocol === "https:" ? "https://" : "http://"', html)
        self.assertIn("location.replace(targetProtocol + host", html)
        self.assertNotIn('privateHost ? "http://" : "https://"', html)
        self.assertIn('var token = "test-token";', html)
        self.assertIn('encodeURIComponent(token)', html)

    def test_launcher_file_is_replaced_with_selected_port(self):
        with TemporaryDirectory() as directory:
            launcher = Path(directory) / "launcher.html"
            with patch.object(backend, "LAUNCHER_FILE", launcher):
                backend.write_launcher_file("test-token", 8795)
            contents = launcher.read_text(encoding="utf-8")
            self.assertIn("privateHost ? 8791 : 8795", contents)
            self.assertIn("location.replace(targetProtocol + host", contents)
            self.assertFalse(launcher.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main()
