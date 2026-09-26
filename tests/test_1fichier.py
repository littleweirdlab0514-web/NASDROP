from email.message import Message
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from urllib.parse import quote

import backend


SHARE = "https://1fichier.com/?lfrhr13bp1m27ow32six"
DIRECT = "https://c42.1fichier.com/file-token"


class Response:
    def __init__(self, body):
        self.body = body.encode("utf-8")
        self.headers = Message()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, count=-1):
        return self.body[:count]


class OneFichierTests(unittest.TestCase):
    def test_metadata_inspection_of_user_supplied_share(self):
        opener = mock.Mock()
        opener.open.return_value = Response(f"{SHARE};라니.png;281582\n")
        with mock.patch.object(backend, "_onefichier_opener", return_value=opener):
            result = backend.inspect_download(SHARE)
        self.assertEqual((result["provider"], result["name"], result["size"]),
                         ("1fichier", "라니.png", 281582))
        self.assertEqual(backend.provider_for_url(SHARE), "1fichier")
        self.assertNotIn("test-@01", repr(result))

    def test_invalid_share_and_direct_urls_are_rejected(self):
        for url in ("http://1fichier.com/?lfrhr13bp1m27ow32six",
                    "https://1fichier.com.evil.test/?lfrhr13bp1m27ow32six",
                    "https://1fichier.com/?lfrhr13bp1m27ow32six&x=y"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                backend._validate_1fichier_share_url(url)
        for url in ("http://c42.1fichier.com/file-token", "https://img.1fichier.com/favicon.ico",
                    "https://127.0.0.1/file", "https://c42.1fichier.com:8080/file"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                backend._validate_1fichier_direct_url(url)

    def test_wait_and_password_post_then_direct_link(self):
        opener = mock.Mock()
        opener.open.side_effect = [
            Response('<form id="f1" method="post"><input name="pass"></form><script>var ct = 2;</script>'),
            Response(f'<a href="{DIRECT}">Download</a>'),
        ]
        with mock.patch.object(backend, "_onefichier_opener", return_value=opener), \
                mock.patch.object(backend.time, "sleep") as sleep:
            self.assertEqual(backend.resolve_1fichier_direct_url(SHARE, "test-@01"), DIRECT)
        self.assertGreaterEqual(sleep.call_count, 2)
        request = opener.open.call_args_list[1].args[0]
        self.assertIn(b"pass=test-%4001", request.data)

    def test_guest_limit_is_not_retried_or_bypassed(self):
        opener = mock.Mock()
        opener.open.return_value = Response("High demand: all free guest slots are currently in use")
        with mock.patch.object(backend, "_onefichier_opener", return_value=opener), \
                self.assertRaises(backend.OneFichierWaitError):
            backend.resolve_1fichier_direct_url(SHARE, "test-@01")
        self.assertEqual(opener.open.call_count, 1)

    def test_daily_free_limit_is_deferred_without_looking_for_a_form(self):
        opener = mock.Mock()
        opener.open.return_value = Response("You already downloaded for free more than 5 files today.")
        with mock.patch.object(backend, "_onefichier_opener", return_value=opener), \
                self.assertRaises(backend.OneFichierWaitError) as raised:
            backend.resolve_1fichier_direct_url(SHARE)
        self.assertEqual(raised.exception.seconds, 24 * 3600)
        self.assertEqual(opener.open.call_count, 1)

    def test_wait_parser_preserves_long_wait_without_polling(self):
        self.assertEqual(backend._onefichier_wait_seconds('You must wait 57 minutes…'), 3425)
        self.assertEqual(backend._onefichier_wait_seconds('You must wait up to 24 minutes between each downloads'), 1445)
        self.assertEqual(backend._onefichier_wait_seconds('Ads / Captcha'), 0)
        self.assertEqual(backend._onefichier_wait_seconds('You already downloaded for free more than 5 files today.'), 86400)

    def test_wait_releases_worker_without_waking_following_jobs(self):
        controller = backend.Controller.__new__(backend.Controller)
        with tempfile.TemporaryDirectory() as directory:
            job = backend.Job(id='0123456789ab', source=SHARE, name='file.bin', size=100, downloaded=48, status='preparing', created_at='', target=directory)
            following = backend.Job(id='fedcba987654', source=SHARE, name='next.bin', size=1, downloaded=0, status='queued', created_at='', target=directory)
            workspace = backend.job_workspace(directory, job.id)
            workspace.mkdir(parents=True)
            stale = workspace / f'.{job.id}.segment.0'
            stale.write_bytes(b'partial')
            controller.jobs = {job.id: job, following.id: following}
            controller.lock = threading.RLock()
            controller.condition = threading.Condition(controller.lock)
            controller.processes = {}
            controller.private_downloads = {}
            controller.running_providers = {'1fichier': {job.id}}
            controller.workers = {}
            controller.save = mock.Mock()
            with mock.patch.object(controller, '_run', side_effect=backend.OneFichierWaitError(3425)), mock.patch.object(backend.time, 'time', return_value=1000):
                controller._run_guarded(job.id, '1fichier')
            self.assertEqual(job.status, 'queued')
            self.assertEqual(job.not_before, 4425)
            self.assertEqual(job.downloaded, 0)
            self.assertFalse(stale.exists())
            self.assertEqual(following.not_before, 0)
            self.assertNotIn('1fichier', controller.running_providers)
            controller.save.assert_called()

    def test_visible_bottom_job_exclusively_owns_the_1fichier_queue(self):
        controller = backend.Controller.__new__(backend.Controller)
        bottom = backend.Job('bottom000001', 'bottom.bin', SHARE, 1, 0, 'queued', '', '/tmp', not_before=2000)
        middle = backend.Job('middle000001', 'middle.bin', SHARE, 1, 0, 'queued', '', '/tmp')
        top = backend.Job('top000000001', 'top.bin', SHARE, 1, 0, 'queued', '', '/tmp')
        controller.jobs = {bottom.id: bottom, middle.id: middle, top.id: top}
        controller.private_downloads = {}
        controller.running_providers = {}
        controller.processes = {}
        controller.postprocess_waiting = []
        controller.processing_job = ''
        controller.stopping = False
        controller.lock = threading.RLock()

        with mock.patch.object(backend.time, 'time', return_value=1000):
            self.assertEqual(controller._onefichier_queue_head(), bottom.id)
            self.assertFalse(controller._can_start(middle))
            self.assertFalse(controller._can_start(top))
            public = {item['id']: item for item in controller.public_jobs()}
        self.assertEqual(public[bottom.id]['not_before'], 2000)
        self.assertIn('순차적으로', public[middle.id]['error'])
        self.assertEqual(public[middle.id]['not_before'], 0)
        self.assertIn('순차적으로', public[top.id]['error'])

        bottom.status = 'completed'
        self.assertEqual(controller._onefichier_queue_head(), middle.id)
        self.assertTrue(controller._can_start(middle))
        self.assertFalse(controller._can_start(top))

    def test_global_controller_starts_after_provider_classifier_definition(self):
        source = Path(backend.__file__).read_text(encoding='utf-8')
        self.assertLess(source.index('def provider_for_url('), source.index('CONTROLLER = None if'))

    def test_account_bootstrap_suppresses_download_dispatcher_before_import(self):
        source = (Path(backend.__file__).parent / 'docker' / 'account.py').read_text(encoding='utf-8')
        self.assertLess(source.index('NAS_PORTAL_ACCOUNT_COMMAND'), source.index('import backend'))
        backend_source = Path(backend.__file__).read_text(encoding='utf-8')
        self.assertIn('NAS_PORTAL_ACCOUNT_COMMAND', backend_source[backend_source.index('CONTROLLER = '):])

    def test_pricing_captcha_label_is_not_a_challenge(self):
        opener = mock.Mock()
        opener.open.side_effect = [
            Response('<table><td>Ads / Captcha</td></table><form id="f1" method="post"></form>'),
            Response(f'<a href="{DIRECT}">Download</a>'),
        ]
        with mock.patch.object(backend, "_onefichier_opener", return_value=opener):
            self.assertEqual(backend.resolve_1fichier_direct_url(SHARE), DIRECT)

    def test_actual_challenge_controls_are_not_bypassed(self):
        for control in ('<div class="g-recaptcha" data-sitekey="test"></div>',
                        '<input name="captcha">',
                        '<textarea name="g-recaptcha-response"></textarea>',
                        '<div class="cf-turnstile"></div>'):
            opener = mock.Mock()
            opener.open.return_value = Response(control)
            with self.subTest(control=control), mock.patch.object(backend, "_onefichier_opener", return_value=opener), self.assertRaisesRegex(ValueError, "사람 확인"):
                backend.resolve_1fichier_direct_url(SHARE)
            self.assertEqual(opener.open.call_count, 1)

    def test_source_password_stays_in_restricted_secret_file(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(backend, "SECRET_DIR", Path(directory)):
            backend.save_job_source_password("0123456789ab", "test-@01")
            self.assertEqual(backend.load_job_source_password("0123456789ab"), "test-@01")
            self.assertNotIn("test-@01", repr(backend.public_inspection({"provider": "1fichier", "url": SHARE})))
            backend.delete_job_secrets("0123456789ab")
            self.assertEqual(backend.load_job_source_password("0123456789ab"), "")

    def test_transfer_has_no_range_or_retry_and_uses_pinned_server(self):
        controller = backend.Controller.__new__(backend.Controller)
        with mock.patch.object(backend, "_resolve_public_addresses", return_value=("1.1.1.1",)):
            script = controller._download_script_1fichier(DIRECT, SHARE, "0123456789ab", 281582,
                                                            "/volume2/downloads/.nasdrop-tmp/0123456789ab",
                                                            "c42.1fichier.com", "1.1.1.1")
        self.assertNotIn(" --range ", script)
        self.assertNotIn("--retry", script)
        self.assertIn('rm -f "$PART" "$PART.more" "$PART.headers"', script)
        self.assertIn("c42.1fichier.com:443:1.1.1.1", script)

    def test_response_filename_corrects_ordinary_and_archive_names(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            controller = backend.Controller.__new__(backend.Controller)
            controller.lock, controller.save = threading.RLock(), mock.Mock()
            for observed in ("테스트 영상.mp4", "압축 파일.zip", "../unsafe.zip"):
                original = workspace / "inspected.bin"
                original.write_bytes(b"demo")
                if observed == "압축 파일.zip":
                    (workspace / observed).write_bytes(b"existing")
                quoted = quote(observed)
                (workspace / ".response-headers").write_bytes(
                    b"HTTP/1.1 302 Found\r\nContent-Disposition: attachment; filename=wrong.bin\r\n\r\n"
                    + f"HTTP/1.1 200 OK\r\nContent-Disposition: attachment; filename*=UTF-8''{quoted}\r\n\r\n".encode()
                )
                job = backend.Job("0123456789ab", "inspected.bin", SHARE, 4, 4, "verifying", "now")
                published = controller._apply_response_filename(job, workspace, original, {"provider": "1fichier"})
                self.assertEqual(published.name, job.name)
                self.assertEqual(published.parent, workspace)
                if observed == "압축 파일.zip":
                    self.assertEqual((workspace / observed).read_bytes(), b"existing")
                    self.assertNotEqual(published.name, observed)
                self.assertFalse((workspace / ".response-headers").exists())

    def test_missing_response_filename_keeps_inspected_name(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            artifact = workspace / "라니.png"
            artifact.write_bytes(b"demo")
            controller = backend.Controller.__new__(backend.Controller)
            job = backend.Job("0123456789ab", "라니.png", SHARE, 4, 4, "verifying", "now")
            self.assertEqual(controller._apply_response_filename(job, workspace, artifact, {"provider": "1fichier"}), artifact)


if __name__ == "__main__":
    unittest.main()
