import os
import tempfile
import unittest
from unittest import mock


_state = tempfile.TemporaryDirectory(prefix="nasdrop-gigafile-test-")
os.environ["NAS_PORTAL_STATE_DIR"] = _state.name

from urllib.parse import urlparse

import backend
from backend import parse_gigafile_page, service_path_id


class GigaFileBundleTest(unittest.TestCase):
    def test_inspection_resolves_masked_name_before_job_is_queued(self):
        page = b'''
          <span id="dl">&#9679;masked display name&#9679;</span>
          <script>var size = 444151760;</script>
        '''

        class Headers:
            def get_all(self, name, default=None):
                if name.lower() == "content-disposition":
                    return ["attachment; filename=legacy.avi; filename*=UTF-8''%5B%EB%B6%80%EB%B6%80%5D%20%EB%AA%85%EC%88%99%20%ED%92%80%EB%B2%84%EC%A0%84.avi"]
                return default or []

        class Response:
            def __init__(self, body=b"", headers=None):
                self.body = body
                self.headers = headers or Headers()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit=None):
                return self.body

        opener = mock.Mock()
        opener.open.side_effect = [Response(page), Response(headers=Headers())]
        with mock.patch.object(backend, "build_opener", return_value=opener):
            result = backend.inspect_gigafile("https://5.gigafile.nu/0915-j0920a222fac2576076c03ac7028ac628")

        self.assertEqual(result["name"], "[부부] 명숙 풀버전.avi")
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(opener.open.call_args_list[1].args[0].method, "HEAD")

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
