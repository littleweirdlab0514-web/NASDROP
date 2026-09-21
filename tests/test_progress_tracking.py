from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import backend


class ProgressTrackingTests(unittest.TestCase):
    def test_segment_sizes_are_counted_when_filename_contains_glob_characters(self):
        controller = backend.Controller.__new__(backend.Controller)
        with TemporaryDirectory(prefix="nasdrop-progress-") as temporary:
            directory = Path(temporary)
            name = "괜찮다 Audio[Kor(HK)]+Chi+Eng.mp4"
            prefix = directory / f".{name}.abc123.segment."
            (directory / f"{prefix.name}0").write_bytes(b"a" * 17)
            (directory / f"{prefix.name}1").write_bytes(b"b" * 23)
            (directory / f"{prefix.name}1.more").write_bytes(b"c" * 11)
            (directory / f"unrelated-{prefix.name}2").write_bytes(b"d" * 100)

            (directory / f"{prefix.name}1.headers").write_bytes(b'HTTP/1.1 206 OK\r\nContent-Range: bytes 73-99/100\r\n\r\n')
            self.assertEqual(controller._local_size(str(prefix), 100, 'segmented2'), 51)

    def test_missing_progress_directory_returns_zero(self):
        controller = backend.Controller.__new__(backend.Controller)
        self.assertEqual(controller._local_size("Z:/definitely-missing/.file.segment.", 100, 'single'), 0)

    def test_copying_partial_fragment_never_counts_bytes_twice(self):
        c = backend.Controller.__new__(backend.Controller)
        with TemporaryDirectory() as tmp:
            prefix = Path(tmp) / '.job.segment.'
            part = Path(str(prefix) + '0')
            more = Path(str(part) + '.more')
            headers = Path(str(part) + '.headers')
            more.write_bytes(b'x' * 60)
            headers.write_bytes(b'HTTP/1.1 206 OK\r\nContent-Range: bytes 0-99/100\r\n\r\n')
            for copied in (0, 20, 60):
                part.write_bytes(b'x' * copied)
                self.assertEqual(c._local_size(str(prefix), 100, 'single'), 60)
            more.unlink(); headers.unlink()
            self.assertEqual(c._local_size(str(prefix), 100, 'single'), 60)
            more.write_bytes(b'x' * 30)
            headers.write_bytes(b'HTTP/1.1 206 OK\r\nContent-Range: bytes 60-99/100\r\n\r\n')
            for copied in (60, 75, 90):
                part.write_bytes(b'x' * copied)
                self.assertEqual(c._local_size(str(prefix), 100, 'single'), 90)

    def test_error_bodies_headers_and_wrong_ranges_are_not_progress(self):
        c = backend.Controller.__new__(backend.Controller)
        with TemporaryDirectory() as tmp:
            prefix = Path(tmp) / '.job.segment.'
            part = Path(str(prefix) + '0')
            part.write_bytes(b'x' * 20)
            Path(str(part) + '.more').write_bytes(b'x' * 70)
            Path(str(prefix) + '7').write_bytes(b'x' * 200)
            headers = Path(str(part) + '.headers')
            for raw in (b'', b'HTTP/1.1 403 Denied\r\n\r\n',
                        b'HTTP/1.1 206 OK\r\nContent-Range: bytes 30-99/100\r\n\r\n',
                        b'HTTP/1.1 206 OK\r\nContent-Range: bytes 20-99/101\r\n\r\n'):
                headers.write_bytes(raw)
                self.assertEqual(c._local_size(str(prefix), 100, 'single'), 20)


if __name__ == "__main__":
    unittest.main()
