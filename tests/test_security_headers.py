import io
import unittest

import backend


class SecurityHeaderTests(unittest.TestCase):
    def test_all_handler_responses_receive_browser_security_headers(self):
        handler = backend.Handler.__new__(backend.Handler)
        handler.request_version = "HTTP/1.1"
        handler._headers_buffer = []
        handler.wfile = io.BytesIO()

        handler.end_headers()

        headers = handler.wfile.getvalue().decode("latin-1")
        self.assertIn("Content-Security-Policy: default-src 'self'", headers)
        self.assertIn("frame-ancestors 'none'", headers)
        self.assertIn("Referrer-Policy: no-referrer", headers)
        self.assertIn("X-Content-Type-Options: nosniff", headers)
        self.assertIn("X-Frame-Options: DENY", headers)
        self.assertIn("Permissions-Policy: camera=(), microphone=(), geolocation=()", headers)

    def test_metadata_redirects_cannot_change_host_or_downgrade_https(self):
        handler = backend.SameHostHTTPSRedirectHandler("api.gofile.io")
        request = backend.Request("https://api.gofile.io/contents/example")

        for target in (
            "http://api.gofile.io/contents/example",
            "https://127.0.0.1/private",
            "https://evil.example/private",
        ):
            with self.subTest(target=target), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "Found", {}, target)

    def test_gigafile_redirects_stay_on_the_original_https_host(self):
        handler = backend.GigaFileRedirectHandler("83.gigafile.nu")
        request = backend.Request("https://83.gigafile.nu/example")

        with self.assertRaises(ValueError):
            handler.redirect_request(request, None, 302, "Found", {}, "https://127.0.0.1/private")


if __name__ == "__main__":
    unittest.main()
