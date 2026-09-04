import unittest

import backend


class DownloadModeTests(unittest.TestCase):
    def setUp(self):
        self.controller = backend.Controller.__new__(backend.Controller)

    def test_download_mode_validation(self):
        self.assertEqual(backend.normalize_download_mode("segmented"), "segmented")
        self.assertEqual(backend.normalize_download_mode(" SINGLE "), "single")
        for value in ("", "fast", None, 8):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    backend.normalize_download_mode(value)

    def test_gigafile_single_mode_uses_one_resumable_file_without_full_verification(self):
        script = self.controller._download_script(
            "example.gigafile.nu", "file-id", "movie.mkv", "abc123", 1024, "/volume1/downloads", mode="single",
        )
        self.assertIn("segment.0", script)
        self.assertIn("-C -", script)
        self.assertNotIn("COUNT=8", script)
        self.assertNotIn("sha256sum", script)
        self.assertNotIn("python3 -m zipfile", script)
        self.assertIn("--connect-timeout 15 --max-time 60", script)
        self.assertIn("--connect-timeout 10 --max-time 30", script)
        self.assertIn("--speed-limit 1024 --speed-time 120", script)

    def test_direct_single_mode_skips_segments_and_hash_even_with_expected_hash(self):
        script = self.controller._download_script_direct(
            "https://cdn.example/file", "https://example/file", "archive.zip", "abc123", 2048,
            "/volume1/downloads", expected_sha256="a" * 64, mode="single",
        )
        self.assertIn("segment.0", script)
        self.assertIn('actual=$(wc -c < "$PART"', script)
        self.assertNotIn("COUNT=8", script)
        self.assertIn("--speed-limit 1024 --speed-time 120", script)
        self.assertNotIn("sha256sum", script)
        self.assertNotIn("python3 -m zipfile", script)

    def test_segmented_mode_keeps_eight_parts_for_python_postprocessing(self):
        script = self.controller._download_script_direct(
            "https://cdn.example/file", "https://example/file", "archive.zip", "abc123", 2048,
            "/volume1/downloads", expected_sha256="a" * 64, mode="segmented",
        )
        self.assertIn("COUNT=8", script)
        self.assertIn("printf 'SEGMENTS_READY=%s\\n' \"$COUNT\"", script)
        self.assertNotIn("sha256sum", script)
        self.assertNotIn("python3 -m zipfile", script)

    def test_gigafile_child_uses_its_own_page_and_download_identifier(self):
        script = self.controller._download_script(
            "15.gigafile.nu", "1110-child", "season.zip", "abc123", 4096,
            "/volume2/downloads/.nasdrop-tmp/abc123", mode="segmented",
        )

        self.assertIn("https://15.gigafile.nu/1110-child", script)
        self.assertIn("https://15.gigafile.nu/download.php?file=1110-child", script)
        self.assertNotIn("dl_zip.php", script)

    def test_gigafile_bundle_can_skip_deep_verification(self):
        script = self.controller._download_script_gigafile_zip(
            "https://example.gigafile.nu/dl_zip.php?file=file-id", "https://example.gigafile.nu/file-id",
            "bundle.zip", "abc123", 4096, "/volume1/downloads", verify=False,
        )
        self.assertIn("segment.0", script)
        self.assertNotIn("sha256sum", script)
        self.assertNotIn("python3 -m zipfile", script)


if __name__ == "__main__":
    unittest.main()
