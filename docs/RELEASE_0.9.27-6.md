# NASDrop 0.9.27-6 stable release

NASDrop 0.9.27-6 adds verified sequential 1fichier downloading and the server side of the X-Share Chrome handoff while preserving existing accounts, jobs, and download folders.

## Highlights

- Register official 1fichier shares directly in NASDrop, including optional file passwords.
- Respect provider wait, guest-slot, and daily free-use limits with a persisted local countdown.
- Retry only the bottom visible 1fichier job; later jobs wait without making independent provider requests.
- Resume the next 1fichier job only after the current queue owner completes, fails, or is paused.
- Keep Docker account bootstrap from starting a temporary download dispatcher.
- Stop and safely delete active jobs from the web dashboard with one Delete action.
- Accept authenticated X-Share handoff from the separate Chrome 0.5.7 companion after the user completes provider verification and clicks Download.

## Verified results

- Linux Python regression suite: 226 passed, 1 skipped.
- Web and Chrome JavaScript suite: 73 passed.
- Docker packaging and 1fichier contract follow-up: 25 passed.
- Docker amd64 and arm64 builds and runtime smoke tests passed.
- Four real sequential 1fichier downloads completed on the NAS: 90,999,059 bytes; 30,303,152 bytes; 429,020,440 bytes after the daily-limit retry; then 12,567,188 bytes.
- Existing Docker credentials remained unchanged through the upgrade.

## Assets

- Synology DSM 7.1+ x86_64: `nasdrop-0.9.27-6-x86_64.spk`
- SHA-256: `0737802AF1C377B87AC8D0CDFC134DD7AB55C42E24BF2B2937A8F6CD27C8472D`
- Docker: `ghcr.io/littleweirdlab0514-web/nasdrop:0.9.27-6`

The native SPK supports x86_64 Synology systems. The Docker image supports `linux/amd64` and `linux/arm64`.
