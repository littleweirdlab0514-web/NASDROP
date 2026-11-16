from email.message import Message
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import quote

import backend


FILE_ID = "123e4567-e89b-42d3-a456-426614174000"
OTHER_ID = "123e4567-e89b-42d3-a456-426614174001"
SHARE = f"https://myapexdrive.com/file/{FILE_ID}"
SIGNATURE = "AbCdEfghijklmnop+/0123456789=="


def direct(file_id=FILE_ID, verify=None, filename="테스트 영상.mp4"):
    verify = f"{int(time.time()) + 3600}-{SIGNATURE}" if verify is None else verify
    return (
        f"https://d.linatalksbayou.com/xbox-apex/987654/{file_id}.mp4"
        f"?verify={quote(verify, safe='')}&fn={quote(filename, safe='')}"
    )


class Response:
    def __init__(self, url, filename="테스트 영상.mp4"):
        self.url, self.status = url, 200
        self.headers = Message()
        self.headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(filename)
        self.headers["Content-Length"] = "100"
        self.headers["Content-Type"] = "video/mp4"
        self.headers["Accept-Ranges"] = "bytes"

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.url


class ApexDriveTests(unittest.TestCase):
    def test_canonical_share_and_exact_signed_direct_url(self):
        self.assertEqual(backend.provider_for_url(SHARE), "apexdrive")
        self.assertEqual(backend._validate_apexdrive_url(SHARE, direct=False), SHARE)
        self.assertEqual(backend._validate_apexdrive_url(direct(), direct=True), direct())
        for bad in (
            SHARE + "?x=1", SHARE.replace("https:", "http:"),
            direct().replace("d.linatalksbayou.com", "d.linatalksbayou.com.evil.example"),
            direct().replace("/xbox-apex/987654/", "/other/987654/"),
            direct().replace("?verify=", "?extra=1&verify="),
            direct() + "&verify=duplicate", direct().replace("&fn=", "&other="),
            direct(verify="short"),
            direct(filename="../unsafe.mp4"), direct(filename="not-video.zip"),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                backend.inspect_browser_handoff(SHARE, bad, "apexdrive")

    def test_verify_is_opaque_and_rejects_blank_control_and_oversize_values(self):
        now = 2_000_000_000
        with mock.patch.object(backend.time, "time", return_value=now):
            for opaque in (
                f"{now + 300}-{SIGNATURE}",
                f"{now - 3600}-{SIGNATURE}",
                "provider-defined-token-without-a-timestamp",
                "opaque:value.with~symbols+/=",
            ):
                value = direct(verify=opaque)
                self.assertEqual(backend._validate_apexdrive_url(value, direct=True), value)
            for bad in (
                direct(verify=""),
                direct(verify="contains space"),
                direct(verify="contains\nnewline"),
                direct(verify="A" * 4097),
                direct(verify=f"{now + 300}-{SIGNATURE}") + "&verify=duplicate",
            ):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    backend._validate_apexdrive_url(bad, direct=True)

    def test_share_and_delivery_uuids_are_independent(self):
        url = direct(OTHER_ID)
        with mock.patch.object(backend, "_open_public_handoff_pinned", return_value=Response(url)):
            self.assertEqual(backend.inspect_browser_handoff(SHARE, url, "apexdrive")["size"], 100)

    def test_inspection_uses_safe_fn_without_exposing_signature(self):
        url = direct(filename="공식 이름.mp4")
        with mock.patch.object(backend, "_open_public_handoff_pinned", return_value=Response(url, "공식 이름.mp4")) as opened:
            result = backend.inspect_payload({"url": SHARE, "resolved_url": url, "provider": "apexdrive"})
        self.assertEqual(result["url"], SHARE)
        self.assertEqual(result["name"], "공식 이름.mp4")
        self.assertEqual(result["size"], 100)
        self.assertEqual(result["provider"], "apexdrive")
        self.assertNotIn(SIGNATURE, str(backend.public_inspection(result)))
        self.assertEqual(opened.call_args.args[1], "HEAD")

    def test_content_disposition_is_required_and_authoritative(self):
        url = direct(filename="expected.mp4")
        missing = Response(url, "expected.mp4")
        del missing.headers["Content-Disposition"]
        with mock.patch.object(backend, "_open_public_handoff_pinned", return_value=missing), self.assertRaises(ValueError):
            backend.inspect_browser_handoff(SHARE, url, "apexdrive")
        with mock.patch.object(backend, "_open_public_handoff_pinned", return_value=Response(url, "other.mp4")):
            result = backend.inspect_browser_handoff(SHARE, url, "apexdrive")
        self.assertEqual(result["name"], "other.mp4")

    def test_signed_url_is_memory_only_and_single_transfer_is_dns_pinned(self):
        url = direct()
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(backend, "SECRET_DIR", Path(temp) / "secrets"):
            controller = backend.Controller.__new__(backend.Controller)
            controller.lock = threading.RLock()
            controller.condition = threading.Condition(controller.lock)
            controller.jobs, controller.private_downloads = {}, {}
            controller.save = mock.Mock()
            file = {"url": SHARE, "name": "테스트 영상.mp4", "size": 100,
                    "provider": "apexdrive", "download_url": url}
            with mock.patch.object(backend, "normalize_target", return_value=temp), \
                 mock.patch.object(backend, "prepare_batch_target", return_value=temp):
                job = controller.start_many([file], temp, False)[0]
            self.assertEqual(backend.load_job_download_url(job.id), "")
            self.assertFalse((Path(temp) / "secrets" / f"{job.id}.json").exists())
            self.assertNotIn(SIGNATURE, str(backend.asdict(job)))

            controller._download_script_direct = mock.Mock(side_effect=RuntimeError("STOP-BEFORE-TRANSFER"))
            with mock.patch.object(
                backend.socket, "getaddrinfo",
                return_value=[(2, 1, 6, "", ("93.184.216.34", 443))],
            ), self.assertRaisesRegex(RuntimeError, "STOP-BEFORE-TRANSFER"):
                controller._run(job.id)
            self.assertEqual(job.transfer_mode, "single")
            self.assertEqual(controller._download_script_direct.call_args.args[0], url)
            self.assertEqual(controller._download_script_direct.call_args.kwargs["resolve_host"], "d.linatalksbayou.com")
            self.assertEqual(controller._download_script_direct.call_args.kwargs["resolve_address"], "93.184.216.34")

            controller.private_downloads = {}
            with self.assertRaisesRegex(ValueError, "공식 Download"):
                controller._run(job.id)


if __name__ == "__main__":
    unittest.main()
