from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import shutil
import unittest

import backend


def job(job_id: str, target: str, size: int, downloaded: int, status: str) -> backend.Job:
    return backend.Job(
        id=job_id,
        name=f"{job_id}.bin",
        source="https://example.com/file",
        size=size,
        downloaded=downloaded,
        status=status,
        created_at=datetime.now().isoformat(),
        target=target,
    )


class StorageCapacityTests(unittest.TestCase):
    def test_peak_estimate_keeps_parts_final_file_and_safety_reserve(self):
        gib = 1024**3
        self.assertEqual(
            backend.minimum_storage_required(10 * gib, 4 * gib),
            16 * gib + backend.STORAGE_RESERVE_BYTES,
        )

    def test_status_reports_destination_filesystem_capacity(self):
        with TemporaryDirectory(prefix="nasdrop-capacity-") as temporary:
            usage = shutil._ntuple_diskusage(1000, 600, 400)
            with patch("backend.shutil.disk_usage", return_value=usage):
                status = backend.target_storage_status(temporary)
        self.assertEqual(status["available"], True)
        self.assertEqual(status["total_bytes"], 1000)
        self.assertEqual(status["used_bytes"], 600)
        self.assertEqual(status["free_bytes"], 400)

    def test_preflight_rejects_when_current_and_reserved_jobs_exceed_free_space(self):
        with TemporaryDirectory(prefix="nasdrop-capacity-") as temporary:
            file_size = 2 * 1024**3
            required = backend.minimum_storage_required(file_size)
            usage = shutil._ntuple_diskusage(required * 2, required, required - 1)
            with patch("backend.shutil.disk_usage", return_value=usage):
                with self.assertRaises(backend.InsufficientStorageError):
                    backend.ensure_storage_capacity(temporary, file_size)

    def test_only_older_active_jobs_on_same_filesystem_are_reserved(self):
        with TemporaryDirectory(prefix="nasdrop-capacity-") as temporary:
            root = Path(temporary)
            first_target = root / "first"
            second_target = root / "second"
            first_target.mkdir()
            second_target.mkdir()
            gib = 1024**3
            jobs = [
                job("old-active", str(first_target), 3 * gib, 1 * gib, "downloading"),
                job("old-failed", str(first_target), 9 * gib, 0, "failed"),
                job("current", str(second_target), 2 * gib, 0, "downloading"),
                job("newer", str(first_target), 7 * gib, 0, "downloading"),
            ]
            self.assertEqual(
                backend.prior_storage_reservation(jobs, "current", str(second_target)),
                backend.minimum_storage_required(3 * gib, 1 * gib),
            )

    def test_storage_error_is_exposed_as_a_stable_public_code(self):
        self.assertEqual(backend.public_error_code("NAS 저장 공간이 부족합니다."), "insufficient_storage")


if __name__ == "__main__":
    unittest.main()
