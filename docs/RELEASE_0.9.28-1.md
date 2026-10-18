# NASDrop 0.9.28-1 — Persistent GoFile registration

NASDrop 0.9.28-1 accepts canonical GoFile share links into the persistent job list before contacting the provider. Adding a second GoFile link no longer waits for the first link's synchronous metadata request to finish.

The authenticated status endpoint now advertises `async_enqueue_providers` with `gigafile` and `gofile`. Capability-aware clients use the existing `POST /api/enqueue` endpoint, while older clients and servers keep the inspect/start fallback.

GoFile metadata inspection runs one job at a time even when parallel same-provider downloads are enabled. HTTP 429 and bounded network failures continue to use the existing persisted provider-wide cooldown. A normal inspection failure stays visible and resumable, releases the GoFile inspection slot, and allows the next queued link to proceed.

The transfer policy is unchanged: each GoFile file uses no more than two connections, provider tokens remain private, and folder shares are expanded into independently verified jobs only after inspection succeeds.
