import unittest

from backend import pairing_server


class PairingServerTests(unittest.TestCase):
    def test_uses_direct_lan_http_address(self):
        self.assertEqual(pairing_server("192.168.1.20:8791"), "http://192.168.1.20:8791")

    def test_uses_https_reverse_proxy_address(self):
        self.assertEqual(
            pairing_server("127.0.0.1:8791", "nasdrop.example.com:8443", "https"),
            "https://nasdrop.example.com:8443",
        )

    def test_rejects_an_invalid_forwarded_host(self):
        self.assertEqual(
            pairing_server("127.0.0.1:8791", "evil.example/path", "https"),
            "https://127.0.0.1:8791",
        )


if __name__ == "__main__":
    unittest.main()
