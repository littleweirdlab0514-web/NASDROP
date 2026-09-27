import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from urllib.error import HTTPError

import backend


SHARE = "https://x-share.net/s/Fixture123"
DIRECT = "https://x-share.net/api/download/Fixture123?key=synthetic-private-key"
PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 443))]


class Response:
    def __init__(self, name="테스트 영상.mp4", **changes):
        self.url, self.status = "https://x-share.net/api/file/Fixture123", 200
        metadata = {"id": "Fixture123", "name": name, "size": 100, "expiresAt": "2099-01-01T00:00:00Z",
                    "archivePassword": "must-not-be-copied"}
        metadata.update(changes)
        self.read = mock.Mock(return_value=json.dumps(metadata).encode())

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.url
    def close(self): pass


class XShareTests(unittest.TestCase):
    def inspect(self, opener):
        with mock.patch.object(backend, "build_opener", return_value=opener), mock.patch.object(
            backend.socket, "getaddrinfo", return_value=PUBLIC_DNS,
        ):
            return backend.inspect_payload({"url": SHARE, "resolved_url": DIRECT, "provider": "xshare"})

    def test_official_urls_and_share_only_instruction(self):
        self.assertEqual(backend.provider_for_url(SHARE), "xshare")
        self.assertEqual(backend._validate_xshare_url(SHARE, direct=False), SHARE)
        self.assertEqual(backend._validate_xshare_url(DIRECT, direct=True), DIRECT)
        with self.assertRaisesRegex(ValueError, "크롬 확장"):
            backend.inspect_download(SHARE)

    def test_host_path_key_and_share_binding(self):
        for bad in (
            DIRECT.replace("https:", "http:"), DIRECT.replace("x-share.net", "x-share.net.evil.example"),
            DIRECT.replace("https://", "https://user@"), DIRECT.replace(".net/", ".net:8443/"),
            DIRECT + "#fragment", DIRECT + "&key=duplicate", DIRECT + "&next=https://example.com",
            DIRECT.replace("synthetic-private-key", ""), DIRECT.replace("synthetic-private-key", "%0Asecret"),
            DIRECT.replace("/api/download/", "/s/"), "https://127.0.0.1/api/download/Fixture123?key=test",
            "https://x-share.net/api/download/../Fixture123?key=test",
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                backend._validate_handoff_transfer_url(bad, "xshare")
        with self.assertRaisesRegex(ValueError, "일치"):
            backend.inspect_browser_handoff(SHARE, DIRECT.replace("Fixture123", "Another123"), "xshare")

    def test_ordinary_archive_names_and_private_key(self):
        for name in ("日本語 테스트.mp4", "압축 파일.zip"):
            response = Response(name=name)
            opener = mock.Mock()
            opener.open.return_value = response
            result = self.inspect(opener)
            self.assertEqual(result["name"], name)
            self.assertEqual(result["size"], 100)
            public = backend.cache_inspection(result)
            self.assertNotIn("synthetic-private-key", str(public))
            self.assertEqual(backend.consume_inspection(public)["download_url"], DIRECT)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url, "https://x-share.net/api/file/Fixture123")
            self.assertNotIn("key=", request.full_url)
            self.assertIsNone(request.get_header("Referer"))
            self.assertIsNone(request.get_header("Cookie"))
            self.assertNotIn("must-not-be-copied", str(result))
            response.read.assert_called_once_with(128 * 1024 + 1)

    def test_keyed_transfer_is_one_body_request_without_preflight_or_referer(self):
        c = backend.Controller.__new__(backend.Controller)
        with mock.patch.object(backend.socket, "getaddrinfo", return_value=PUBLIC_DNS):
            script = c._download_script_xshare(DIRECT, "123456abcdef", 100, "/tmp/fixture", "x-share.net", "93.184.216.34")
        self.assertEqual(script.count("curl --config"), 1)
        self.assertNotIn("--range", script)
        self.assertNotIn("--retry", script)
        self.assertNotIn("referer =", script)
        self.assertIn('proxy = ""', script)
        self.assertIn('resolve = "x-share.net:443:93.184.216.34"', script)
        self.assertIn('--max-redirs 0', script)
        self.assertIn('[ "$actual" -eq 100 ]', script)

    def test_redirects_remain_first_party_and_secret_free(self):
        opener = mock.Mock()
        for target in ("https://files.example/file.zip", "https://127.0.0.1/file.zip", SHARE, DIRECT):
            opener.open.side_effect = HTTPError(DIRECT, 302, "", {"Location": target}, None)
            with self.subTest(target=target), self.assertRaises(ValueError) as caught:
                self.inspect(opener)
            self.assertNotIn("synthetic-private-key", str(caught.exception))

    def test_private_or_mixed_dns_answers_never_contacted(self):
        for addresses in (
            [(2, 1, 6, "", ("192.168.1.157", 443))],
            PUBLIC_DNS + [(2, 1, 6, "", ("127.0.0.1", 443))],
        ):
            with mock.patch.object(backend.socket, "getaddrinfo", return_value=addresses), mock.patch.object(
                backend, "build_opener",
            ) as opener, self.assertRaises(ValueError):
                backend._open_public_handoff_pinned(DIRECT, "HEAD", {})
            opener.assert_not_called()

    def test_bad_metadata_and_missing_name(self):
        for field, value in (("id", "Another123"), ("size", 0), ("size", True), ("size", backend.MAX_FILE_BYTES + 1),
                             ("name", ""), ("name", None), ("expiresAt", "2000-01-01T00:00:00Z")):
            response = Response(**{field: value})
            opener = mock.Mock()
            opener.open.return_value = response
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.inspect(opener)
        response = Response()
        response.read.return_value = b"<html>not metadata</html>"
        opener.open.return_value = response
        with self.assertRaises(ValueError):
            self.inspect(opener)
        response.read.return_value = b"x" * (128 * 1024 + 1)
        with self.assertRaises(ValueError):
            self.inspect(opener)

    def test_restart_uses_private_key_single_connection_and_dns_pin(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(backend, "SECRET_DIR", Path(temp) / "secrets"):
            c = backend.Controller.__new__(backend.Controller)
            c.lock = threading.RLock()
            c.condition = threading.Condition(c.lock)
            c.jobs, c.private_downloads, c.save = {}, {}, mock.Mock()
            file = {"url": SHARE, "name": "archive.zip", "size": 100, "provider": "xshare", "download_url": DIRECT}
            with mock.patch.object(backend, "normalize_target", return_value=temp), mock.patch.object(backend, "prepare_batch_target", return_value=temp):
                job = c.start_many([file], temp, False)[0]
            self.assertEqual(backend.load_job_download_url(job.id), DIRECT)
            self.assertNotIn("synthetic-private-key", str(backend.asdict(job)))
            c.private_downloads = {}
            c._download_script_xshare = mock.Mock(side_effect=RuntimeError("STOP-BEFORE-TRANSFER"))
            with mock.patch.object(backend.socket, "getaddrinfo", return_value=PUBLIC_DNS), self.assertRaisesRegex(RuntimeError, "STOP-BEFORE-TRANSFER"):
                c._run(job.id)
            self.assertEqual(job.transfer_mode, "single")
            self.assertEqual(c._download_script_xshare.call_args.args[0], DIRECT)
            self.assertEqual(c._download_script_xshare.call_args.args[4:], ("x-share.net", "93.184.216.34"))

    def test_transfer_headers_override_name_without_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".response-headers").write_bytes(b'HTTP/1.1 302 Found\r\nContent-Disposition: attachment; filename=wrong.bin\r\n\r\nHTTP/1.1 200 OK\r\nContent-Disposition: attachment; filename="../safe.zip"\r\n\r\n')
            artifact = root / "original.bin"
            artifact.write_bytes(b"data")
            existing = root / ".._safe.zip"
            existing.write_bytes(b"existing")
            c = backend.Controller.__new__(backend.Controller)
            c.lock, c.save = threading.RLock(), mock.Mock()
            job = backend.Job("123456abcdef", artifact.name, SHARE, 4, 4, "verifying", "now")
            result = c._apply_response_filename(job, root, artifact, {"provider": "xshare"})
            self.assertEqual(result.parent, root)
            self.assertEqual(result.suffix, ".zip")
            self.assertEqual(existing.read_bytes(), b"existing")
            self.assertFalse((root / ".response-headers").exists())

    def test_full_response_validation_rejects_error_bodies_and_strips_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            part = Path(temp) / ".fixture.segment.0"
            for content_type, allowed in (("application/octet-stream", True), ("video/mp4", True),
                                          ("application/zip", True), ("text/html", False), ("application/json", False)):
                with self.subTest(content_type=content_type):
                    part.unlink(missing_ok=True)
                    part.with_name(part.name + ".more").write_bytes(b"data")
                    part.with_name(part.name + ".headers").write_bytes(
                        f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}\r\nContent-Disposition: attachment; filename=fixture.zip\r\nSet-Cookie: secret\r\n\r\n".encode())
                    self.assertEqual(backend.commit_fragment(part, 0, 3, 4, file_response=True), allowed)
                    self.assertFalse(part.with_name(part.name + ".headers").exists())
                    if allowed:
                        self.assertEqual(part.read_bytes(), b"data")
                        self.assertNotIn(b"secret", (part.parent / ".response-headers").read_bytes())
                    else:
                        self.assertFalse(part.exists())

    def test_completed_attempt_drops_only_download_key(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(backend, "SECRET_DIR", Path(temp)):
            backend.save_job_download_url("123456abcdef", DIRECT)
            backend.save_job_password("123456abcdef", "synthetic-archive-password")
            backend.save_job_download_url("123456abcdef", "")
            self.assertEqual(backend.load_job_download_url("123456abcdef"), "")
            self.assertEqual(backend.load_job_password("123456abcdef"), "synthetic-archive-password")


if __name__ == "__main__":
    unittest.main()
