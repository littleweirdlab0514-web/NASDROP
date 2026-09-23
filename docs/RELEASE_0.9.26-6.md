# NASDrop 0.9.26-6 credential-bootstrap test build

This prerelease replaces the unsuccessful DSM auto-login experiment with the same explicit account-login model used by Docker. Real DSM installation testing is still required.

## Changes

- The DSM icon opens the ordinary NASDrop login page. The auto-login CGI, SynoToken probing, HMAC handoffs, handoff API endpoints, and browser fragment exchange are removed.
- On a **new** Synology installation, the temporary ID and password are both `nasdrop`. They are stored as a salted PBKDF2 hash, never plaintext. The account can only read minimal status/account information, replace credentials, or sign out until **both** ID and password are changed.
- Existing custom NASDrop credentials remain unchanged on update. An untouched `nasdrop` / `nasdrop` account is again forced to change both credentials, and its old sessions are revoked.
- The upgrade script deletes the obsolete `dsm_launcher_secret` and any stale `ui/launcher.cgi` at the package path. The new SPK excludes the CGI, and package validation rejects its return.
- Login and settings copy is updated in English, Korean, Japanese, and Chinese.

## Manual DSM checks

For a fresh install, open the DSM icon, sign in with `nasdrop` / `nasdrop`, verify that downloads and settings are blocked, enter current password `nasdrop`, and save a **different ID** and a new password of 10–128 characters. Sign out and confirm the old credentials fail and the new credentials work. On an upgrade, confirm the prior custom ID/password still works without reset. Also verify that the DSM icon never signs in automatically.

The temporary login must not be left unchanged on an internet-facing installation. Use HTTPS through a trusted reverse proxy. Docker promotion remains gated on successful Synology testing and parity verification.

## Test asset

- File: `nasdrop-0.9.26-6-x86_64.spk`
- SHA-256: `51bdd3f3100ca11ad81535812068072c388c85083d7fdb60f3a47168b884524f`
