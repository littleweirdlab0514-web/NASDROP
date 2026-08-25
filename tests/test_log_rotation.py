import logging
import os
import tempfile
import unittest


_state = tempfile.TemporaryDirectory(prefix="nasdrop-log-test-")
os.environ["NAS_PORTAL_STATE_DIR"] = _state.name

from backend import rotating_log_handler


class LogRotationTests(unittest.TestCase):
    def test_log_size_is_bounded_and_only_two_backups_are_kept(self):
        with tempfile.TemporaryDirectory(prefix="nasdrop-rotation-") as directory:
            path = os.path.join(directory, "service.log")
            handler = rotating_log_handler(path, max_bytes=256, backup_count=2)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger = logging.getLogger(f"nasdrop-rotation-{id(self)}")
            logger.handlers = [handler]
            logger.propagate = False
            logger.setLevel(logging.INFO)

            for index in range(100):
                logger.info("request-%03d %s", index, "x" * 40)
            handler.close()
            logger.handlers = []

            logs = sorted(name for name in os.listdir(directory) if name.startswith("service.log"))
            self.assertEqual(logs, ["service.log", "service.log.1", "service.log.2"])
            self.assertLessEqual(sum(os.path.getsize(os.path.join(directory, name)) for name in logs), 768)


if __name__ == "__main__":
    unittest.main()
