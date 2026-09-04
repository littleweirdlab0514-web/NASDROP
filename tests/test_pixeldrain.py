import unittest
from unittest import mock

import backend


class PixeldrainTests(unittest.TestCase):
    def test_metadata_request_uses_current_package_version(self):
        metadata = {
            "success": True,
            "can_download": True,
            "size": 1024,
            "name": "archive.zip",
            "hash_sha256": "a" * 64,
        }
        with mock.patch.object(backend, "_json_request", return_value=metadata) as request:
            result = backend.inspect_pixeldrain("https://pixeldrain.com/u/abcdefgh")
        self.assertEqual(result["provider"], "pixeldrain")
        self.assertEqual(
            request.call_args.kwargs["headers"]["User-Agent"],
            f"NASDrop/{backend.PACKAGE_VERSION}",
        )


if __name__ == "__main__":
    unittest.main()
