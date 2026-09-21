from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import backend
from test_browser_handoff import SHARES, Response, direct
from test_handoff_redirects import redirect


class HandoffDiagnosticsTests(unittest.TestCase):
    def test_untrusted_host_is_not_disclosed_or_contacted(self):
        opener = mock.Mock()
        opener.open.side_effect = redirect(direct('vikingfile'), 'https://private-secret.example/path?token=secret')
        with mock.patch.object(backend, 'build_opener', return_value=opener), self.assertRaises(ValueError) as caught:
            backend.inspect_browser_handoff(SHARES['vikingfile'], direct('vikingfile'), 'vikingfile')
        self.assertIn('허용 목록에 없는', str(caught.exception))
        self.assertNotIn('[', str(caught.exception))
        self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(opener.open.call_count, 1)

    def test_bad_metadata_is_redacted(self):
        for field, value, code in [('Content-Length', 'secret-url', '파일 크기 응답'),
                                   ('Content-Type', 'text/html', '오류 페이지')]:
            response = Response(direct('vikingfile'))
            if field in response.headers:
                response.headers.replace_header(field, value)
            else:
                response.headers[field] = value
            with mock.patch.object(backend, 'build_opener') as factory, self.assertRaises(ValueError) as caught:
                factory.return_value.open.return_value = response
                backend.inspect_browser_handoff(SHARES['vikingfile'], direct('vikingfile'), 'vikingfile')
            self.assertIn(code, str(caught.exception))
            self.assertNotIn('[', str(caught.exception))
            self.assertNotIn('secret-url', str(caught.exception))

    def test_transfer_errors_use_only_numeric_markers(self):
        for rc in (18, 28, 22, 23, 47, 56):
            message = backend.handoff_transfer_error(f'secret-token\nNASDROP_TRANSFER curl={rc} merge=0 attempt=3')
            self.assertNotIn('[', message)
            self.assertNotIn('CURL_', message)
            self.assertNotIn('secret', message)
        self.assertIn('다운로드가 중단', backend.handoff_transfer_error('secret'))

    def test_real_shell_resume_and_bounded_failures(self):
        bash = shutil.which('bash') or r'C:\Program Files\Git\bin\bash.exe'
        if not Path(bash).exists():
            self.skipTest('bash required')
        # Use real fragment verification and shell control flow. The fake transport
        # delivers one byte then fails; delays are recorded rather than slept.
        for rc, status, retries, expected_calls in [(18, 206, 3, 4), (28, 206, 3, 4),
                                                    (18, 206, 0, 1), (22, 403, 3, 1),
                                                    (22, 429, 3, 1), (23, 206, 3, 1),
                                                    (18, 200, 3, 2), (0, 206, 3, 2)]:
            with self.subTest(rc=rc, status=status, retries=retries), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                prefix = (root / 'part').as_posix()
                fake = f'''fakecurl() {{
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -r) range="$2"; shift 2;;
      --dump-header) hdr="$2"; shift 2;;
      -o) out="$2"; shift 2;;
      *) shift;;
    esac
  done
  first=${{range%-*}}
  printf '%s\\n' "$first" >> {shlex.quote((root / 'calls').as_posix())}
  printf 'HTTP/1.1 {status} Test\\r\\nContent-Range: bytes %s-7/8\\r\\n\\r\\n' "$first" > "$hdr"
  printf x > "$out"
  if [ {rc} -eq 0 ]; then
    if [ "$first" -eq 0 ]; then return 18; fi
    printf xxxxxxx > "$out"
  fi
  return {rc}
}}
sleep() {{ printf '%s\\n' "$1" >> {shlex.quote((root / 'delays').as_posix())}; }}
'''
                script = 'set -eu\nPATH=/usr/bin:/bin:$PATH\n' + fake + backend.Controller._transfer_loop(prefix, 8, 'single', 'fakecurl', transient_retries=retries)
                result = subprocess.run([bash, '-s'], input=script, text=True, capture_output=True, timeout=20)
                if rc == 0:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((root / 'part.0').read_bytes(), b'xxxxxxxx')
                else:
                    self.assertNotEqual(result.returncode, 0)
                calls = (root / 'calls').read_text().splitlines()
                self.assertEqual(len(calls), expected_calls, result.stderr)
                self.assertEqual(calls, [str(i) for i in range(expected_calls)])
                if expected_calls == 4:
                    self.assertEqual((root / 'delays').read_text().splitlines(), ['10', '20', '30'])
                    self.assertEqual((root / 'part.0').read_bytes(), b'xxxx')
