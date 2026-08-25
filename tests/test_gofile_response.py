import os
import tempfile
import time
import unittest
from email.message import Message
from urllib.error import HTTPError
from unittest.mock import patch


_state = tempfile.TemporaryDirectory(prefix="nasdrop-gofile-test-")
os.environ["NAS_PORTAL_STATE_DIR"] = _state.name

import backend
from backend import inspect_gofile, public_inspection


class GoFileResponseTest(unittest.TestCase):
    def setUp(self):
        backend.GOFILE_SESSION = None
        backend.GOFILE_LAST_REQUEST = 0
        backend.GOFILE_COOLDOWN_UNTIL = 0
        backend.GOFILE_COOLDOWN_REASON = ""
        backend.INSPECTION_CACHE.clear()
        backend.GOFILE_COOLDOWN_FILE.unlink(missing_ok=True)

    def test_first_429_trips_persistent_cooldown_without_retrying(self):
        headers = Message()
        headers["Retry-After"] = "60"
        error = HTTPError("https://api.gofile.io/test", 429, "Too Many Requests", headers, None)

        with patch("backend._json_request", side_effect=error) as request:
            with self.assertRaises(backend.GofileCooldownError):
                backend._gofile_json_request("https://api.gofile.io/test")

        request.assert_called_once()
        self.assertGreaterEqual(backend.GOFILE_COOLDOWN_UNTIL, time.time() + 29 * 60)
        saved = backend._load_gofile_cooldown()
        self.assertEqual(saved[1], "GoFile 요청 제한(HTTP 429)이 감지되었습니다.")
        self.assertGreater(saved[0], time.time())

    def test_active_cooldown_blocks_request_without_network_access(self):
        backend.GOFILE_COOLDOWN_UNTIL = time.time() + 600
        backend.GOFILE_COOLDOWN_REASON = "test"

        with patch("backend._json_request") as request:
            with self.assertRaises(backend.GofileCooldownError):
                backend._gofile_json_request("https://api.gofile.io/test")

        request.assert_not_called()

    @patch("backend._gofile_website_token", return_value="a" * 64)
    @patch("backend._json_request")
    def test_accepts_share_whose_root_object_is_the_file(self, request, _website_token):
        request.side_effect = [
            {"data": {"token": "guest-token"}},
            {
                "status": "ok",
                "data": {
                    "canAccess": True,
                    "type": "file",
                    "name": "example.bin",
                    "size": 1234,
                    "link": "https://store1.gofile.io/download/example.bin",
                },
            },
        ]

        result = inspect_gofile("https://gofile.io/d/osu4kYrK")

        self.assertEqual(result["name"], "example.bin")
        self.assertEqual(result["size"], 1234)
        self.assertEqual(result["provider"], "gofile")
        self.assertEqual(result["download_token"], "guest-token")

    @patch("backend._gofile_website_token", return_value="a" * 64)
    @patch("backend._json_request")
    def test_collects_every_file_across_pages_without_a_three_file_limit(self, request, _website_token):
        def file_item(index):
            return {
                "id": f"id-{index}", "code": f"code-{index}", "type": "file",
                "name": f"file-{index}.bin", "size": index + 1,
                "link": f"https://store1.gofile.io/download/file-{index}.bin",
            }

        first_page = {str(i): file_item(i) for i in range(100)}
        second_page = {str(i): file_item(i) for i in range(100, 125)}
        request.side_effect = [
            {"data": {"token": "guest-token"}},
            {"status": "ok", "data": {"canAccess": True, "id": "root", "type": "folder", "name": "batch", "children": first_page}},
            {"status": "ok", "data": {"canAccess": True, "id": "root", "type": "folder", "name": "batch", "children": second_page}},
        ]

        result = inspect_gofile("https://gofile.io/d/many-files")

        self.assertTrue(result["batch"])
        self.assertEqual(result["file_count"], 125)
        self.assertEqual(len(result["files"]), 125)
        self.assertEqual(result["size"], sum(range(1, 126)))
        public = public_inspection(result)
        self.assertEqual(public["file_count"], 125)
        self.assertNotIn("files", public)
        self.assertNotIn("download_token", public)

    def test_cached_inspection_is_consumed_without_a_second_provider_lookup(self):
        inspected = {
            "url": "https://gofile.io/d/folder", "name": "folder (4개 파일)",
            "size": 10, "expires": "", "provider": "gofile", "batch": True,
            "file_count": 4, "files": [{"name": "one.bin"}],
        }
        public = backend.cache_inspection(inspected)

        with patch("backend.inspect_download") as provider_lookup:
            consumed = backend.consume_inspection(public)

        self.assertIs(consumed, inspected)
        provider_lookup.assert_not_called()

    @patch("backend._gofile_website_token", return_value="a" * 64)
    @patch("backend._json_request")
    def test_preserves_nested_folder_as_a_relative_target(self, request, _website_token):
        request.side_effect = [
            {"data": {"token": "guest-token"}},
            {"status": "ok", "data": {"canAccess": True, "id": "root", "type": "folder", "name": "root", "children": {
                "folder": {"id": "folder-id", "code": "folder-code", "type": "folder", "name": "Disc 1"},
            }}},
            {"status": "ok", "data": {"canAccess": True, "id": "folder-id", "type": "folder", "name": "Disc 1", "children": {
                "file": {"id": "file-id", "code": "file-code", "type": "file", "name": "track.bin", "size": 99, "link": "https://store1.gofile.io/download/track.bin"},
            }}},
        ]

        result = inspect_gofile("https://gofile.io/d/nested")

        self.assertEqual(result["relative_path"], "Disc 1")

    def test_creates_safe_nested_batch_target(self):
        with tempfile.TemporaryDirectory(prefix="nasdrop-batch-target-") as base:
            destination = backend.prepare_batch_target(base, "Disc 1/Audio")
            self.assertTrue(os.path.isdir(destination))
            self.assertTrue(destination.endswith(os.path.join("Disc 1", "Audio")))


if __name__ == "__main__":
    unittest.main()
