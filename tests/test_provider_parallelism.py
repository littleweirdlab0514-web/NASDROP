import os
import tempfile
import threading
import time
import unittest
from unittest import mock


_state = tempfile.TemporaryDirectory(prefix="nasdrop-scheduler-test-")
os.environ["NAS_PORTAL_STATE_DIR"] = _state.name

import backend
from backend import Controller, Job


class ProbeController(Controller):
    def __init__(self, provider_limit=1):
        self.started = []
        self.releases = {}
        self.test_provider_limit = provider_limit
        super().__init__()

    def load(self):
        self.jobs = {}

    def _run(self, job_id):
        with self.condition:
            self.started.append(job_id)
            self.condition.notify_all()
        self.releases[job_id].wait(timeout=5)

    def _provider_limit(self):
        return self.test_provider_limit

    def enqueue_probe(self, job_id, provider, delay=0):
        source = {
            "gigafile": "https://example.gigafile.nu/example-id",
            "gofile": "https://gofile.io/d/example",
            "pixeldrain": "https://pixeldrain.com/u/abcdefgh",
        }[provider]
        with self.condition:
            self.jobs[job_id] = Job(
                job_id, job_id, source, 1, 0, "queued", "now", "/volume2/downloads",
                not_before=time.time() + delay,
            )
            self.private_downloads[job_id] = {"provider": provider}
            self.releases[job_id] = threading.Event()
            self.condition.notify_all()

    def wait_started(self, count, timeout=3):
        deadline = time.monotonic() + timeout
        with self.condition:
            while len(self.started) < count and time.monotonic() < deadline:
                self.condition.wait(deadline - time.monotonic())
            return list(self.started)


class ProviderParallelismTest(unittest.TestCase):
    def test_disk_protection_blocks_new_downloads_while_postprocessing_is_pending(self):
        controller = ProbeController()
        job = Job("gofile-next", "next", "https://gofile.io/d/example", 1, 0, "queued", "now", "/volume2/downloads")
        controller.private_downloads[job.id] = {"provider": "gofile"}
        controller.postprocess_waiting.append("finished-job")
        with mock.patch.object(backend, "DISK_PROTECTION", True):
            self.assertFalse(controller._can_start(job))
        with mock.patch.object(backend, "DISK_PROTECTION", False):
            self.assertTrue(controller._can_start(job))

    def test_staged_job_waits_until_its_release_time(self):
        controller = ProbeController()
        controller.enqueue_probe("gofile-later", "gofile", delay=0.35)

        self.assertEqual(controller.wait_started(1, timeout=0.12), [])
        self.assertEqual(controller.wait_started(1, timeout=0.5), ["gofile-later"])
        controller.releases["gofile-later"].set()

    def test_different_providers_run_together_while_same_provider_waits(self):
        controller = ProbeController()
        controller.enqueue_probe("gofile-1", "gofile")
        controller.enqueue_probe("gofile-2", "gofile")
        controller.enqueue_probe("pixeldrain-1", "pixeldrain")

        first_wave = controller.wait_started(2)
        self.assertEqual(set(first_wave), {"gofile-1", "pixeldrain-1"})
        self.assertNotIn("gofile-2", first_wave)

        controller.releases["pixeldrain-1"].set()
        time.sleep(0.15)
        self.assertNotIn("gofile-2", controller.started)

        controller.releases["gofile-1"].set()
        self.assertIn("gofile-2", controller.wait_started(3))
        controller.releases["gofile-2"].set()

    def test_same_provider_can_run_together_when_option_is_enabled(self):
        controller = ProbeController(provider_limit=2)
        controller.enqueue_probe("gofile-1", "gofile")
        controller.enqueue_probe("gofile-2", "gofile")
        controller.enqueue_probe("gofile-3", "gofile")

        first_wave = controller.wait_started(2)
        self.assertEqual(set(first_wave), {"gofile-1", "gofile-2"})
        self.assertNotIn("gofile-3", first_wave)

        controller.releases["gofile-1"].set()
        self.assertIn("gofile-3", controller.wait_started(3))
        controller.releases["gofile-2"].set()
        controller.releases["gofile-3"].set()


if __name__ == "__main__":
    unittest.main()
