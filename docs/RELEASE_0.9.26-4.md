# NASDrop 0.9.26-4 DSM auto-launch test build

This Synology package revision restores the intended DSM icon behavior without returning to a reusable token in a static file. It requires verification on a real DSM installation before being treated as a confirmed fix.

## Changes

- The launcher checks both DSM authenticator locations. If the first cookie-only checks do not return a valid username, it asks DSM `login.cgi` for the current session's SynoToken and retries authentication with the token in the query string and request header.
- JSON failures such as DSM error 119 cannot be mistaken for usernames. Administrator-group membership remains required before a short-lived, one-use NASDrop handoff is created.
- The temporary `0.9.26-3` redirection to a separate NASDrop login is removed. A failed DSM authentication shows a secret-free diagnostic category instead of granting access or opening an unrelated login flow.
- No DSM cookie, SynoToken, account password, or handoff value is written to a static launcher file or diagnostic message.

## Manual DSM checks

Install the SPK, sign in to DSM as an administrator, and open NASDrop from the DSM icon. It should open without another login. Then verify that a signed-out request and a non-administrator session cannot obtain a NASDrop session. If it still fails, report only the diagnostic category shown in parentheses; do not copy cookies, tokens, or session IDs.

Docker and direct NASDrop clients are unchanged. Docker parity and promotion remain gated on the real DSM result.

## Test asset

- File: `nasdrop-0.9.26-4-x86_64.spk`
- SHA-256: `6CFDEEE189760AAE2A4573F08B39CAA813DCC9C7059F8FB4AF92395B87C396F1`
