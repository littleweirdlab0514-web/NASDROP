# NASDrop 0.9.25-1 test build

This Synology test package adds protected GigaFile download-key handling. It is paired with Chrome companion 0.5.5.

## Changes

- GigaFile download keys are separate from archive extraction passwords.
- The NAS web portal can submit a key when a job is created.
- A protected job created without a key pauses with `download_key_required`; the key can be entered on the job to resolve and resume it.
- Rejected keys do not trigger automatic retries.
- Keys are not placed in URLs, public job/status responses, service logs, or Chrome storage. The server uses restricted per-job secret storage only while the key is needed.
- Chrome companion 0.5.5 recognizes only the official GigaFile key field and official download action after a user click, with normal browser-download fallback on an older server.

## Verification status

- Automated Python and Chrome regression suites are release gates for this build.
- A real protected GigaFile page has been confirmed to require a key without exposing it.
- A complete correct-key transfer, wrong-key recovery, restart, and DSM package-update flow still require target-NAS testing.
- Docker carries the same source version but remains unpublished until Synology verification and Docker parity smoke tests pass.
