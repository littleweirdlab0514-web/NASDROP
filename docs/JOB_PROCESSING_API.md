# Per-job processing options (0.9.17)

Included in the local 0.9.17-1 SPK build; **not included in the previously built 0.9.16-1 SPK**. Public release and NAS installation are separate steps.

Authenticated `GET /api/status` advertises `job_processing_options: true`.

## Request

`POST /api/jobs/{id}/processing` with existing Bearer authorization:

```json
{"extract": true, "password": "optional new archive password"}
```

- `extract` is a required boolean.
- An omitted, null, or empty password preserves the stored password when extraction stays enabled. A nonempty string replaces it.
- Disabling extraction removes the archive password only, preserving other secrets such as a private direct-download URL.
- HTTP 200 returns `{"job": ...}` with no password or private URL. Missing jobs return 404; invalid input/state returns 400.

## State rules

- Allowed: queued, ready, inspecting, paused, downloading, password_required.
- Rejected: waiting_processing, verifying, extracting, publishing, stopping, completed, failed, cancelled.
- Reject during shutdown, while owning the postprocessing slot, or while a paused/password-waiting job still has a registered worker.
- Updates and processing transitions share the controller lock. Ordinary updates do not automatically resume paused jobs.
- Password-waiting jobs with extraction enabled require a new or stored nonempty password and are requeued.
- Disabling extraction on a password-waiting job requires its retained artifact and checksum. Requeue verifies the artifact before publishing it without extraction; missing artifacts are rejected rather than redownloaded by this operation.
- Inspection placeholders pass current options to their child jobs. Refresh the list if a placeholder has already been replaced.

Tests cover validation, state restrictions, secret preservation/removal, save-error rollback, password retry, and retained-artifact publication. The separate secret and state writes are not a cross-file transaction in a process crash. Live NAS and extension end-to-end verification remain separate.
