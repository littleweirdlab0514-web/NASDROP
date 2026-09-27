# Safe stop-and-delete API

Implemented in NASDrop 0.9.23-1; existing 0.9.22 packages do not advertise this capability. Live DSM verification is pending.

## Client contract

### Mandatory product behavior (2026-09-26)

On a compatible server, clicking Delete is sufficient even while a job is active. The user must not be required to pause it first. Internally the operation is stop -> confirm worker/process shutdown -> automatically clean up the selected job. This is a permanent Synology/Docker UI and API contract, not an optional server-only feature.

- Enable Delete for eligible active selections when `job_safe_delete` is advertised and send `stop_active: true`. Disable repeated deletion only while deletion is already pending.
- Show pending shutdown until polling confirms the record is gone. Never report completed deletion merely because the API accepted the request.
- Preserve published files and extracted output; remove only the job record, secrets, and exact temporary workspace after ownership ends.
- Test button eligibility and request payload, plus active-transfer stop/cleanup, duplicate actions, cleanup failure, and published-file preservation. Verify the real flow in Docker first, then DSM-specific lifecycle behavior from the same source.
- The legacy fallback below applies only when the server does not advertise the capability; it must not become the normal behavior of current NASDrop clients.

- Authenticated `GET /api/status` advertises `job_safe_delete: true`.
- Opt in with `POST /api/jobs/delete` and `{"ids":["123456abcdef"],"stop_active":true}`.
- HTTP 200: `{"ok":true,"deleted":1,"pending":[]}` when cleanup finishes immediately.
- HTTP 202: `{"ok":true,"deleted":0,"pending":["123456abcdef"]}` when worker shutdown is pending. A mixed batch may put every selected job into pending cleanup.
- Pending jobs expose `status: "stopping"` and `delete_requested: true`. Disable resume, processing changes, password submission and repeat deletion controls. Continue polling `/api/jobs`; absence confirms completion, not HTTP 202 alone.
- Cleanup failure retains the record with `delete_requested: false`, `status: "failed"` and a safe error. The user may retry deletion after resolving the failure.
- Omitted `stop_active` preserves the old strict endpoint: active jobs are rejected. Non-boolean values are rejected.
- If the capability is absent, do not send active deletion requests. A legacy client may pause supported phases, wait until the worker is fully stopped, then delete. Refuse extraction/publication deletion on old servers.

## Safety and deletion scope

Only the selected job record, secrets and exact private `.nasdrop-tmp/<job-id>` workspace are deleted. Published files and extracted output folders are retained. Symlink workspaces are rejected. No broad target-directory cleanup is performed.

Worker ownership remains until download, inspection and processing return. ZIP/TAR copying and 7-Zip subprocesses observe cancellation. Final publication checks cancellation under the same lock used to accept deletion; output already published before that boundary is preserved. If process termination cannot be confirmed, preserve ownership and files rather than racing the writer.

Inspection can take until its current network request returns. The API does not claim immediate completion or forcefully kill Python threads. After a service restart, pending deletion is converted to a paused job requiring a fresh explicit deletion request; it is never replayed automatically.

Regression coverage: `tests/test_safe_delete.py`, existing workspace-delete tests and `tests/test_transfer_reliability.py`. Local tests do not establish live DSM lifecycle behavior; that verification remains pending.
