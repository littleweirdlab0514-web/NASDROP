# NASDrop 0.9.23-4

NASDrop 0.9.23-4 makes mandatory credential replacement unconditional for the Docker default account.

## Docker default-account enforcement

- A missing `/config/credentials.json` still receives temporary ID `nasdrop` and password `nasdrop`.
- On every Docker start, NASDrop now also detects an existing account that verifies as exactly `nasdrop` / `nasdrop` and atomically restores `must_change_password: true`.
- Custom credentials are left unchanged.
- After the temporary login, only account/status reads, credential replacement, and logout are permitted. Download, folder, settings, and job APIs return HTTP 403 with `password_change_required`.
- The web portal opens the account form and requires a new ID and a password of 10–128 characters.
- The temporary password remains a bootstrap-only exception and cannot be saved as the replacement password.

## Downloads

- Synology DSM 7.1 or later on x86_64: `nasdrop-0.9.23-4-x86_64.spk`
- Docker: `ghcr.io/littleweirdlab0514-web/nasdrop:0.9.23-4`

The Docker image supports `linux/amd64` and `linux/arm64`. See the [Docker installation guide](DOCKER_INSTALL.md) or the [Korean Docker installation guide](DOCKER_INSTALL.ko.md).

## Verification

- Legacy default credentials are upgraded without changing their PBKDF2 salt or password hash.
- Existing sessions are revoked when the mandatory-change flag is restored.
- Non-default credentials remain byte-for-byte unchanged.
- Python regression suite: 189 tests passed on amd64 and arm64; one platform-dependent test skipped.
- JavaScript regression suite: 60 tests passed on amd64 and arm64.
- An actual amd64 legacy default-account container restored the flag, preserved its PBKDF2 salt/hash, accepted `nasdrop` / `nasdrop`, and returned HTTP 403 for jobs.
