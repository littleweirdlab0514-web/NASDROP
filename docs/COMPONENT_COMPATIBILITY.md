# NASDrop component compatibility

NASDrop uses one server implementation across Synology and Docker. The Synology package is the reference distribution; Docker packages the same server and web files with only container-specific startup, account, storage, and runtime wiring.

## Current compatibility matrix

| Component | Current line | Server contract |
| --- | --- | --- |
| Synology package | 0.9.26-6 credential-bootstrap test build | Canonical server; DSM icon opens the ordinary NASDrop login; fresh installs require replacement of both temporary credentials |
| Docker image | 0.9.26-6 pending | Same credential API and web UI; build and smoke-test after the Synology flow passes |
| Android app | 0.8.16+ | Uses `job_safe_delete`; older servers keep strict stopped-job deletion |
| Chrome extension | 0.5.5 | Adds protected GigaFile key handoff and user-assisted Send.now handoff; keeps strict deletion behavior |

The version numbers document tested combinations. Runtime feature decisions must use `/api/status` capabilities rather than version comparisons.

## Ownership model

- `backend.py`, `transfer_parts.py`, `gofile_wt.mjs`, and `synology/web` define canonical server behavior.
- Synology owns DSM packaging, launcher integration, permissions, and update lifecycle.
- Docker owns the entrypoint, UID/GID mapping, mounted storage, health check, and multi-architecture runtime. It must not fork API or provider behavior.
- Docker may carry a container-specific runtime binary only when its architecture and checksum are pinned and its required archive formats are verified during the image build.
- Android and Chrome own presentation and platform integration. They consume the same authenticated API and degrade safely when a capability is absent.

## Capability rules

1. Add optional behavior to `/api/status` before a client depends on it.
2. Clients treat a missing, false, or malformed capability as unsupported.
3. Clients must not infer support from a semantic-version comparison.
4. Server changes remain backward compatible unless a coordinated major contract change is documented.
5. Signed provider URLs, passwords, cookies, and authorization headers are never exposed through capability data or logs.

Current coordinated capabilities include:

- `password_change_required`: the Docker `nasdrop` / `nasdrop` bootstrap account may authenticate only to read a minimal version/change-required status, read account data, replace its credentials, or log out; downloads, folders, settings, inspection, and job operations return HTTP 403 with this code until both credentials are replaced. A legacy untouched default account keeps the same credentials and has the mandatory-change flag restored.

- `job_safe_delete`: permits `POST /api/jobs/delete` with `stop_active: true`; legacy deletion remains strict.
- `job_processing_options`: permits per-job extraction and password updates.
- `browser_handoff_providers`: lists the exact browser-assisted providers accepted by the server.
- `gigafile_download_key`: permits a client to submit a GigaFile download key when creating a job and to resume a paused `download_key_required` job through the dedicated key endpoint.

Provider changes shared by the server and Chrome must pass both regression suites and a real provider flow before Docker is synchronized and smoke-tested from the same canonical source. Docker must not add a provider-specific implementation of its own.

Creating a normal `v*` server tag builds, smoke-tests, and publishes only an immutable `candidate-<package-version>` Docker manifest. It must not move the version, minor, or `latest` tags. After the user confirms the Synology package on real hardware and the Docker maintainer verifies parity, run the separate `Docker promote candidate` workflow manually. Promotion attaches the version, minor, and `latest` tags to the already-tested candidate digest without rebuilding it.

An explicit async-enqueue capability must be added before Android removes its remaining legacy version check. Until then, the client must retain the normal inspect/start fallback.

## Release gate

For every server release:

1. Update the package, backend, Dockerfile, and Compose versions together.
2. Run the full Python and JavaScript regression suites.
3. Build the SPK and inspect its packaged files.
4. Build Docker for `linux/amd64` and `linux/arm64`.
5. Compare hashes of the canonical core and web files with the files embedded in the Docker smoke image.
6. Run Docker authentication, storage, provider, archive, safe-delete, restart, and shutdown smoke tests.
7. Run Android and Chrome contract tests against present and absent capabilities.
8. Update this matrix and publish English release notes describing client requirements and fallbacks.

Do not publish a Docker image from manually copied or modified server sources. The release workflow must build from the same Git commit as the Synology package.
