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

            self.assertEqual(controller._local_size(str(prefix)), 51)

    def test_missing_progress_directory_returns_zero(self):
        controller = backend.Controller.__new__(backend.Controller)
        self.assertEqual(controller._local_size("Z:/definitely-missing/.file.segment."), 0)


if __name__ == "__main__":
    unittest.main()
