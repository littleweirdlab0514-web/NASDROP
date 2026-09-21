import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import backend


class AsyncInspectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name, value in [('STATE_FILE', self.root / 'jobs.json'), ('STATE_DIR', self.root),
                            ('SHUTDOWN_EVENT', threading.Event())]:
            patcher = mock.patch.object(backend, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in ('normalize_target', 'prepare_batch_target'):
            patcher = mock.patch.object(backend, name, side_effect=lambda value, *args: value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in ('save_job_password', 'delete_job_secrets'):
            patcher = mock.patch.object(backend, name)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(backend, 'load_job_password', return_value='synthetic-secret')
        patcher.start()
        self.addCleanup(patcher.stop)
        c = backend.Controller.__new__(backend.Controller)
        c.stopping = False
        c.lock = threading.RLock()
        c.condition = threading.Condition(c.lock)
        c.jobs, c.processes, c.private_downloads, c.running_providers = {}, {}, {}, {}
        c.processing_job, c.postprocess_waiting = None, []
        self.c = c
        self.url = 'https://123.gigafile.nu/1231-abcdef'

    def enqueue(self):
        return self.c.enqueue_gigafile(self.url, '/downloads', True, 'synthetic-secret')

    def files(self):
        return [{'provider': 'gigafile', 'url': self.url + str(i), 'name': name,
                 'size': 8, 'download_url': 'https://123.gigafile.nu/download.php?file=test'}
                for i, name in enumerate(['video.mp4', 'archive.zip'])]

    def test_enqueue_is_persisted_without_provider_request_or_password_in_state(self):
        with mock.patch.object(backend, 'inspect_gigafile') as inspect:
            job = self.enqueue()
            inspect.assert_not_called()
        self.assertEqual(job.status, 'inspecting')
        self.assertTrue(job.inspection_pending)
        state = backend.STATE_FILE.read_text()
        self.assertNotIn('synthetic-secret', state)
        self.assertEqual(json.loads(state)[0]['id'], job.id)

    def test_batch_replaces_placeholder_once_preserving_destination_and_options(self):
        job = self.enqueue()
        with mock.patch.object(backend, 'inspect_gigafile', return_value={'batch': True, 'files': self.files()}):
            self.c._resolve_queued_link(job.id)
        self.assertNotIn(job.id, self.c.jobs)
        self.assertEqual(len(self.c.jobs), 2)
        for child in self.c.jobs.values():
            self.assertEqual(child.target, '/downloads')
            self.assertFalse(child.inspection_pending)
            self.assertTrue(child.extract)
        self.assertEqual(len(json.loads(backend.STATE_FILE.read_text())), 2)

    def test_pause_during_lookup_cannot_publish_children(self):
        job = self.enqueue()
        self.c.running_providers = {'gigafile': {job.id}}
        def lookup(_):
            self.c.pause(job.id)
            with self.assertRaises(ValueError):
                self.c.resume(job.id)
            return {'batch': True, 'files': self.files()}
        with mock.patch.object(backend, 'inspect_gigafile', side_effect=lookup):
            self.c._run_guarded(job.id, 'gigafile')
        self.assertEqual(job.status, 'paused')
        self.assertEqual(len(self.c.jobs), 1)
        self.c.resume(job.id)
        self.assertEqual(job.status, 'inspecting')

    def test_restart_retains_pending_link_as_resumable_paused_job(self):
        job = self.enqueue()
        self.c.jobs = {}
        self.c.load()
        restored = self.c.jobs[job.id]
        self.assertEqual(restored.status, 'paused')
        self.assertTrue(restored.inspection_pending)
        self.c.resume(job.id)
        self.assertEqual(restored.status, 'inspecting')

    def test_lookup_failure_is_visible_and_retryable(self):
        job = self.enqueue()
        with mock.patch.object(backend, 'inspect_gigafile', side_effect=TimeoutError('lookup timed out')):
            self.c._run_guarded(job.id, 'gigafile')
        self.assertEqual(job.status, 'failed')
        self.c.resume(job.id)
        self.assertEqual(job.status, 'inspecting')

    def test_failed_expansion_preserves_placeholder(self):
        job = self.enqueue()
        with mock.patch.object(backend, 'inspect_gigafile', return_value={'batch': True, 'files': self.files()}), mock.patch.object(self.c, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.c._resolve_queued_link(job.id)
        self.assertEqual(list(self.c.jobs), [job.id])
        self.assertEqual(len(json.loads(backend.STATE_FILE.read_text())), 1)

    def test_rejects_untrusted_urls_before_network(self):
        for url in ('http://123.gigafile.nu/x', 'https://localhost/x',
                    'https://123.gigafile.nu.evil/x', 'https://u:p@123.gigafile.nu/x',
                    'https://123.gigafile.nu:8443/x'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.c.enqueue_gigafile(url, '/downloads')
