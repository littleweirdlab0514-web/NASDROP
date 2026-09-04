import os
import tempfile
import unittest
from unittest import mock


_state = tempfile.TemporaryDirectory(prefix="nasdrop-gigafile-test-")
os.environ["NAS_PORTAL_STATE_DIR"] = _state.name

from urllib.parse import urlparse

import backend
from backend import is_gigafile_fallback_name, parse_gigafile_page, service_path_id


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

    def test_current_multi_file_page_queues_individual_downloads(self):
        file_id = "1130-2f2108602e74e6f046ef2343c37f2ecb"
        source = '''
          <span id="matomete_zip_filename">gigafile-1130-test.zip</span>
          <span class="download_term_value">2026-11-30</span>
          <script>var files = [
            {"file":"1130-a", "size":123, "bypasses":[]},
            {"file":"1130-b", "size":456, "bypasses":[]}
          ];</script>
          <span class="matomete_file_name ">first.zip</span>
          <span class="matomete_file_name ">second.zip</span>
        '''

        result = parse_gigafile_page(source, f"https://83.gigafile.nu/{file_id}", "83.gigafile.nu", file_id)

        self.assertEqual(result["name"], "GigaFile ×2")
        self.assertEqual(result["size"], 579)
        self.assertTrue(result["batch"])
        self.assertEqual(result["file_count"], 2)
        self.assertEqual([item["name"] for item in result["files"]], ["first.zip", "second.zip"])
        self.assertTrue(all(item["download_mode"] == "gigafile_file" for item in result["files"]))
        self.assertEqual(result["files"][0]["download_url"], "https://83.gigafile.nu/download.php?file=1130-a")

    def test_multi_file_names_allow_attribute_order_quotes_and_extra_classes(self):
        source = '''
          <script>var files = [
            {"file":"1130-a", "size":123},
            {"file":"1130-b", "size":456}
          ];</script>
          <span id='first' class='row matomete_file_name active'>first.zip</span>
          <span data-kind="file" class="matomete_file_name row">second.zip</span>
        '''

        result = parse_gigafile_page(source, "https://83.gigafile.nu/parent", "83.gigafile.nu", "parent")

        self.assertEqual([item["name"] for item in result["files"]], ["first.zip", "second.zip"])

    def test_invalid_null_size_is_reported_as_gigafile_metadata_error(self):
        source = '''
          <script>var files = [{"file":"1130-a", "size":null}];</script>
          <span class="matomete_file_name">first.zip</span>
        '''

        with self.assertRaisesRegex(ValueError, "GigaFile 개별 파일 정보"):
            parse_gigafile_page(source, "https://83.gigafile.nu/parent", "83.gigafile.nu", "parent")

    def test_batch_total_may_exceed_single_file_limit(self):
        each = backend.MAX_FILE_BYTES - 1
        source = f'''
          <script>var files = [
            {{"file":"1130-a", "size":{each}}},
            {{"file":"1130-b", "size":{each}}}
          ];</script>
          <span class="matomete_file_name">first.zip</span>
          <span class="matomete_file_name">second.zip</span>
        '''

        result = parse_gigafile_page(source, "https://83.gigafile.nu/parent", "83.gigafile.nu", "parent")

        self.assertTrue(result["batch"])
        self.assertGreater(result["size"], backend.MAX_FILE_BYTES)

    def test_batch_names_are_replaced_with_download_response_names(self):
        inspected = {
            "files": [
                {"url": "https://83.gigafile.nu/a", "download_url": "https://83.gigafile.nu/download.php?file=a", "name": "●ファイル名が置換されました●", "size": 123},
                {"url": "https://83.gigafile.nu/b", "download_url": "https://83.gigafile.nu/download.php?file=b", "name": "page-name.zip", "size": 456},
            ]
        }

        def probe(item, _host, _cookie):
            return ("actual-a.zip", 123) if item["size"] == 123 else ("actual-b.zip", 456)

        with mock.patch.object(backend, "_probe_gigafile_file", side_effect=probe):
            result = backend.resolve_gigafile_batch_names(inspected, "83.gigafile.nu", backend.CookieJar())

        self.assertEqual([item["name"] for item in result["files"]], ["actual-a.zip", "actual-b.zip"])

    def test_masked_batch_name_falls_back_safely_when_probe_fails(self):
        inspected = {
            "files": [{
                "url": "https://83.gigafile.nu/a",
                "download_url": "https://83.gigafile.nu/download.php?file=a",
                "name": "●ファイル名が置換されました※DLしたファイルは、原題まま表示されます。●",
                "size": 123,
            }]
        }

        with mock.patch.object(backend, "_probe_gigafile_file", side_effect=OSError("offline")):
            result = backend.resolve_gigafile_batch_names(inspected, "83.gigafile.nu", backend.CookieJar())

        self.assertEqual(result["files"][0]["name"], "GigaFile a")
        self.assertNotIn("ファイル名が置換されました", result["files"][0]["name"])
        self.assertTrue(is_gigafile_fallback_name(result["files"][0]["name"], result["files"][0]["url"]))

    def test_only_the_matching_child_id_is_accepted_as_a_restart_fallback(self):
        source = "https://83.gigafile.nu/1130-child"
        self.assertTrue(is_gigafile_fallback_name("GigaFile 1130-child", source))
        self.assertFalse(is_gigafile_fallback_name("GigaFile another-child", source))

    def test_current_single_item_page_selects_individual_file_not_bundle_zip(self):
        file_id = "1024-parent"
        source = '''
          <span id="matomete_zip_filename">gigafile-1024-parent.zip</span>
          <script>var files = [{"file":"1024-child", "size":321, "bypasses":[]}];</script>
          <span class="matomete_file_name ">actual-name.zip</span>
        '''

        result = parse_gigafile_page(source, f"https://121.gigafile.nu/{file_id}", "121.gigafile.nu", file_id)

        self.assertNotIn("batch", result)
        self.assertEqual(result["name"], "actual-name.zip")
        self.assertEqual(result["download_mode"], "gigafile_file")
        self.assertEqual(result["download_url"], "https://121.gigafile.nu/download.php?file=1024-child")

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
