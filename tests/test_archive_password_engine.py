import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import backend


@unittest.skipUnless(os.environ.get('NASDROP_TEST_7ZIP'), 'Set NASDROP_TEST_7ZIP for real engine tests')
class ArchivePasswordEngineTests(unittest.TestCase):
    def test_real_encrypted_zip_password_transport(self):
        engine = Path(os.environ['NASDROP_TEST_7ZIP'])
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(backend, 'SEVEN_ZIP', engine):
            root = Path(temp)
            source = root / 'sample.txt'
            source.write_bytes(b'Synthetic password regression fixture.')
            password = 'test-admin-$&! punctuation'
            for method in ('ZipCrypto', 'AES256'):
                with self.subTest(method=method):
                    archive = root / (method + '.zip')
                    # Synthetic test password only; no user secrets in argv/fixtures.
                    subprocess.run([str(engine), 'a', '-tzip', '-mem=' + method,
                                    '-p' + password, str(archive), str(source)],
                                   capture_output=True, check=True, timeout=30)
                    backend._validate_seven_zip_listing(archive, password)
                    destination = root / method
                    destination.mkdir()
                    backend._extract_with_seven_zip(archive, destination, password)
                    self.assertEqual((destination / 'sample.txt').read_bytes(), source.read_bytes())
                    with self.assertRaises(backend.PasswordRequiredError):
                        backend._run_seven_zip(['t', str(archive)], 'deliberately-wrong', timeout=30)
