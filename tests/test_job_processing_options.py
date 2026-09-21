import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import backend


class JobProcessingOptionsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patcher = mock.patch.object(backend, 'SECRET_DIR', self.root / 'secrets')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.c = backend.Controller.__new__(backend.Controller)
        self.c.lock = threading.RLock()
        self.c.condition = threading.Condition(self.c.lock)
        self.c.stopping = False
        self.c.processing_job = None
        self.c.running_providers = {}
        self.c.private_downloads = {}
        self.c.save = mock.Mock()
        self.job = backend.Job('abcdef123456', 'archive.zip', 'https://example.com/file', 4, 4,
                               'queued', 'now', target=str(self.root))
        self.c.jobs = {self.job.id: self.job}
        backend.save_job_password(self.job.id, 'synthetic-old')
        backend.save_job_download_url(self.job.id, 'https://example.com/private-link')

    def update(self, extract, password=None):
        return self.c.update_processing(self.job.id, extract, password)

    def test_empty_and_omitted_password_preserve_secret(self):
        for password in (None, ''):
            result = self.update(True, password)
            self.assertEqual(backend.load_job_password(self.job.id), 'synthetic-old')
            self.assertNotIn('password', result)
            self.assertNotIn('synthetic-old', str(self.c.public_jobs()))

    def test_false_removes_only_password(self):
        self.update(False, 'ignored-new')
        self.assertEqual(backend.load_job_password(self.job.id), '')
        self.assertEqual(backend.load_job_download_url(self.job.id), 'https://example.com/private-link')
        self.assertFalse(self.job.extract)

    def test_allowed_states_save_without_resuming(self):
        for status in ('queued', 'ready', 'inspecting', 'paused', 'downloading'):
            self.job.status = status
            self.update(True, 'synthetic-new')
            self.assertEqual(self.job.status, status)
            self.assertEqual(backend.load_job_password(self.job.id), 'synthetic-new')

    def test_busy_or_final_states_cannot_change(self):
        for status in ('waiting_processing', 'verifying', 'extracting', 'publishing', 'stopping', 'completed', 'failed', 'cancelled'):
            self.job.status = status
            with self.assertRaises(ValueError):
                self.update(False)
            self.assertTrue(self.job.extract)
        self.job.status = 'paused'
        self.c.running_providers = {'gigafile': {self.job.id}}
        with self.assertRaises(ValueError):
            self.update(False)

    def test_password_waiting_requeues_only_with_password(self):
        self.job.status = 'password_required'
        backend.delete_job_password(self.job.id)
        with self.assertRaises(ValueError):
            self.update(True)
        self.update(True, 'synthetic-new')
        self.assertEqual(self.job.status, 'queued')

    def test_skip_extraction_uses_retained_artifact_without_network(self):
        self.job.status = 'password_required'
        with self.assertRaises(ValueError):
            self.update(False)
        workspace = backend.job_workspace(self.job.target, self.job.id)
        workspace.mkdir(parents=True)
        artifact = workspace / self.job.name
        artifact.write_bytes(b'data')
        self.job.sha256 = hashlib.sha256(b'data').hexdigest()
        self.update(False)
        self.assertEqual(self.job.status, 'queued')
        with mock.patch.object(self.c, '_postprocess') as post, mock.patch.object(backend, 'inspect_download') as inspect:
            self.c._run(self.job.id)
            post.assert_called_once_with(self.job.id, workspace, artifact, self.job.target, verify_artifact=True)
            inspect.assert_not_called()
        with mock.patch.object(backend, 'normalize_target', side_effect=lambda p:p), mock.patch.object(backend, 'extract_archive_safely') as extract:
            output, extracted = backend.promote_download(artifact, self.job.target, False)
            self.assertEqual(output.read_bytes(), b'data')
            self.assertFalse(extracted)
            extract.assert_not_called()

    def test_save_failure_restores_previous_options_and_password(self):
        self.c.save.side_effect = OSError('disk full')
        with self.assertRaises(OSError):
            self.update(False)
        self.assertTrue(self.job.extract)
        self.assertEqual(backend.load_job_password(self.job.id), 'synthetic-old')

    def test_strict_input_validation(self):
        for value in (None, 1, 'true', [], {}):
            with self.assertRaises(ValueError):
                self.update(value)
        with self.assertRaises(ValueError):
            self.update(True, {'secret': 'invalid'})
        with self.assertRaises(ValueError):
            self.update(True, 'line\nbreak')
