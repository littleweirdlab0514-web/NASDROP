import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import backend
from transfer_parts import commit_fragment, segment_count, segment_chunk, initial_transfer_mode


class TransferReliabilityTests(unittest.TestCase):
    def test_gofile_two_parts_and_legacy_concurrency(self):
        self.assertEqual(initial_transfer_mode('gofile', 'segmented'), 'segmented2')
        self.assertEqual(initial_transfer_mode('gofile', 'single'), 'single')
        self.assertEqual(initial_transfer_mode('gigafile', 'segmented'), 'segmented')
        for size in range(1, 100):
            chunk = segment_chunk(size, 'segmented2')
            count = segment_count(size, 'segmented2')
            self.assertLessEqual(count, 2)
            self.assertLess((count - 1) * chunk, size)
            self.assertGreaterEqual(count * chunk, size)
        controller = backend.Controller.__new__(backend.Controller)
        for name in ('video.mp4', 'archive.zip'):
            for mode, count, chunk in [('segmented2', 2, 40), ('segmented', 8, 10), ('single', 1, 80)]:
                script = controller._download_script_gofile('https://example.com/file', 'test', 'https://gofile.io/d/test', name, 'test', 80, '/tmp/test', mode=mode)
                self.assertIn(f'COUNT={count}\nCHUNK={chunk}\n', script)
                self.assertIn('i % 2', script)
        job = backend.Job('test', 'file.zip', 'https://gofile.io/d/test', 7, 7, 'verifying', 'now', transfer_mode='segmented2')
        (self.root / '.test.segment.0').write_bytes(b'abcd')
        (self.root / '.test.segment.1').write_bytes(b'efg')
        artifact, _digest = controller._assemble_artifact(job, self.root, {})
        self.assertEqual(artifact.read_bytes(), b'abcdefg')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.part = self.root / 'part'
        self.more = self.root / 'part.more'
        self.headers = self.root / 'part.headers'

    def fragment(self, body=b'cdef', first=2, last=7, total=8):
        self.more.write_bytes(body)
        self.headers.write_bytes(
            f'HTTP/1.1 206 Partial Content\r\nContent-Range: bytes {first}-{last}/{total}\r\n'.encode()
            + b'Set-Cookie: secret=never-retain\r\nContent-Disposition: attachment; filename="file.zip"\r\n\r\n')

    def test_partial_response_is_committed_and_replay_is_idempotent(self):
        self.part.write_bytes(b'ab')
        self.fragment()
        self.assertTrue(commit_fragment(self.part, 0, 7, 8))
        self.assertEqual(self.part.read_bytes(), b'abcdef')
        self.fragment()
        self.assertTrue(commit_fragment(self.part, 0, 7, 8))
        self.assertEqual(self.part.read_bytes(), b'abcdef')
        self.assertNotIn(b'secret', (self.root / '.response-headers').read_bytes())
        self.assertFalse(self.headers.exists())

    def test_io_failure_keeps_validated_fragment_for_replay_without_cookies(self):
        self.part.write_bytes(b'ab')
        self.fragment()
        with mock.patch('transfer_parts.shutil.copyfileobj', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                commit_fragment(self.part, 0, 7, 8)
        self.assertTrue(self.more.exists())
        self.assertNotIn(b'secret', self.headers.read_bytes())
        self.assertTrue(commit_fragment(self.part, 0, 7, 8))
        self.assertEqual(self.part.read_bytes(), b'abcdef')

    def test_bad_range_never_corrupts_existing_part(self):
        for first, last, total in [(3, 7, 8), (2, 6, 8), (2, 7, 9)]:
            self.part.write_bytes(b'ab')
            self.fragment(first=first, last=last, total=total)
            self.assertFalse(commit_fragment(self.part, 0, 7, 8))
            self.assertEqual(self.part.read_bytes(), b'ab')

    def test_429_without_body_sets_cooldown_marker(self):
        self.headers.write_bytes(b'HTTP/1.1 429 Too Many Requests\r\nRetry-After: 900\r\n\r\n')
        self.assertFalse(commit_fragment(self.part, 0, 7, 8))
        self.assertEqual(json.loads((self.root / '.rate-limit').read_text())['retry_after'], '900')

    def test_legacy_unverified_fragment_is_discarded_without_touching_part(self):
        self.part.write_bytes(b'ab')
        self.more.write_bytes(b'unknown')
        self.assertFalse(commit_fragment(self.part, 0, 7, 8))
        self.assertEqual(self.part.read_bytes(), b'ab')

    def test_small_file_layout_has_no_empty_ranges(self):
        for size in range(1, 100):
            chunk = (size + 7) // 8
            count = segment_count(size)
            self.assertLessEqual(count, 8)
            self.assertLess((count - 1) * chunk, size)
            self.assertGreaterEqual(count * chunk, size)

    def test_single_file_hash_interruption_keeps_downloaded_part(self):
        job = backend.Job('test', 'file.zip', 'https://example.gigafile.nu/id', 4, 4, 'verifying', 'now', transfer_mode='single')
        part = self.root / '.test.segment.0'
        part.write_bytes(b'data')
        controller = backend.Controller.__new__(backend.Controller)
        with mock.patch.object(controller, '_file_sha256', side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):
                controller._assemble_artifact(job, self.root, {})
        self.assertEqual(part.read_bytes(), b'data')

    def test_copy_and_hash_observe_job_cancellation(self):
        self.part.write_bytes(b'data')
        with self.assertRaises(InterruptedError):
            backend.Controller._file_sha256(self.part, cancelled=lambda: True)
        target = io.BytesIO()
        with self.assertRaises(InterruptedError):
            backend._copy_checked(io.BytesIO(b'data'), target, 4, cancelled=lambda: True)
        self.assertEqual(target.getvalue(), b'')

    def test_body_rejects_non_objects(self):
        handler = backend.Handler.__new__(backend.Handler)
        for raw in [b'[]', b'null', b'1', b'"text"']:
            handler.headers = {'content-length': str(len(raw))}
            handler.rfile = io.BytesIO(raw)
            with self.assertRaises(ValueError):
                handler.body()

    def test_generated_shell_propagates_failure_and_resumes_exact_bytes(self):
        shell = shutil.which('bash') if os.name != 'nt' else r'C:\Program Files\Git\bin\bash.exe'
        if not shell or not Path(shell).exists():
            self.skipTest('Bash required for generated transfer script integration test')
        data = bytes(range(256))
        class Server(BaseHTTPRequestHandler):
            fail_once = True
            def do_GET(self):
                first, last = map(int, self.headers['Range'].removeprefix('bytes=').split('-'))
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {first}-{last}/{len(data)}')
                self.send_header('Content-Length', str(last-first+1))
                self.send_header('Connection', 'close')
                self.end_headers()
                if first == 0 and Server.fail_once:
                    Server.fail_once = False
                    self.wfile.write(data[:2])
                else:
                    self.wfile.write(data[first:last+1])
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        prefix = (self.root / 'segment').as_posix()
        script = 'export PATH="/usr/bin:/bin:$PATH"\nset -eu\n' + backend.Controller._transfer_loop(
            prefix, len(data), 'segmented', f'curl --silent --show-error --max-time 5 http://127.0.0.1:{server.server_port}/file')
        first = subprocess.run([shell, '-s'], input=script, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(first.returncode, 0, first.stderr)
        self.assertEqual((self.root / 'segment.0').read_bytes(), data[:2])
        second = subprocess.run([shell, '-s'], input=script, text=True, capture_output=True, timeout=30)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(b''.join((self.root / f'segment.{i}').read_bytes() for i in range(8)), data)

    def controller(self, status='verifying'):
        c = backend.Controller.__new__(backend.Controller)
        c.lock = threading.RLock()
        c.condition = threading.Condition(c.lock)
        c.jobs = {'test': backend.Job('test', 'file.zip', 'https://gofile.io/d/test', 8, 0, status, 'now')}
        c.running_providers = {'gofile': {'test'}}
        c.private_downloads = {'test': {'provider': 'gofile'}}
        c.processes = {}
        c.processing_job = None
        c.postprocess_waiting = []
        c.save = mock.Mock()
        return c

    def test_pause_blocks_resume_until_worker_exits(self):
        c = self.controller()
        c.pause('test')
        self.assertEqual(c.jobs['test'].status, 'stopping')
        with self.assertRaises(ValueError):
            c.resume('test')
        with mock.patch.object(c, '_run'):
            c._run_guarded('test', 'gofile')
        self.assertEqual(c.jobs['test'].status, 'paused')
        c.resume('test')
        self.assertEqual(c.jobs['test'].status, 'queued')

    def test_postprocess_does_not_overwrite_pause_after_gate(self):
        c = self.controller()
        def gate(job_id):
            c.jobs[job_id].status = 'stopping'
            return True
        with mock.patch.object(c, '_enter_postprocessing', side_effect=gate), mock.patch.object(backend, 'promote_download') as publish:
            c._postprocess('test', self.root, self.root / 'file.zip', str(self.root))
            publish.assert_not_called()
        self.assertEqual(c.jobs['test'].status, 'stopping')

    def test_gofile_transfer_429_defers_all_same_provider_jobs(self):
        c = self.controller('downloading')
        c.jobs['next'] = backend.Job('next', 'next', 'https://gofile.io/d/next', 8, 0, 'queued', 'now')
        c.jobs['other'] = backend.Job('other', 'other', 'https://pixeldrain.com/u/abcdefgh', 8, 0, 'queued', 'now')
        (self.root / '.rate-limit').write_text('{"retry_after":"900"}')
        with mock.patch.object(backend, 'GOFILE_COOLDOWN_UNTIL', 0), mock.patch.object(backend, 'GOFILE_COOLDOWN_REASON', ''), mock.patch.object(backend, 'GOFILE_COOLDOWN_FILE', self.root / 'cooldown.json'):
            c._defer_gofile(c.jobs['test'], self.root)
            self.assertEqual(c.jobs['test'].status, 'queued')
            self.assertEqual(c.jobs['test'].not_before, c.jobs['next'].not_before)
            self.assertGreater(c.jobs['test'].not_before, backend.time.time() + 890)
            self.assertEqual(c.jobs['other'].not_before, 0)
            self.assertFalse(c._can_start(c.jobs['next']))

    def test_shutdown_terminates_processes_and_persists_pause(self):
        c = self.controller('downloading')
        process = mock.Mock()
        c.processes['test'] = process
        with mock.patch.object(backend, 'SHUTDOWN_EVENT', threading.Event()), mock.patch.object(c, '_terminate') as terminate, mock.patch.object(c, '_stop_process') as stop:
            c.shutdown(timeout=0)
            terminate.assert_called_once_with(process)
            stop.assert_called_once_with(process)
            self.assertEqual(c.jobs['test'].status, 'paused')
            self.assertTrue(c.stopping)


if __name__ == '__main__':
    unittest.main()
