# NASDrop component compatibility

NASDrop uses one server implementation across Synology and Docker. The Synology package is the reference distribution; Docker packages the same server and web files with only container-specific startup, account, storage, and runtime wiring.

## Current compatibility matrix

| Component | Current line | Server contract |
| --- | --- | --- |
| Synology package | 0.9.27-7 stable | x86_64 SPK built from the same verified server source and confirmed by the user |
| Docker image | 0.9.27-7 stable | The verified amd64/arm64 candidate was promoted by digest to the version, minor, and latest tags |
| Android app | 0.8.16+ | Uses `job_safe_delete`; older servers keep strict stopped-job deletion |
| Chrome extension | 0.5.9 release | Includes current AkiraBox and X-Share handoff plus Pixeldrain's classless no-preview Download control |

The version numbers document tested combinations. Runtime feature decisions must use `/api/status` capabilities rather than version comparisons.

NASDrop 0.9.27 adds an optional `source_password` field to the existing inspect/start flow for 1fichier. Older Android/Chrome clients remain compatible because the field is optional; they do not yet collect a 1fichier file password. Web-form use needs no new client capability. Docker real-flow and multi-architecture parity checks passed.

Revision 0.9.27-5 gives the bottom visible 1fichier job exclusive retry ownership. Following 1fichier jobs remain queued without copying its countdown and become eligible one at a time only after the current owner completes, fails, or is paused. The API shape is unchanged, so existing clients remain compatible.

Revision 0.9.27-6 classifies 1fichier's form-less daily free-download-limit page as a 24-hour persisted wait. The API remains unchanged. Four real NAS downloads completed: two before the limit, then the deferred 429,020,440-byte owner and the following 12,567,188-byte job after reset. This verifies both automatic retry and sequential ownership transfer.

Revision 0.9.27-7 fixes X-Share's first real transfer failure. From the NAS Docker network, X-Share's public API returned HTTP 403 to curl's default user agent and HTTP 200 when the explicit NASDrop user agent was supplied. The keyed transfer now supplies that same user agent and identity encoding while preserving the one-shot, pinned-address security boundary.

Revision 0.9.27-2 added `xshare` to `browser_handoff_providers`. Chrome 0.5.9 accepts the existing `{provider, url, resolved_url}` contract, validates a same-file first-party keyed endpoint, and obtains metadata without consuming the key. The transfer uses one full GET without resume or automatic replay. Signed-out, unsupported, and older companion installations leave the provider's normal download intact. The user confirmed the real X-Share NAS flow on 2026-09-30.

The 0.9.27-7 Docker `candidate`, version, `0.9`, and `latest` tags point to the verified multi-platform manifest digest `sha256:3c146e31ca803ba98a025b71e693f25bcc0264e91ea8e1e58c6996bd64a17561`. Promotion reused that digest without rebuilding it; candidate run 36655115146 and promotion run 36655501406 passed.

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

As decided by the user on 2026-09-26, shared changes are implemented and tested first in the private Docker deployment. Coordinate Chrome changes with its dedicated maintainer and verify the real provider flow there before building the Synology SPK from the same canonical source. Docker must not add a provider-specific fork. Synology still requires separate DSM launcher, permissions, packaging, and update/stop verification; Docker success alone does not close those gates. Preserve accounts, jobs, and mounted storage during test updates.

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
