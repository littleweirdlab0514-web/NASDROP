# NASDrop 0.9.26-5 DSM launcher test build

This prerelease tests a second DSM authentication route for NAS installations where both direct `authenticate.cgi` calls produce empty output. It has not yet been confirmed on a real DSM device.

## Changes

- When direct authentication returns only empty/unavailable results, retry through the DSM HTTP listener on `127.0.0.1` with the incoming DSM session cookie.
- If needed, obtain a SynoToken from a successful `login.cgi` response (root or nested `data` form) and retry. JSON errors and failed login responses are never accepted as credentials.
- Disable proxy use and redirects on these loopback requests to prevent the DSM cookie from being forwarded elsewhere. Bound the port, cookie, response size, and timeout.
- Keep administrator-group verification and the 30-second one-use handoff. No static bearer token or separate NASDrop login fallback is restored.

## Manual DSM check

Install this SPK, sign in to DSM as an administrator, and open NASDrop from the DSM icon. It should not ask for another login. Then verify that a signed-out or non-administrator DSM request cannot obtain a NASDrop session. Report only the secret-free error category if it fails; never share cookies or tokens.

Docker parity and promotion remain gated on this real DSM result.

## Test asset

- File: `nasdrop-0.9.26-5-x86_64.spk`
- SHA-256: `5C585E3F7BB5B3C59E262BBB67CFD7A919D4C2F88A3203220938FF5BFBC9AA03`
