# NASDrop 0.9.26-1 security test build

This build addresses the security review findings before wider distribution.

## Security changes

- The DSM launcher no longer stores a bearer token in a world-readable static HTML file. DSM now invokes an administrator-only CGI, validates the current DSM session through Synology's `authenticate.cgi`, and creates an HMAC-signed, 30-second, one-use handoff using a key kept outside the web root.
- A DSM launcher session cannot replace an existing NASDrop account without the current NASDrop password.
- The GoFile WT helper creates all injected objects inside its VM context and runs under Node's permission model without file-write, child-process, worker, addon, or WASI permissions. Regression tests cover both Date and navigator constructor escape paths.
- Send.now DNS results must all be public. Inspection connects to a validated address while retaining the original TLS hostname, and the transfer pins curl to a validated address.
- Docker preserves the documented `nasdrop` / `nasdrop` bootstrap login, stores it only as a salted PBKDF2 hash, and confines it to minimal account/status operations until mandatory replacement. A legacy untouched default account has the mandatory-change flag restored without password rotation. Until replacement, `/api/status` returns only the version and password-change requirement.

## Test gate

Install the SPK manually and verify DSM icon launch while signed in as an administrator, rejection while signed out or as a non-administrator, initial account setup, existing-account password protection, GoFile inspection/download, and one Send.now browser-assisted download. Docker publication remains pending until this Synology build passes the real-NAS test.

## Test asset

- File: `nasdrop-0.9.26-1-x86_64.spk`
- SHA-256: `7F7230FE3E46551C8DA65540A50AA3BCE9271DAD9A6683E65AF2EA59439395A4`
