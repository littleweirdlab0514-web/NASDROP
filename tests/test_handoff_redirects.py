from datetime import datetime, timezone
import unittest
from unittest import mock
from urllib.error import HTTPError

import backend
from test_browser_handoff import SHARES, Response, direct


def final(provider):
    if provider == 'akirabox':
        return 'https://us1.akirabox.com/synthetic/path/file.zip?access=synthetic-private-access'
    date = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    host = next(iter(backend.HANDOFF_FILE_HOSTS['vikingfile']))
    return f'https://{host}/synthetic/file.zip?X-Amz-Date={date}&X-Amz-Expires=3600&X-Amz-Signature=synthetic-private-signature'


def redirect(url, location):
    return HTTPError(url, 302, '', {'Location': location}, None)


def ranged(url):
    response = Response(url)
    response.status = 206
    response.headers.replace_header('Content-Length', '1')
    response.headers['Content-Range'] = 'bytes 0-0/100'
    response.read = mock.Mock(side_effect=AssertionError('Must not read file body'))
    return response


class HandoffRedirectTests(unittest.TestCase):
    def inspect(self, provider, responses):
        opener = mock.Mock()
        opener.open.side_effect = responses
        with mock.patch.object(backend, 'build_opener', return_value=opener):
            result = backend.inspect_browser_handoff(SHARES[provider], direct(provider), provider)
        return result, opener

    def test_akira_observed_redirect_uses_final_url_not_initial_endpoint(self):
        url = final('akirabox')
        result, opener = self.inspect('akirabox', [redirect(direct('akirabox'), url), Response(url, '영화.mp4')])
        self.assertEqual(result['download_url'], url)
        self.assertEqual(result['name'], '영화.mp4')
        self.assertEqual(result['url'], SHARES['akirabox'])
        self.assertNotIn('synthetic-private', str(backend.public_inspection(result)))
        self.assertEqual(opener.open.call_args.args[0].get_method(), 'HEAD')

    def test_viking_get_signed_url_rejects_head_but_range_works(self):
        url = final('vikingfile')
        response = ranged(url)
        result, opener = self.inspect('vikingfile', [redirect(direct('vikingfile'), url), HTTPError(url, 403, 'secret', {}, None), response])
        self.assertEqual(result['size'], 100)
        self.assertEqual(result['download_url'], url)
        self.assertEqual(opener.open.call_args.args[0].get_method(), 'GET')
        self.assertEqual(opener.open.call_args.args[0].get_header('Range'), 'bytes=0-0')
        for call in opener.open.call_args_list:
            self.assertIsNone(call.args[0].get_header('Cookie'))
            self.assertEqual(call.args[0].get_header('Referer'), SHARES['vikingfile'])
        response.read.assert_not_called()

    def test_head_missing_range_metadata_probes_instead_of_rejecting(self):
        url = final('akirabox')
        head = Response(url)
        del head.headers['Accept-Ranges']
        result, opener = self.inspect('akirabox', [redirect(direct('akirabox'), url), head, ranged(url)])
        self.assertEqual(result['size'], 100)
        self.assertEqual(opener.open.call_count, 3)

    def test_disallowed_redirect_never_reaches_destination(self):
        for provider in SHARES:
            for bad in ('http://127.0.0.1/private', 'https://us2.akirabox.com/a?access=x',
                        'https://us1.akirabox.com.evil.example/a?access=x',
                        'https://unrelated.r2.cloudflarestorage.com/a',
                        final(provider).replace('https://', 'https://user@'),
                        final(provider).replace('.com/', '.com:444/'),
                        final('vikingfile' if provider == 'akirabox' else 'akirabox')):
                opener = mock.Mock()
                opener.open.side_effect = redirect(direct(provider), bad)
                with self.subTest(provider=provider, bad=bad), mock.patch.object(backend, 'build_opener', return_value=opener), self.assertRaises(ValueError):
                    backend.inspect_browser_handoff(SHARES[provider], direct(provider), provider)
                self.assertEqual(opener.open.call_count, 1)

    def test_redirect_loop_and_hop_limit_are_bounded(self):
        for responses, count in [([redirect(direct('akirabox'), direct('akirabox'))], 1),
                                 ([redirect(direct('akirabox'), final('akirabox') + str(i)) for i in range(4)], 4)]:
            opener = mock.Mock()
            opener.open.side_effect = responses
            with mock.patch.object(backend, 'build_opener', return_value=opener), self.assertRaises(ValueError):
                backend.inspect_browser_handoff(SHARES['akirabox'], direct('akirabox'), 'akirabox')
            self.assertEqual(opener.open.call_count, count)

    def test_range_ignored_or_invalid_never_reads_whole_body(self):
        for invalid in ('ignored', 'bad-range', 'wrong-length'):
            url = final('vikingfile')
            response = ranged(url)
            if invalid == 'ignored': response.status = 200
            if invalid == 'bad-range': response.headers.replace_header('Content-Range', 'bytes 1-1/100')
            if invalid == 'wrong-length': response.headers.replace_header('Content-Length', '100')
            with self.assertRaises(ValueError):
                self.inspect('vikingfile', [redirect(direct('vikingfile'), url), HTTPError(url, 403, '', {}, None), response])
            response.read.assert_not_called()

    def test_expired_or_duplicate_r2_signature_metadata_rejected(self):
        for url in (final('vikingfile').replace('X-Amz-Expires=3600', 'X-Amz-Expires=0'),
                    final('vikingfile') + '&X-Amz-Signature=other',
                    final('vikingfile').replace(datetime.now(timezone.utc).strftime('%Y%m%d'), '20000101')):
            with self.assertRaises(ValueError): backend._validate_handoff_transfer_url(url, 'vikingfile')

    def test_final_transfer_still_disallows_redirect_and_restores_from_secret(self):
        from pathlib import Path
        import tempfile
        import threading
        for provider in SHARES:
            url = final(provider)
            with tempfile.TemporaryDirectory() as temp, mock.patch.object(backend, 'SECRET_DIR', Path(temp) / 'secrets'):
                c = backend.Controller.__new__(backend.Controller)
                c.lock = threading.RLock()
                c.condition = threading.Condition(c.lock)
                c.save = mock.Mock()
                job = backend.Job('123456abcdef', 'file.zip', SHARES[provider], 100, 0, 'queued', 'now', target=temp)
                c.jobs, c.private_downloads = {job.id: job}, {}
                backend.save_job_download_url(job.id, url)
                c._download_script_direct = mock.Mock(side_effect=RuntimeError('STOP'))
                with self.assertRaisesRegex(RuntimeError, 'STOP'): c._run(job.id)
                self.assertEqual(c._download_script_direct.call_args.args[0], url)
                self.assertEqual(job.transfer_mode, 'single')
            c = backend.Controller.__new__(backend.Controller)
            script = c._download_script_direct(url, SHARES[provider], 'file.zip', '123456abcdef', 100, '/tmp/test', mode='single')
            self.assertIn('--max-redirs 0', script)
            self.assertNotIn('Cookie:', script)


if __name__ == '__main__': unittest.main()
