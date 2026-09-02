from email.message import Message
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import quote

import backend


FILE_ID = "i6wbczs7yfx7"
TOKEN = "signed_token_1234567890-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIRECT_URL = f"https://ts.buzzheavier.com/d/{FILE_ID}?v={TOKEN}"


class FakeHeadResponse:
    def __init__(self, url=DIRECT_URL, name="테스트 파일.zip", size=270_279_158):
        self.url = url
        self.headers = Message()
        self.headers.add_header(
            "Content-Disposition",
            f"attachment; filename=download.bin; filename*=UTF-8''{quote(name)}",
        )
        self.headers["Content-Length"] = str(size)
        self.headers["Content-Type"] = "application/zip"
        self.headers["Accept-Ranges"] = "bytes"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url


class BuzzheavierTests(unittest.TestCase):
    def test_signed_direct_link_is_inspected_without_exposing_token(self):
        opener = mock.Mock()
        opener.open.return_value = FakeHeadResponse()
        with mock.patch.object(backend, "build_opener", return_value=opener):
            inspected = backend.inspect_buzzheavier(DIRECT_URL)

        self.assertEqual(inspected["provider"], "buzzheavier")
        self.assertEqual(inspected["url"], f"https://buzzheavier.com/{FILE_ID}")
        self.assertEqual(inspected["name"], "테스트 파일.zip")
        self.assertEqual(inspected["size"], 270_279_158)
        self.assertEqual(inspected["download_url"], DIRECT_URL)
        self.assertNotIn(TOKEN, repr(backend.public_inspection(inspected)))
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "HEAD")

    def test_share_page_requires_copy_download_link(self):
        with self.assertRaisesRegex(ValueError, "Copy download link"):
            backend.inspect_download(f"https://buzzheavier.com/{FILE_ID}")

    def test_ordinary_file_name_is_available_before_queueing(self):
        opener = mock.Mock()
        opener.open.return_value = FakeHeadResponse(name="movie.mp4", size=1234)
        with mock.patch.object(backend, "build_opener", return_value=opener):
            inspected = backend.inspect_buzzheavier(DIRECT_URL)
        self.assertEqual(inspected["name"], "movie.mp4")
        self.assertEqual(inspected["size"], 1234)

    def test_missing_range_or_filename_metadata_is_rejected(self):
        response = FakeHeadResponse()
        del response.headers["Accept-Ranges"]
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(backend, "build_opener", return_value=opener), self.assertRaisesRegex(ValueError, "이어받기"):
            backend.inspect_buzzheavier(DIRECT_URL)

        response = FakeHeadResponse()
        del response.headers["Content-Disposition"]
        opener.open.return_value = response
        with mock.patch.object(backend, "build_opener", return_value=opener), self.assertRaisesRegex(ValueError, "파일 정보"):
            backend.inspect_buzzheavier(DIRECT_URL)

    def test_redirect_handler_blocks_non_buzzheavier_destination(self):
        handler = backend.BuzzheavierRedirectHandler()
        with self.assertRaisesRegex(ValueError, "허용되지 않은 서버"):
            handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1/private")

    def test_rejects_missing_token_and_lookalike_hosts(self):
        invalid = (
            f"https://ts.buzzheavier.com/d/{FILE_ID}",
            f"https://buzzheavier.com.evil.example/d/{FILE_ID}?v={TOKEN}",
            f"http://ts.buzzheavier.com/d/{FILE_ID}?v={TOKEN}",
            f"https://ts.buzzheavier.com/d/{FILE_ID}?v={TOKEN}&next=https://example.com",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                backend._validate_buzzheavier_download_url(value)

    def test_download_token_survives_password_changes_but_is_removed_at_cleanup(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(backend, "SECRET_DIR", Path(temp)):
            job_id = "0123456789ab"
            backend.save_job_download_url(job_id, DIRECT_URL)
            backend.save_job_password(job_id, "archive password")
            self.assertEqual(backend.load_job_download_url(job_id), DIRECT_URL)
            self.assertEqual(backend.load_job_password(job_id), "archive password")

            backend.delete_job_password(job_id)
            self.assertEqual(backend.load_job_download_url(job_id), DIRECT_URL)
            self.assertEqual(backend.load_job_password(job_id), "")

            backend.delete_job_secrets(job_id)
            self.assertFalse(backend._job_secret_path(job_id).exists())

    def test_buzzheavier_script_captures_headers_inside_job_workspace(self):
        controller = backend.Controller.__new__(backend.Controller)
        script = controller._download_script_direct(
            DIRECT_URL,
            f"https://buzzheavier.com/{FILE_ID}",
            "테스트 파일.zip",
            "0123456789ab",
            1024,
            "/volume2/downloads/.nasdrop-tmp/0123456789ab",
            capture_headers=True,
        )
        self.assertIn(".response-headers", script)
        self.assertIn(" -I ", script)
        self.assertIn("SEGMENTS_READY", script)

    def test_transfer_time_name_is_sanitized_and_updates_archive_name(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / ".response-headers").write_bytes(
                b"HTTP/1.1 302 Found\r\nContent-Disposition: attachment; filename=wrong.bin\r\n\r\n"
                b"HTTP/1.1 200 OK\r\nContent-Disposition: attachment; filename*=UTF-8''..%2Factual%20archive.zip\r\n\r\n"
            )
            artifact = workspace / "initial.bin"
            artifact.write_bytes(b"archive")
            job = backend.Job("0123456789ab", artifact.name, f"https://buzzheavier.com/{FILE_ID}", 7, 7, "verifying", "now")
            controller = backend.Controller.__new__(backend.Controller)
            controller.lock = backend.threading.RLock()
            controller.save = mock.Mock()

            renamed = controller._apply_response_filename(job, workspace, artifact, {"provider": "buzzheavier"})

            self.assertEqual(renamed.name, ".._actual archive.zip")
            self.assertEqual(backend.archive_kind(job.name), "zip")

    def test_provider_classification_includes_public_and_download_hosts(self):
        self.assertEqual(backend.provider_for_url(f"https://buzzheavier.com/{FILE_ID}"), "buzzheavier")
        self.assertEqual(backend.provider_for_url(DIRECT_URL), "buzzheavier")


if __name__ == "__main__":
    unittest.main()
