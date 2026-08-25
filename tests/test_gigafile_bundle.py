import os
import tempfile
import unittest
from unittest.mock import patch


_state = tempfile.TemporaryDirectory(prefix="nasdrop-gigafile-test-")
os.environ["NAS_PORTAL_STATE_DIR"] = _state.name

from urllib.parse import urlparse

from backend import (
    _content_disposition_filename,
    _gigafile_original_name,
    _is_gigafile_masked_name,
    inspect_gigafile,
    parse_gigafile_page,
    service_path_id,
)


class _FakeResponse:
    def __init__(self, disposition="", body=b""):
        self.headers = {"Content-Disposition": disposition}
        self.body = body

    def read(self, _limit=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return self.responses.pop(0)


class GigaFileBundleTest(unittest.TestCase):
    def test_accepts_current_bundle_identifier_and_parses_zip(self):
        file_id = "1130-2f2108602e74e6f046ef2343c37f2ecb"
        source = '''
          <span id="matomete_zip_filename">gigafile-1130-test.zip</span>
          <span class="download_term_value">2026-11-30</span>
          <script>var files = [
            {"file":"1130-a", "size":123, "bypasses":[]},
            {"file":"1130-b", "size":456, "bypasses":[]}
          ];</script>
        '''

        result = parse_gigafile_page(source, f"https://83.gigafile.nu/{file_id}", "83.gigafile.nu", file_id)

        self.assertEqual(result["name"], "gigafile-1130-test.zip")
        self.assertEqual(result["size"], 579)
        self.assertEqual(result["download_mode"], "gigafile_zip")
        self.assertEqual(result["download_url"], f"https://83.gigafile.nu/dl_zip.php?file={file_id}")

    def test_existing_single_file_format_still_parses(self):
        file_id = "1130-b10ef056a1efe7012d3d9f27b3ca35885"
        source = '''
          <span id="dl">example.zip</span>
          <span class="download_term_value">tomorrow</span>
          <script>var size = 789;</script>
        '''

        result = parse_gigafile_page(source, f"https://83.gigafile.nu/{file_id}", "83.gigafile.nu", file_id)

        self.assertEqual(result["size"], 789)
        self.assertEqual(result["download_mode"], "gigafile_file")
        self.assertIn("/download.php?file=", result["download_url"])

    def test_detects_gigafile_filename_replacement_notice(self):
        notice = "●ファイル名が置換されました※DLしたファイルは、原題まま表示されます。●"
        self.assertTrue(_is_gigafile_masked_name(notice))
        self.assertFalse(_is_gigafile_masked_name("ordinary archive.zip"))

    def test_prefers_utf8_content_disposition_filename(self):
        disposition = "attachment; filename=masked.mp4; filename*=UTF-8''%ED%85%8C%EC%8A%A4%ED%8A%B8%20%EC%98%81%EC%83%81.mp4"
        self.assertEqual(_content_disposition_filename(disposition), "테스트 영상.mp4")

    def test_reads_original_name_with_only_a_one_byte_range_request(self):
        opener = _FakeOpener(_FakeResponse("attachment; filename*=UTF-8''original%20name.zip"))
        file_id = "0828-e81d60f12666e719a4034713d775b68ec"

        name = _gigafile_original_name(opener, f"https://127.gigafile.nu/{file_id}", "127.gigafile.nu", file_id)

        self.assertEqual(name, "original name.zip")
        self.assertEqual(len(opener.requests), 1)
        request, timeout = opener.requests[0]
        self.assertEqual(request.get_header("Range"), "bytes=0-0")
        self.assertEqual(request.get_header("Referer"), f"https://127.gigafile.nu/{file_id}")
        self.assertEqual(timeout, 30)

    def test_rejects_missing_original_filename(self):
        opener = _FakeOpener(_FakeResponse())
        with self.assertRaisesRegex(ValueError, "원본 파일명"):
            _gigafile_original_name(opener, "https://127.gigafile.nu/example", "127.gigafile.nu", "example")

    def test_normal_page_name_does_not_make_an_extra_request(self):
        page = b'<span id="dl">ordinary.zip</span><script>var size = 789;</script>'
        opener = _FakeOpener(_FakeResponse(body=page))

        with patch("backend.build_opener", return_value=opener):
            result = inspect_gigafile("https://127.gigafile.nu/example")

        self.assertEqual(result["name"], "ordinary.zip")
        self.assertEqual(len(opener.requests), 1)

    def test_masked_page_name_makes_one_small_filename_request(self):
        notice = "●ファイル名が置換されました※DLしたファイルは、原題まま表示されます。●"
        page = f'<span id="dl">{notice}</span><script>var size = 789;</script>'.encode()
        opener = _FakeOpener(
            _FakeResponse(body=page),
            _FakeResponse("attachment; filename*=UTF-8''restored%20name.zip"),
        )

        with patch("backend.build_opener", return_value=opener):
            result = inspect_gigafile("https://127.gigafile.nu/example")

        self.assertEqual(result["name"], "restored name.zip")
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(opener.requests[1][0].get_header("Range"), "bytes=0-0")

    def test_service_id_is_not_tied_to_a_provider_length_rule(self):
        future_id = "A-1_future.identifier~with-a-different-length"
        self.assertEqual(service_path_id(urlparse(f"https://example.invalid/{future_id}")), future_id)
        self.assertEqual(service_path_id(urlparse(f"https://example.invalid/u/{future_id}"), "u"), future_id)

    def test_service_path_still_rejects_unsafe_or_ambiguous_paths(self):
        with self.assertRaises(ValueError):
            service_path_id(urlparse("https://example.invalid/one/two"))
        with self.assertRaises(ValueError):
            service_path_id(urlparse("https://example.invalid/%2Fetc%2Fpasswd"))


if __name__ == "__main__":
    unittest.main()
