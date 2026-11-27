# NASDrop 0.9.30-3 — GoFile DNS compatibility candidate

- Falls back to Cloudflare DNS-over-HTTPS when the NAS or ISP resolver cannot resolve a verified `*.gofile.io` delivery host.
- Accepts only public A records and pins the validated address in curl while TLS verifies the original GoFile hostname.
- Supports the permission-flag names used by Docker's Node 20 and current Node releases without running the GoFile token helper outside its filesystem sandbox.
- Retains the NAS capacity protection from 0.9.30-2 and X-Share recovery from 0.9.30-1.

The supplied `https://gofile.io/d/BiPUMun6` share was verified through metadata inspection and a one-byte HTTP 206 range transfer; the full 6.84 GB file was not downloaded during testing.
