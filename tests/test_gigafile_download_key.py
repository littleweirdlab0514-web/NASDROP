import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse

import backend


class GigaFileDownloadKeyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patches = (
            mock.patch.object(backend, "SECRET_DIR", self.root / "secrets"),
            mock.patch.object(backend, "STATE_DIR", self.root),
            mock.patch.object(backend, "STATE_FILE", self.root / "jobs.json"),
            mock.patch.object(backend, "SHUTDOWN_EVENT", threading.Event()),
            mock.patch.object(backend, "normalize_target", side_effect=lambda value: value),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def controller(self):
        controller = backend.Controller.__new__(backend.Controller)
        controller.stopping = False
        controller.lock = threading.RLock()
        controller.condition = threading.Condition(controller.lock)
        controller.jobs = {}
        controller.processes = {}
        controller.private_downloads = {}
        controller.running_providers = {}
        controller.processing_job = None
        controller.postprocess_waiting = []
        return controller

    def test_page_detection_requires_both_key_input_and_protected_download_call(self):
        protected = '<input id="dlkey"><button onclick="download(file, true, false)">Download</button>'
        self.assertTrue(backend._gigafile_page_requires_download_key(protected))
        self.assertFalse(backend._gigafile_page_requires_download_key('<input id="dlkey">'))

    def test_key_is_kept_only_in_restricted_secret_file(self):
        controller = self.controller()
        job = controller.enqueue_gigafile(
            "https://38.gigafile.nu/example", "/downloads", False, "", "K-1!",
        )
        state = backend.STATE_FILE.read_text(encoding="utf-8")
        public = json.dumps(controller.public_jobs(), ensure_ascii=False)
        self.assertNotIn("K-1!", state)
        self.assertNotIn("K-1!", public)
        self.assertEqual(backend.load_job_download_key(job.id), "K-1!")
        secret_path = backend._job_secret_path(job.id)
        if os.name != "nt":
            self.assertEqual(secret_path.stat().st_mode & 0o777, 0o600)

    def test_missing_key_waits_without_automatic_retry(self):
        controller = self.controller()
        job = controller.enqueue_gigafile("https://38.gigafile.nu/example", "/downloads")
        with mock.patch.object(
            backend, "inspect_gigafile",
            side_effect=backend.GigaFileDownloadKeyRequiredError("GigaFile download key required"),
        ) as inspect:
            controller._run_guarded(job.id, "gigafile")
        self.assertEqual(inspect.call_count, 1)
        self.assertEqual(job.status, "download_key_required")
        self.assertEqual(job.not_before, 0)

    def test_wrong_key_is_removed_and_new_submission_requeues(self):
        controller = self.controller()
        job = controller.enqueue_gigafile(
            "https://38.gigafile.nu/example", "/downloads", False, "", "BAD!",
        )
        with mock.patch.object(
            backend, "inspect_gigafile",
            side_effect=backend.GigaFileDownloadKeyInvalidError("GigaFile download key rejected"),
        ):
            controller._run_guarded(job.id, "gigafile")
        self.assertEqual(job.status, "download_key_required")
        self.assertEqual(backend.load_job_download_key(job.id), "")
        controller.submit_download_key(job.id, "NEW!")
        self.assertEqual(job.status, "inspecting")
        self.assertEqual(backend.load_job_download_key(job.id), "NEW!")

    def test_download_url_is_encoded_and_not_put_on_process_argv(self):
        inspected = {
            "url": "https://38.gigafile.nu/child",
            "name": "example.zip",
            "size": 100,
            "provider": "gigafile",
            "download_url": "https://38.gigafile.nu/download.php?file=child",
        }
        result = backend._apply_gigafile_download_key(inspected, "38.gigafile.nu", "A&B!")
        query = parse_qs(urlparse(result["download_url"]).query)
        self.assertEqual(query, {"file": ["child"], "dlkey": ["A&B!"]})
        script = self.controller()._download_script(
            "38.gigafile.nu", "child", "example.zip", "abcdef012345", 100,
            str(self.root), download_url=result["download_url"],
        )
        self.assertIn('curl --config "$CURL_CONFIG"', script)
        self.assertNotIn("A&B!", script.split("curl --config", 1)[1])

    def test_key_validation_rejects_control_characters_and_excess_length(self):
        for value in ("12345", "a\nb", "a\x00b"):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                backend._validate_gigafile_download_key(value)


if __name__ == "__main__":
    unittest.main()
