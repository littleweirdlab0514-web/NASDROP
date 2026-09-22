# NASDrop 0.9.23-3

NASDrop 0.9.23-3 fixes first-run access for the Docker distribution while preserving existing installations.

## Docker first-run login

- A new empty `/config` volume receives temporary ID `nasdrop` and temporary password `nasdrop` automatically.
- The temporary password is a bootstrap-only exception. New passwords still require 10–128 characters.
- After the temporary login, NASDrop permits only account replacement, account/status reads, and logout. Download, folder, settings, and job APIs return HTTP 403 with `password_change_required` until the credentials are changed.
- The web portal immediately opens the account form, hides other operations, and requires the current temporary password plus a new ID and strong password.
- A successful change removes the bootstrap flag, revokes every old session, and returns one new session.
- Existing `credentials.json` files are never overwritten. Native Synology account and DSM launcher initialization remain unchanged.
- Chrome recognizes the `password_change_required` contract and directs the user to complete the change in the web portal.

## Downloads

- Synology DSM 7.1 or later on x86_64: `nasdrop-0.9.23-3-x86_64.spk`
- Docker: `ghcr.io/littleweirdlab0514-web/nasdrop:0.9.23-3`

The Docker image supports `linux/amd64` and `linux/arm64`. Docker selects the correct platform automatically. See the [Docker installation guide](DOCKER_INSTALL.md) or the [Korean Docker installation guide](DOCKER_INSTALL.ko.md).

## Verification

- Python regression suite: 187 tests passed on amd64 and arm64; one platform-dependent test skipped
- JavaScript regression suite: 60 tests passed on amd64 and arm64
- Actual amd64 and arm64 containers verified temporary login, API confinement, mandatory credential replacement, old-session revocation, and normal access through the replacement session
- An existing credentials file remained byte-for-byte unchanged across the Docker bootstrap command
- Password source text was absent from `credentials.json`; only the existing salted PBKDF2-SHA256 representation was stored
