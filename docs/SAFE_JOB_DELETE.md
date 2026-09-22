# Safe stop-and-delete API

Implemented in NASDrop 0.9.23-1; existing 0.9.22 packages do not advertise this capability. Live DSM verification is pending.

## Client contract

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
