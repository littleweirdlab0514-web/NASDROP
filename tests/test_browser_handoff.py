from email.message import Message
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import quote

import backend


SHARES = {'akirabox': 'https://akirabox.to/Test123/file', 'vikingfile': 'https://vik1ngfile.site/f/Test123'}
SENDNOW_SHARE = 'https://send.now/e0g53wnqs8ze'
SENDNOW_DIRECT = 'https://cdn-2.send.now/files/synthetic/file.zip?token=synthetic-private-token'


def direct(provider):
    if provider == 'akirabox':
        return 'https://akirabox.com/download/synthetic-token/file.zip?expiration=' + str(int(time.time()) + 3600) + '&signature=' + 'a' * 64
    return 'https://vikingfile.com/d/synthetic-token/file.zip'


class Response:
    def __init__(self, url, name='테스트 영상.mp4'):
        self.url, self.status = url, 200
        self.headers = Message()
        self.headers['Content-Disposition'] = "attachment; filename=old.bin; filename*=UTF-8''" + quote(name)
        self.headers['Content-Length'] = '100'
        self.headers['Content-Type'] = 'application/octet-stream'
        self.headers['Accept-Ranges'] = 'bytes'

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.url


class BrowserHandoffTests(unittest.TestCase):
    def test_sendnow_user_resolved_link_uses_single_connection_handoff(self):
        opener = mock.Mock()
        opener.open.return_value = Response(SENDNOW_DIRECT, '브라우저 파일.zip')
        with mock.patch.object(backend, 'build_opener', return_value=opener):
            result = backend.inspect_payload({'url': SENDNOW_SHARE, 'resolved_url': SENDNOW_DIRECT, 'provider': 'sendnow'})
        self.assertEqual(result['url'], SENDNOW_SHARE)
        self.assertEqual(result['name'], '브라우저 파일.zip')
        self.assertEqual(result['provider'], 'sendnow')
        self.assertNotIn('synthetic-private-token', str(backend.public_inspection(result)))
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), 'HEAD')
        self.assertEqual(request.get_header('Referer'), SENDNOW_SHARE)
        self.assertIsNone(request.get_header('Cookie'))

    def test_sendnow_allows_public_https_delivery_hosts_but_blocks_ssrf(self):
        public = 'https://downloads.example/file.zip?token=synthetic'
        with mock.patch.object(backend.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]):
            self.assertEqual(backend._validate_handoff_transfer_url(public, 'sendnow'), public)
        for address in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '192.168.1.157', '::1'):
            with self.subTest(address=address), mock.patch.object(backend.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', (address, 443))]), self.assertRaises(ValueError):
                backend._validate_handoff_transfer_url('https://downloads.example/file.zip', 'sendnow')
        for bad in (SENDNOW_SHARE, 'http://cdn.send.now/file.zip', 'https://user@cdn.send.now/file.zip',
                    'https://cdn.send.now:8443/file.zip', 'https://cdn.send.now/file.zip#fragment',
                    'https://send.now.evil.example/file.zip', 'https://127.0.0.1/file.zip'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                backend.inspect_browser_handoff(SENDNOW_SHARE, bad, 'sendnow')

    def test_sendnow_restart_secret_and_response_filename(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(backend, 'SECRET_DIR', Path(temp) / 'secrets'):
            c = backend.Controller.__new__(backend.Controller)
            c.lock = threading.RLock()
            c.condition = threading.Condition(c.lock)
            c.jobs, c.private_downloads = {}, {}
            c.save = mock.Mock()
            file = {'url': SENDNOW_SHARE, 'name': 'archive.zip', 'size': 100, 'provider': 'sendnow', 'download_url': SENDNOW_DIRECT}
            with mock.patch.object(backend, 'normalize_target', return_value=temp), mock.patch.object(backend, 'prepare_batch_target', return_value=temp):
                job = c.start_many([file], temp, False)[0]
            self.assertEqual(backend.load_job_download_url(job.id), SENDNOW_DIRECT)
            c.private_downloads = {}
            c._download_script_direct = mock.Mock(side_effect=RuntimeError('STOP-BEFORE-TRANSFER'))
            with self.assertRaisesRegex(RuntimeError, 'STOP-BEFORE-TRANSFER'):
                c._run(job.id)
            self.assertEqual(job.transfer_mode, 'single')
            self.assertEqual(c._download_script_direct.call_args.args[0], SENDNOW_DIRECT)
            self.assertTrue(c._download_script_direct.call_args.kwargs['capture_headers'])

    def test_metadata_normal_file_and_archive_and_secret_filter(self):
        for provider in SHARES:
            for name in ('테스트 영상.mp4', '압축.zip'):
                url = direct(provider)
                opener = mock.Mock()
                opener.open.return_value = Response(url, name)
                with mock.patch.object(backend, 'build_opener', return_value=opener):
                    result = backend.inspect_payload({'url': SHARES[provider], 'resolved_url': url, 'provider': provider})
                self.assertEqual(result['name'], name)
                self.assertEqual(result['provider'], provider)
                public = backend.cache_inspection(result)
                self.assertNotIn('synthetic-token', str(public))
                self.assertEqual(backend.consume_inspection(public)['download_url'], url)
                request = opener.open.call_args.args[0]
                self.assertEqual(request.get_method(), 'HEAD')
                self.assertEqual(request.get_header('Referer'), SHARES[provider])
                self.assertIsNone(request.get_header('Cookie'))

    def test_untrusted_hosts_credentials_ports_and_cross_provider_rejected(self):
        for provider in SHARES:
            url = direct(provider)
            for bad in (url.replace('https:', 'http:'), url.replace('https://', 'https://user@'),
                        url.replace('.com/', '.com:444/'), url.replace('.com/', '.com.evil.example/'),
                        url + '#fragment', url + '\n', 'https://127.0.0.1/download/a/b'):
                with self.subTest(provider=provider, bad=bad), self.assertRaises(ValueError):
                    backend.inspect_browser_handoff(SHARES[provider], bad, provider)
            with self.assertRaises(ValueError):
                backend.inspect_browser_handoff(SHARES[provider], direct('vikingfile' if provider == 'akirabox' else 'akirabox'), provider)
        with self.assertRaises(ValueError):
            backend.inspect_browser_handoff(SHARES['vikingfile'], direct('vikingfile'), 'arbitrary')

    def test_expired_signature_and_duplicate_query_rejected(self):
        url = direct('akirabox')
        for bad in (url.replace(str(int(time.time()) + 3600), '1000000000'), url + '&signature=' + 'b' * 64, url + '&next=https://example.com'):
            with self.assertRaises(ValueError):
                backend._validate_akira_url(bad, direct=True)

    def test_redirects_blocked_and_error_contains_no_token(self):
        for target in ('http://127.0.0.1/a', direct('akirabox')):
            url = direct('akirabox')
            opener = mock.Mock()
            opener.open.side_effect = HTTPError(url, 302, '', {'Location': target}, None)
            with self.assertRaises(ValueError):
                backend.inspect_browser_handoff(SHARES['akirabox'], url, 'akirabox')
        opener = mock.Mock()
        opener.open.side_effect = HTTPError(direct('akirabox'), 403, 'synthetic-token', {}, None)
        with mock.patch.object(backend, 'build_opener', return_value=opener), self.assertRaises(ValueError) as caught:
            backend.inspect_browser_handoff(SHARES['akirabox'], direct('akirabox'), 'akirabox')
        self.assertNotIn('synthetic-token', str(caught.exception))

    def test_head_unsupported_uses_bounded_range_without_reading_body(self):
        url = direct('vikingfile')
        response = Response(url)
        response.status = 206
        response.headers.replace_header('Content-Length', '1')
        response.headers['Content-Range'] = 'bytes 0-0/100'
        response.read = mock.Mock(side_effect=AssertionError('Body must not be downloaded'))
        opener = mock.Mock()
        opener.open.side_effect = [HTTPError(url, 405, '', {}, None), response]
        with mock.patch.object(backend, 'build_opener', return_value=opener):
            self.assertEqual(backend.inspect_browser_handoff(SHARES['vikingfile'], url, 'vikingfile')['size'], 100)
        self.assertEqual(opener.open.call_args.args[0].get_header('Range'), 'bytes=0-0')
        response.read.assert_not_called()

    def test_html_and_missing_ranges_rejected_missing_name_safe_fallback(self):
        for field, value in [('Content-Type', 'text/html'), ('Accept-Ranges', 'none'), ('Content-Length', '0')]:
            response = Response(direct('vikingfile'))
            response.headers.replace_header(field, value)
            opener = mock.Mock()
            opener.open.return_value = response
            with mock.patch.object(backend, 'build_opener', return_value=opener), self.assertRaises(ValueError):
                backend.inspect_browser_handoff(SHARES['vikingfile'], response.url, 'vikingfile')
        response = Response(direct('vikingfile'))
        del response.headers['Content-Disposition']
        opener.open.return_value = response
        with mock.patch.object(backend, 'build_opener', return_value=opener):
            self.assertEqual(backend.inspect_browser_handoff(SHARES['vikingfile'], response.url, 'vikingfile')['name'], 'file.zip')

    def test_response_filename_repeated_headers_malicious_path_and_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for provider in SHARES:
                (root / '.response-headers').write_bytes(b'HTTP/1.1 302 Found\r\nContent-Disposition: attachment; filename=wrong.bin\r\n\r\nHTTP/1.1 200 OK\r\nContent-Disposition: attachment; filename="../safe.zip"\r\n\r\n')
                original = root / 'original.bin'
                original.write_bytes(b'data')
                (root / '.._safe.zip').write_bytes(b'existing')
                c = backend.Controller.__new__(backend.Controller)
                c.lock, c.save = threading.RLock(), mock.Mock()
                job = backend.Job('123456abcdef', 'original.bin', SHARES[provider], 4, 4, 'verifying', 'now')
                result = c._apply_response_filename(job, root, original, {'provider': provider})
                self.assertEqual(result.parent, root)
                self.assertEqual(result.suffix, '.zip')
                self.assertEqual((root / '.._safe.zip').read_bytes(), b'existing')
                self.assertEqual(job.name, result.name)

    def test_restart_secret_storage_and_single_transfer(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(backend, 'SECRET_DIR', Path(temp) / 'secrets'):
            for provider in SHARES:
                c = backend.Controller.__new__(backend.Controller)
                c.lock = threading.RLock()
                c.condition = threading.Condition(c.lock)
                c.jobs, c.private_downloads = {}, {}
                c.save = mock.Mock()
                url = direct(provider)
                file = {'url': SHARES[provider], 'name': 'archive.zip', 'size': 100, 'provider': provider, 'download_url': url}
                with mock.patch.object(backend, 'normalize_target', return_value=temp), mock.patch.object(backend, 'prepare_batch_target', return_value=temp):
                    job = c.start_many([file], temp, False)[0]
                self.assertEqual(backend.load_job_download_url(job.id), url)
                self.assertNotIn('synthetic-token', str(backend.asdict(job)))
                c.private_downloads = {}
                c._download_script_direct = mock.Mock(side_effect=RuntimeError('STOP-BEFORE-TRANSFER'))
                with self.assertRaisesRegex(RuntimeError, 'STOP-BEFORE-TRANSFER'):
                    c._run(job.id)
                self.assertEqual(job.transfer_mode, 'single')
                self.assertEqual(c._download_script_direct.call_args.args[0], url)
                self.assertEqual(c._download_script_direct.call_args.kwargs['mode'], 'single')


class DeleteWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c = backend.Controller.__new__(backend.Controller)
        self.c.lock = threading.RLock()
        self.c.running_providers, self.c.private_downloads = {}, {}
        self.c.save = mock.Mock()
        self.job = backend.Job('123456abcdef', 'file.zip', SHARES['akirabox'], 10, 3, 'paused', 'now', target=str(self.root))
        self.c.jobs = {self.job.id: self.job}
        self.workspace = backend.job_workspace(str(self.root), self.job.id)
        self.workspace.mkdir(parents=True)
        (self.workspace / 'part').write_bytes(b'abc')

    def test_delete_failure_preserves_record_and_secret(self):
        with mock.patch.object(backend.shutil, 'rmtree', side_effect=PermissionError), mock.patch.object(backend, 'delete_job_secrets') as secret:
            with self.assertRaisesRegex(ValueError, '기록을 보존'):
                self.c.delete([self.job.id])
            secret.assert_not_called()
        self.assertIn(self.job.id, self.c.jobs)
        self.assertTrue(self.workspace.exists())

    def test_stopping_worker_is_not_deleted(self):
        for active in ('stopping', 'downloading', 'extracting'):
            self.job.status = active
            with self.assertRaises(ValueError): self.c.delete([self.job.id])
        self.job.status = 'paused'
        self.c.running_providers = {'akirabox': {self.job.id}}
        with self.assertRaises(ValueError): self.c.delete([self.job.id])

    def test_delete_workspace_only_preserves_completed_output(self):
        output = self.root / 'completed.zip'
        output.write_bytes(b'final')
        self.job.status, self.job.output = 'completed', str(output)
        with mock.patch.object(backend, 'delete_job_secrets'):
            self.assertEqual(self.c.delete([self.job.id]), 1)
        self.assertFalse(self.workspace.exists())
        self.assertEqual(output.read_bytes(), b'final')

    def test_symlink_workspace_is_never_followed(self):
        with mock.patch.object(Path, 'is_symlink', return_value=True), mock.patch.object(backend.shutil, 'rmtree') as remove:
            with self.assertRaises(ValueError): self.c.delete([self.job.id])
            remove.assert_not_called()
        self.assertIn(self.job.id, self.c.jobs)


if __name__ == '__main__':
    unittest.main()
