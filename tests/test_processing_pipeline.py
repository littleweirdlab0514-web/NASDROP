import io
import os
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest import mock
import zipfile


_state = tempfile.TemporaryDirectory(prefix="nasdrop-processing-test-")
os.environ["NAS_PORTAL_STATE_DIR"] = _state.name

import backend


class ProcessingPipelineTests(unittest.TestCase):
    def test_content_disposition_restores_hidden_gigafile_name_for_regular_file(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            headers = workspace / ".response-headers"
            headers.write_bytes(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Disposition: attachment; filename=hidden.mp4; "
                b"filename*=UTF-8''%ED%82%A4%EC%8A%A4%EB%B0%A9%EB%85%80%20%EB%AA%A8%EC%9D%8C.mp4\r\n\r\n"
            )
            placeholder = "●ファイル名が置換されました※DLしたファイルは、原題まま表示されます。●"
            artifact = workspace / placeholder
            artifact.write_bytes(b"video")
            job = backend.Job("0123456789ab", placeholder, "https://110.gigafile.nu/example", 5, 5, "verifying", "now")
            controller = backend.Controller.__new__(backend.Controller)
            controller.lock = backend.threading.RLock()
            controller.save = mock.Mock()

            renamed = controller._apply_response_filename(job, workspace, artifact, {"provider": "gigafile"})

            self.assertEqual(renamed.name, "키스방녀 모음.mp4")
            self.assertEqual(job.name, "키스방녀 모음.mp4")
            self.assertEqual(renamed.read_bytes(), b"video")
            self.assertFalse(headers.exists())

    def test_gigafile_script_captures_response_filename_without_body_probe(self):
        controller = backend.Controller.__new__(backend.Controller)
        script = controller._download_script(
            "110.gigafile.nu", "example", "placeholder", "0123456789ab", 1024,
            "/volume2/downloads/.nasdrop-tmp/0123456789ab",
        )
        self.assertIn(".response-headers", script)
        self.assertIn(" -I ", script)

    def test_response_filename_uses_last_redirect_header_and_sanitizes_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            headers = Path(temp) / "headers"
            headers.write_bytes(
                b"HTTP/1.1 302 Found\r\nContent-Disposition: attachment; filename=wrong.bin\r\n\r\n"
                b"HTTP/1.1 200 OK\r\nContent-Disposition: attachment; "
                b"filename*=UTF-8''..%2Ffinal%20name.mp4\r\n\r\n"
            )
            name = backend.response_download_name(headers)
            self.assertEqual(name, ".._final name.mp4")
            self.assertNotIn("/", name)
            self.assertNotIn("\\", name)

    def test_missing_content_disposition_keeps_inspected_name(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            artifact = workspace / "inspected-name.mkv"
            artifact.write_bytes(b"video")
            job = backend.Job("0123456789ab", artifact.name, "https://110.gigafile.nu/example", 5, 5, "verifying", "now")
            controller = backend.Controller.__new__(backend.Controller)
            controller.lock = backend.threading.RLock()
            controller.save = mock.Mock()

            result = controller._apply_response_filename(job, workspace, artifact, {"provider": "gigafile"})

            self.assertEqual(result, artifact)
            self.assertEqual(job.name, "inspected-name.mkv")

    def test_actual_archive_name_controls_archive_detection_and_folder_name(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / ".response-headers").write_text(
                "HTTP/1.1 200 OK\r\nContent-Disposition: attachment; filename=actual.zip\r\n\r\n",
                encoding="ascii",
            )
            artifact = workspace / "masked-name"
            artifact.write_bytes(b"archive")
            job = backend.Job("0123456789ab", artifact.name, "https://110.gigafile.nu/example", 7, 7, "verifying", "now")
            controller = backend.Controller.__new__(backend.Controller)
            controller.lock = backend.threading.RLock()
            controller.save = mock.Mock()

            renamed = controller._apply_response_filename(job, workspace, artifact, {"provider": "gigafile"})

            self.assertEqual(backend.archive_kind(job.name), "zip")
            self.assertEqual(backend.archive_output_name(renamed.name), "actual")

    def test_segment_assembly_happens_in_python_postprocessing(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            job = backend.Job("0123456789ab", "joined.bin", "https://example.com", 16, 16, "verifying", "now")
            for index in range(8):
                (workspace / f".{job.name}.{job.id}.segment.{index}").write_bytes(bytes([index]) * 2)
            controller = backend.Controller.__new__(backend.Controller)

            artifact, digest = controller._assemble_artifact(job, workspace, {})

            self.assertEqual(artifact.read_bytes(), b"".join(bytes([index]) * 2 for index in range(8)))
            self.assertEqual(digest, backend.hashlib.sha256(artifact.read_bytes()).hexdigest())
            self.assertFalse(any(workspace.glob("*.segment.*")))

    def test_download_scripts_leave_segments_for_disk_protected_processing(self):
        controller = backend.Controller.__new__(backend.Controller)
        script = controller._download_script_direct(
            "https://example.com/file", "https://example.com/page", "file.bin", "0123456789ab", 1024, "/volume2/downloads/.nasdrop-tmp/0123456789ab",
        )
        self.assertIn("SEGMENTS_READY", script)
        self.assertNotIn("sha256sum", script)
        self.assertNotIn("cat /volume2", script)

    def test_rar_and_7z_are_recognized_by_external_engine(self):
        self.assertEqual(backend.archive_kind("backup.7z"), "7zip")
        self.assertEqual(backend.archive_kind("BACKUP.RAR"), "7zip")
        self.assertEqual(backend.archive_output_name("BACKUP.RAR"), "BACKUP")

    def test_password_is_stored_separately_and_removed(self):
        job_id = "0123456789ab"
        backend.save_job_password(job_id, "secret value")
        path = backend._job_secret_path(job_id)
        try:
            self.assertEqual(backend.load_job_password(job_id), "secret value")
            self.assertNotIn("secret value", repr(backend.Job(job_id, "a.zip", "https://example.com", 1, 0, "queued", "now")))
        finally:
            backend.delete_job_password(job_id)
        self.assertFalse(path.exists())

    def test_external_engine_password_failure_becomes_retryable_state(self):
        with tempfile.TemporaryDirectory() as temp:
            engine = Path(temp) / "7zz"
            engine.write_bytes(b"placeholder")
            result = backend.subprocess.CompletedProcess([], 2, "", "ERROR: Wrong password")
            with mock.patch.object(backend, "SEVEN_ZIP", engine), mock.patch.object(backend.subprocess, "run", return_value=result):
                with self.assertRaises(backend.PasswordRequiredError):
                    backend._run_seven_zip(["x", "archive.7z"], "incorrect")

    def test_external_engine_listing_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            engine = Path(temp) / "7zz"
            engine.write_bytes(b"placeholder")
            listing = "Path = ../escape.txt\nSize = 4\nAttributes = A\n\n"
            result = backend.subprocess.CompletedProcess([], 0, listing, "")
            with mock.patch.object(backend, "SEVEN_ZIP", engine), mock.patch.object(backend.subprocess, "run", return_value=result):
                with self.assertRaisesRegex(ValueError, "벗어나는 경로"):
                    backend._validate_seven_zip_listing(Path(temp) / "archive.rar", "")

    def test_workspace_is_hidden_and_scoped_to_target(self):
        with tempfile.TemporaryDirectory() as target:
            workspace = backend.job_workspace(target, "0123456789ab")
            self.assertEqual(workspace, Path(target).resolve() / ".nasdrop-tmp" / "0123456789ab")
            with self.assertRaises(ValueError):
                backend.job_workspace(target, "../outside")

    def test_legacy_parts_are_moved_into_new_workspace_for_upgrade_resume(self):
        with tempfile.TemporaryDirectory() as target_value:
            target = Path(target_value)
            job_id = "0123456789ab"
            name = "archive.zip"
            old_part = target / f".{name}.{job_id}.segment.0"
            old_more = target / f".{name}.{job_id}.segment.0.more"
            unrelated = target / f".{name}.{job_id}.other"
            old_part.write_bytes(b"part")
            old_more.write_bytes(b"more")
            unrelated.write_bytes(b"keep")
            workspace = backend.job_workspace(target_value, job_id)
            workspace.mkdir(parents=True)

            moved = backend.migrate_legacy_workspace(target_value, name, job_id, workspace)

            self.assertEqual(moved, 2)
            self.assertEqual((workspace / old_part.name).read_bytes(), b"part")
            self.assertEqual((workspace / old_more.name).read_bytes(), b"more")
            self.assertFalse(old_part.exists())
            self.assertTrue(unrelated.exists())

    def test_regular_file_is_promoted_without_overwriting_existing_file(self):
        with tempfile.TemporaryDirectory() as target_value:
            target = Path(target_value)
            (target / "movie.mkv").write_bytes(b"old")
            workspace = target / ".nasdrop-tmp" / "0123456789ab"
            workspace.mkdir(parents=True)
            artifact = workspace / "movie.mkv"
            artifact.write_bytes(b"new")

            output, extracted = backend.promote_download(artifact, target_value, auto_extract=True)

            self.assertFalse(extracted)
            self.assertEqual(output.name, "movie (1).mkv")
            self.assertEqual(output.read_bytes(), b"new")
            self.assertEqual((target / "movie.mkv").read_bytes(), b"old")

    def test_zip_is_extracted_to_archive_named_folder(self):
        with tempfile.TemporaryDirectory() as target_value:
            target = Path(target_value)
            workspace = target / ".nasdrop-tmp" / "0123456789ab"
            workspace.mkdir(parents=True)
            artifact = workspace / "photos.zip"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("one.jpg", b"one")
                archive.writestr("album/two.jpg", b"two")

            output, extracted = backend.promote_download(artifact, target_value, auto_extract=True)

            self.assertTrue(extracted)
            self.assertEqual(output, target / "photos")
            self.assertEqual((output / "one.jpg").read_bytes(), b"one")
            self.assertEqual((output / "album" / "two.jpg").read_bytes(), b"two")
            self.assertTrue(artifact.exists(), "archive remains private until workspace cleanup")

    def test_cp949_zip_filename_without_utf8_flag_is_restored(self):
        with tempfile.TemporaryDirectory() as target_value:
            target = Path(target_value)
            workspace = target / ".nasdrop-tmp" / "0123456789ab"
            workspace.mkdir(parents=True)
            artifact = workspace / "legacy-korean.zip"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("ab.txt", b"subtitle")

            encoded = artifact.read_bytes()
            self.assertEqual(encoded.count(b"ab.txt"), 2)
            artifact.write_bytes(encoded.replace(b"ab.txt", "가.txt".encode("cp949")))

            output, extracted = backend.promote_download(artifact, target_value, auto_extract=True)

            self.assertTrue(extracted)
            self.assertEqual((output / "가.txt").read_bytes(), b"subtitle")
            self.assertFalse((output / "\u2562\u2591.txt").exists())

    def test_matching_single_top_level_folder_is_not_double_nested(self):
        with tempfile.TemporaryDirectory() as target_value:
            target = Path(target_value)
            workspace = target / ".nasdrop-tmp" / "0123456789ab"
            workspace.mkdir(parents=True)
            artifact = workspace / "album.zip"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("album/song.flac", b"audio")

            output, extracted = backend.promote_download(artifact, target_value, auto_extract=True)

            self.assertTrue(extracted)
            self.assertEqual((output / "song.flac").read_bytes(), b"audio")
            self.assertFalse((output / "album").exists())

    def test_matching_top_level_folder_stays_flat_when_destination_name_collides(self):
        with tempfile.TemporaryDirectory() as target_value:
            target = Path(target_value)
            (target / "album").mkdir()
            workspace = target / ".nasdrop-tmp" / "0123456789ab"
            workspace.mkdir(parents=True)
            artifact = workspace / "album.zip"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("album/song.flac", b"audio")

            output, _ = backend.promote_download(artifact, target_value, auto_extract=True)

            self.assertEqual(output, target / "album (1)")
            self.assertEqual((output / "song.flac").read_bytes(), b"audio")
            self.assertFalse((output / "album").exists())

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as target_value:
            target = Path(target_value)
            workspace = target / ".nasdrop-tmp" / "0123456789ab"
            workspace.mkdir(parents=True)
            artifact = workspace / "unsafe.zip"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("../escape.txt", b"blocked")

            with self.assertRaisesRegex(ValueError, "벗어나는 경로"):
                backend.promote_download(artifact, target_value, auto_extract=True)
            self.assertFalse((target.parent / "escape.txt").exists())

    def test_compressed_tar_is_extracted(self):
        with tempfile.TemporaryDirectory() as target_value:
            target = Path(target_value)
            workspace = target / ".nasdrop-tmp" / "0123456789ab"
            workspace.mkdir(parents=True)
            artifact = workspace / "documents.tar.gz"
            payload = b"report"
            info = tarfile.TarInfo("report.txt")
            info.size = len(payload)
            with tarfile.open(artifact, "w:gz") as archive:
                archive.addfile(info, io.BytesIO(payload))

            output, extracted = backend.promote_download(artifact, target_value, auto_extract=True)

            self.assertTrue(extracted)
            self.assertEqual(output, target / "documents")
            self.assertEqual((output / "report.txt").read_bytes(), payload)

    def test_zip_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as target_value:
            target = Path(target_value)
            workspace = target / ".nasdrop-tmp" / "0123456789ab"
            workspace.mkdir(parents=True)
            artifact = workspace / "link.zip"
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr(info, "../../outside")

            with self.assertRaisesRegex(ValueError, "심볼릭 링크"):
                backend.promote_download(artifact, target_value, auto_extract=True)


if __name__ == "__main__":
    unittest.main()
