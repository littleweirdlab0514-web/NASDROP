# NASDrop 0.9.26-6 stable release

This stable release replaces the unsuccessful DSM auto-login experiment with the same explicit account-login model used by Docker. The user confirmed the installed Synology package works; Docker amd64 and arm64 smoke tests passed against the identical canonical server source.

DSM auto-login was dropped because the older static launcher token risked exposing NASDrop access, while the replacement DSM-session checks failed repeatedly on the real NAS. The DSM icon now only opens NASDrop. Users sign in separately with a NASDrop account, which makes the authentication boundary explicit across DSM, direct browsers, and client apps.

## Changes

- The DSM icon opens the ordinary NASDrop login page. The auto-login CGI, SynoToken probing, HMAC handoffs, handoff API endpoints, and browser fragment exchange are removed.
- On a **new** Synology installation, the temporary ID and password are both `nasdrop`. They are stored as a salted PBKDF2 hash, never plaintext. The account can only read minimal status/account information, replace credentials, or sign out until **both** ID and password are changed.
- Existing custom NASDrop credentials remain unchanged on update. An untouched `nasdrop` / `nasdrop` account is again forced to change both credentials, and its old sessions are revoked.
- The upgrade script deletes the obsolete `dsm_launcher_secret` and any stale `ui/launcher.cgi` at the package path. The new SPK excludes the CGI, and package validation rejects its return.
- Login and settings copy is updated in English, Korean, Japanese, and Chinese.

## Manual DSM checks

For a fresh install, open the DSM icon, sign in with `nasdrop` / `nasdrop`, verify that downloads and settings are blocked, enter current password `nasdrop`, and save a **different ID** and a new password of 10–128 characters. Sign out and confirm the old credentials fail and the new credentials work. On an upgrade, confirm the prior custom ID/password still works without reset. Also verify that the DSM icon never signs in automatically.

The temporary login must not be left unchanged on an internet-facing installation. Use HTTPS through a trusted reverse proxy. Docker promotion reused the verified multi-platform candidate manifest digest `sha256:ac92592779f5c0a720c1a483cd984de803861c598af306a0bbb9aed0a130036c` without rebuilding it.

## Test asset

- File: `nasdrop-0.9.26-6-x86_64.spk`
- SHA-256: `51bdd3f3100ca11ad81535812068072c388c85083d7fdb60f3a47168b884524f`
