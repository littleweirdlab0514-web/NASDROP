from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import backend


class StorageRootTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="nasdrop-storage-")
        self.root = Path(self.temporary.name).resolve()
        self.downloads = self.root / "downloads"
        self.downloads.mkdir()
        self.original_roots = backend.STORAGE_ROOTS
        backend.STORAGE_ROOTS = (self.downloads,)

    def tearDown(self):
        backend.STORAGE_ROOTS = self.original_roots
        self.temporary.cleanup()

    def test_generic_mounted_root_is_selectable_and_browsable(self):
        child = self.downloads / "movies"
        child.mkdir()
        self.assertEqual(backend.normalize_target(str(self.downloads)), str(self.downloads))
        root_listing = backend.browse_folders("/")
        self.assertEqual(root_listing["folders"][0]["path"], str(self.downloads))
        listing = backend.browse_folders(str(self.downloads))
        self.assertEqual(listing["parent"], "/")
        self.assertEqual(listing["folders"][0]["path"], str(child))

    def test_paths_outside_configured_mounts_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "허용된 저장소"):
            backend.normalize_target(str(self.root))
        with self.assertRaisesRegex(ValueError, "탐색할 수 없는"):
            backend.browse_folders(str(self.root))


if __name__ == "__main__":
    unittest.main()
