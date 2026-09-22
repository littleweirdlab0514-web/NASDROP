import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import backend


class SafeDeleteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c = backend.Controller.__new__(backend.Controller)
        self.c.lock = threading.RLock()
        self.c.condition = threading.Condition(self.c.lock)
        self.c.stopping = False
        self.c.processes, self.c.private_downloads, self.c.running_providers = {}, {}, {}
        self.c.processing_job, self.c.postprocess_waiting = None, []
        self.c.save = mock.Mock()
        self.job = backend.Job('123456abcdef', 'file.zip', 'https://example.com/file',
                               4, 4, 'paused', 'now', target=str(self.root))
        self.c.jobs = {self.job.id: self.job}
        self.workspace = backend.job_workspace(str(self.root), self.job.id)
        self.workspace.mkdir(parents=True)
        (self.workspace / 'part').write_bytes(b'data')
        self.output = self.root / 'published.zip'
        self.output.write_bytes(b'keep')
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(backend, 'SHUTDOWN_EVENT', threading.Event()).start()
        mock.patch.object(backend, 'SECRET_DIR', self.root / 'secrets').start()

    def wait_deleted(self):
        with self.c.condition:
            self.assertTrue(self.c.condition.wait_for(lambda: self.job.id not in self.c.jobs, timeout=5))
        self.assertFalse(self.workspace.exists())
        self.assertEqual(self.output.read_bytes(), b'keep')

    def test_idle_and_queued_delete_immediately_preserves_output(self):
        self.job.status = 'queued'
        self.assertEqual(self.c.request_delete([self.job.id, self.job.id]),
                         {'ok': True, 'deleted': 1, 'pending': []})
        self.wait_deleted()

    def test_all_worker_phases_wait_then_delete_and_repeated_request_coalesces(self):
        for status in ('inspecting', 'ready', 'downloading', 'waiting_processing', 'verifying', 'extracting', 'publishing', 'stopping'):
            with self.subTest(status=status):
                self.c.jobs[self.job.id] = self.job
                self.workspace.mkdir(parents=True, exist_ok=True)
                self.job.status, self.job.delete_requested = status, False
                self.c.running_providers = {'test': {self.job.id}}
                entered, release = threading.Event(), threading.Event()
                def work(_):
                    entered.set()
                    release.wait(5)
                self.c._run = work
                worker = threading.Thread(target=self.c._run_guarded, args=(self.job.id, 'test'))
                worker.start()
                self.assertTrue(entered.wait(2))
                try:
                    result = self.c.request_delete([self.job.id])
                    self.assertEqual(result['pending'], [self.job.id])
                    self.assertEqual(self.c.request_delete([self.job.id]), result)
                    self.assertTrue(self.workspace.exists())
                    self.assertEqual(self.job.status, 'stopping')
                    with self.assertRaises(ValueError):
                        self.c.resume(self.job.id)
                    with self.assertRaises(ValueError):
                        self.c.delete([self.job.id])
                    with self.assertRaises(ValueError):
                        self.c.update_processing(self.job.id, False, '')
                finally:
                    release.set()
                    worker.join(5)
                self.wait_deleted()

    def test_real_subprocess_writer_exits_before_workspace_cleanup(self):
        self.job.status = 'extracting'
        self.c.running_providers = {'test': {self.job.id}}
        marker = self.workspace / 'writer'
        command = [sys.executable, '-c',
                   'import pathlib,time; p=pathlib.Path(__import__("sys").argv[1]); '
                   'p.write_text("ready");\nwhile True:\n p.write_text("working"); time.sleep(.01)', str(marker)]
        processes = []
        popen = subprocess.Popen
        def capture(*args, **kwargs):
            process = popen(*args, **kwargs)
            processes.append(process)
            return process
        self.c._run = lambda _: backend._run_interruptible(command, cancelled=lambda: self.job.delete_requested,
                            process_callback=lambda process: self.c._track_processing_process(self.job.id, process))
        with mock.patch.object(backend.subprocess, 'Popen', side_effect=capture):
            worker = threading.Thread(target=self.c._run_guarded, args=(self.job.id, 'test'))
            worker.start()
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(marker.exists())
                self.c.request_delete([self.job.id])
                self.wait_deleted()
                self.assertIsNotNone(processes[0].poll())
            finally:
                self.job.delete_requested = True
                worker.join(5)
        self.assertFalse(worker.is_alive())

    def test_publication_cancelled_after_extraction_leaves_output_untouched(self):
        artifact = self.workspace / 'file.zip'
        artifact.write_bytes(b'archive')
        def extract(_archive, destination, _password, **kwargs):
            (destination / 'data').write_bytes(b'extracted')
            self.job.delete_requested = True
        with mock.patch.object(backend, 'extract_archive_safely', side_effect=extract):
            with self.assertRaises(InterruptedError):
                backend.promote_download(artifact, str(self.root), True,
                                         cancelled=lambda: self.job.delete_requested, publication_lock=self.c.lock)
        self.assertFalse((self.root / 'file').exists())
        self.assertTrue(artifact.exists())
        with self.assertRaises(InterruptedError):
            backend.promote_download(artifact, str(self.root), False, cancelled=lambda: True)
        self.assertTrue(artifact.exists())

    def test_async_cleanup_failure_preserves_record_and_allows_retry(self):
        self.job.status, self.job.delete_requested = 'paused', True
        with mock.patch.object(backend.shutil, 'rmtree', side_effect=PermissionError):
            self.c._finish_delete(self.job.id)
        self.assertIn(self.job.id, self.c.jobs)
        self.assertFalse(self.job.delete_requested)
        self.assertEqual(self.job.status, 'failed')
        self.assertTrue(self.job.error)
        self.assertTrue(self.workspace.exists())
        self.c.request_delete([self.job.id])
        self.wait_deleted()

    def test_save_failure_rolls_back_flags_before_starting_delete_thread(self):
        self.job.status = 'downloading'
        self.c.running_providers = {'test': {self.job.id}}
        self.c.save.side_effect = OSError('disk full')
        with mock.patch.object(backend.threading, 'Thread') as thread:
            with self.assertRaises(OSError):
                self.c.request_delete([self.job.id])
            thread.assert_not_called()
        self.assertFalse(self.job.delete_requested)
        self.assertEqual(self.job.status, 'downloading')
        self.assertTrue(self.workspace.exists())

    def test_restart_does_not_replay_destructive_request(self):
        self.job.delete_requested, self.job.status = True, 'stopping'
        state = self.root / 'jobs.json'
        state.write_text(json.dumps([backend.asdict(self.job)]))
        with mock.patch.object(backend, 'STATE_FILE', state):
            self.c.load()
        restored = self.c.jobs[self.job.id]
        self.assertFalse(restored.delete_requested)
        self.assertEqual(restored.status, 'paused')
        self.assertTrue(self.workspace.exists())

    def test_process_stop_failure_never_deletes_and_legacy_delete_still_refuses(self):
        self.job.delete_requested = True
        self.c.processes[self.job.id] = mock.Mock()
        with mock.patch.object(self.c, '_stop_process', side_effect=TimeoutError):
            self.c._finish_delete(self.job.id)
        self.assertTrue(self.workspace.exists())
        with self.assertRaises(ValueError):
            self.c.delete([self.job.id])

    def test_api_opt_in_and_response_contract(self):
        handler = backend.Handler.__new__(backend.Handler)
        handler.path = '/api/jobs/delete'
        handler.authorized = lambda: True
        handler.send_json = mock.Mock()
        handler.body = lambda: {'ids': [self.job.id], 'stop_active': True}
        with mock.patch.object(backend, 'CONTROLLER', self.c):
            result = {'ok': True, 'deleted': 0, 'pending': [self.job.id]}
            with mock.patch.object(self.c, 'request_delete', return_value=result):
                handler.do_POST()
            self.assertEqual(handler.send_json.call_args.args, (backend.HTTPStatus.ACCEPTED, result))
            handler.body = lambda: {'ids': [self.job.id]}
            with mock.patch.object(self.c, 'delete', return_value=1) as strict, mock.patch.object(self.c, 'request_delete') as safe:
                handler.do_POST()
                strict.assert_called_once_with([self.job.id])
                safe.assert_not_called()
            handler.body = lambda: {'ids': [self.job.id], 'stop_active': 'true'}
            handler.do_POST()
            self.assertEqual(handler.send_json.call_args.args[0], backend.HTTPStatus.BAD_REQUEST)

    def test_unconfirmed_process_stop_keeps_worker_ownership(self):
        self.c.running_providers = {'test': {self.job.id}}
        self.c.processes[self.job.id] = mock.Mock()
        self.c._run = mock.Mock(side_effect=RuntimeError('synthetic failure'))
        with mock.patch.object(self.c, '_stop_process', side_effect=TimeoutError):
            self.c._run_guarded(self.job.id, 'test')
        self.assertIn(self.job.id, self.c.running_providers['test'])
        self.assertTrue(self.workspace.exists())


if __name__ == '__main__':
    unittest.main()
