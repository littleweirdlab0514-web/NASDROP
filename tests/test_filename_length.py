from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote

import backend


class FilenameLengthTests(unittest.TestCase):
    def test_utf8_budget_keeps_extension_and_does_not_split_characters(self):
        for suffix in ['.mp4', '.ZIP', '.tar.gz', '.7z']:
            name = '한글日本語😀' * 80 + suffix
            safe = backend._clean_download_name(name)
            self.assertLessEqual(len(safe.encode('utf-8')), 240)
            self.assertTrue(safe.endswith(suffix))
            self.assertNotIn('\ufffd', safe)
            self.assertEqual(backend._clean_download_name(safe), safe)
        self.assertEqual(backend._clean_download_name('짧은 이름.mp4'), '짧은 이름.mp4')

    def test_truncated_names_remain_distinct_and_collisions_stay_bounded(self):
        prefix = '가' * 180
        self.assertNotEqual(backend._clean_download_name(prefix+'A.zip'), backend._clean_download_name(prefix+'B.zip'))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / backend._clean_download_name(prefix+'.zip')
            path.write_bytes(b'old')
            other = backend.unique_destination(path)
            self.assertNotEqual(other, path)
            self.assertLessEqual(len(other.name.encode()), 240)
            self.assertTrue(other.name.endswith('.zip'))
            self.assertEqual(path.read_bytes(), b'old')

    def test_actual_header_name_obeys_byte_budget(self):
        for suffix in ['.mp4', '.zip']:
            header = ("attachment; filename*=UTF-8''" + quote('긴제목' * 100 + suffix)).encode()
            name = backend.content_disposition_download_name([header])
            self.assertLessEqual(len(name.encode()), 240)
            self.assertTrue(name.endswith(suffix))

    def test_short_transfer_paths_and_assembly(self):
        name = backend._clean_download_name('긴파일명' * 100 + '.mp4')
        controller = backend.Controller.__new__(backend.Controller)
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            job = backend.Job('0123456789ab', name, 'https://example.gigafile.nu/id', 16, 16, 'verifying', 'now')
            for i in range(8):
                (workspace / f'.{job.id}.segment.{i}').write_bytes(b'ab')
            artifact, digest = controller._assemble_artifact(job, workspace, {})
            self.assertEqual(artifact.read_bytes(), b'ab' * 8)
            for script in [controller._download_script('example.gigafile.nu','id',name,job.id,16,temp),
                           controller._download_script_direct('https://example.org/file','https://example.org',name,job.id,16,temp)]:
                self.assertNotIn(name, script)
                self.assertIn(f'.{job.id}.segment', script)

    def test_existing_hidden_workspace_parts_migrate_without_loss(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            workspace = target / 'workspace'
            workspace.mkdir()
            old = workspace / '.old.mp4.0123456789ab.segment.0'
            old.write_bytes(b'partial')
            self.assertEqual(backend.migrate_legacy_workspace(temp,'old.mp4','0123456789ab',workspace),1)
            self.assertEqual((workspace / '.0123456789ab.segment.0').read_bytes(), b'partial')
            self.assertFalse(old.exists())
            self.assertEqual(backend.migrate_legacy_workspace(temp,'old.mp4','0123456789ab',workspace),0)


if __name__ == '__main__':
    unittest.main()
