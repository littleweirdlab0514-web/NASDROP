# NASDrop

## Android closed-test volunteers wanted

Already using NASDrop? LittleWeirdLab is recruiting existing NASDrop users to help test the **NASDrop Android companion app** before its public Google Play release.

- **Who can join:** Android users with their own working NASDrop Server and a Google Play account. Connect the app to your own server using your NASDrop ID and password; you do not need access to the maintainer's NAS.
- **What to test:** Server sign-in, sharing supported links from a browser, adding downloads, destination-folder selection, progress display, and UI/language issues. Please use files you own or are authorized to download, and respect provider rate limits.
- **Participation:** Please plan to stay opted in for at least **14 consecutive days**, use the app during that time, and share honest feedback. We are aiming for at least **15 volunteers** to allow for dropouts. A positive review is not required.
- **Cost:** The app is free with ads and offers an optional one-time ad-removal purchase. **No purchase is required to participate.**

**To volunteer, email [littleweirdlab0514@gmail.com](mailto:littleweirdlab0514@gmail.com)** with the subject **NASDrop Android Test**. Include the Google account email you will use in Google Play, your Android version, and your NASDrop Server version. We will use the supplied account email to add you to the tester list and send participation instructions and the closed-test link when the release is available. This is a recruitment announcement, not an immediate public-download link.

**Do not post your Google account email, NAS address, passwords, private download links, or unredacted screenshots in public issues or comments.** Feedback can be sent by email; only share sanitized technical details publicly. This public repository remains the NASDrop Server project; the Android app source repository remains private.

---

[![DSM 7.1 and 7.2 supported](https://img.shields.io/badge/DSM-7.1%20%7C%207.2%20supported-brightgreen)](#install-a-prebuilt-release)

> [!TIP]
> **DSM 7.1 support is now available.** NASDrop has been verified on real DSM 7.1 and DSM 7.2 hardware. The current SPK supports Intel/AMD 64-bit (`x86_64`) Synology NAS models running DSM 7.1 or later.

NASDrop is a self-hosted personal download portal for Synology DSM and Docker hosts. Paste a supported GigaFile, GoFile, Pixeldrain, or Buzzheavier signed direct link, or use the Chrome companion for browser-assisted providers, and the storage server downloads the file directly.

**[Download the latest SPK release](https://github.com/littleweirdlab0514-web/NASDROP/releases/latest)**

## NASDrop for Chrome companion extension

Send supported download buttons directly to your own NASDrop server, manage the queue, and choose automatic extraction without repeatedly opening the NAS web portal. The extension is a companion client, not a standalone downloader or a replacement for the server.

- **Chrome extension 0.5.5 ZIP is compatible with the NASDrop Server 0.9.26-5 DSM launcher test build.**
- **[Installation, updates, permissions and usage](chrome-extension/README.md)**
- **[Step-by-step installation guide in Korean](chrome-extension/INSTALL.ko.md)**
- **Compatible NASDrop Server 0.9.26-5 includes the protected GigaFile handoff and the security hardening described below.**

Extract the ZIP into a permanent folder, open `chrome://extensions`, enable **Developer mode**, and choose **Load unpacked** for the folder containing `manifest.json`. Connect using your own NASDrop address and ID/password, with a writable default download folder configured on the server. For updates, replace the unpacked files, click **Reload**, and refresh open provider pages. ZIP installations do not update automatically.

The extension supports English, Korean, Japanese and Chinese, with a manual language selector and English fallback. Refresh/automatic extraction, per-job extraction/password settings, pause/resume and history deletion are available. Removing completed history does not remove the downloaded output.

**This is a GitHub-distributed preview, not a Chrome Web Store listing.** AkiraBox/VikingFile browser handoff requires Server **0.9.19 or later** and a fresh official download link from the provider page. Send.now support is user-assisted: complete verification and Continue normally, then click the actual `Download [size]` button on the following page so Chrome can hand that resulting download to NASDrop. Browser cookies are not copied to the NAS, and CAPTCHA/provider restrictions are not bypassed. The server and extension are installed and versioned separately.

> [!IMPORTANT]
> NASDrop is an independent, unofficial community project. It is not listed in Synology's official Package Center catalog and must be installed manually. It is not affiliated with, endorsed by, or sponsored by Synology or any supported download service.

> [!WARNING]
> **Third-party service changes may break NASDrop.** NASDrop depends on external download websites and APIs. Providers may change their policies, terms, authentication, URL formats, rate limits, APIs, or download mechanisms without notice. Such changes may cause some or all NASDrop download functions to stop working temporarily or permanently. Continued compatibility and uninterrupted availability are not guaranteed.

## What's new in 0.9.26 (security test build)

- DSM launcher test revision `0.9.26-5` tries the two DSM authenticator locations, then a loopback DSM HTTP request when direct execution returns no output. Loopback requests disable proxies and redirects so DSM cookies cannot be forwarded elsewhere. A DSM icon launch still requires a verified DSM administrator session; this behavior still requires a real-NAS test.
- Replaced the static DSM launcher bearer token with a DSM-authenticated administrator CGI and an HMAC-signed, 30-second, one-use handoff. Static launcher files no longer contain credentials, and an existing NASDrop account can no longer be replaced from a DSM launcher session without its current NASDrop password.
- Hardened GoFile's remote helper: injected values are created inside the VM context, string/Wasm code generation stays disabled, the helper process runs with Node's permission model and read access only to its own entry file, and navigator-constructor escape coverage is included.
- Send.now inspection pins each connection to the public IP set that was validated, and the final curl transfer uses a validated `resolve` entry so DNS cannot be re-resolved to a private address between validation and use.
- Docker keeps the documented one-time `nasdrop` / `nasdrop` bootstrap login. It exposes only minimal account/status operations until both credentials are replaced, and restores the mandatory-change flag if a legacy untouched default account is found.

## What's new in 0.9.25 (test build)

- Added a separate GigaFile download-key field. It is not confused with an archive extraction password. The NAS web portal can send the key when creating a job.
- If a protected GigaFile link was added without a key, the job pauses with a clear `download_key_required` state. Enter the key on that job to resolve and resume it without discarding already verified work. A rejected key is not retried automatically.
- Download keys are excluded from URLs, public job/status responses, logs, and Chrome storage. They are kept only in the job's restricted secret storage while needed and removed after the protected file is resolved.
- Chrome companion 0.5.5 reads only GigaFile's official four-digit key field and official download control after the user's click. It falls back to the site's normal download on older servers. Detection of a real protected link has been verified; a complete key-authenticated NAS transfer remains a target-NAS test gate.

## What's new in 0.9.24 (test build)

- Added user-assisted Send.now handoff with Chrome companion 0.5.4. Verification and Continue remain normal site actions; the extension redirects only the Chrome download created by the later final Download button and does not automate or bypass CAPTCHA/Cloudflare. Version 0.5.4 also removes the incorrect assumption that Chrome download events include a tab ID.
- The server accepts changing public HTTPS delivery hosts without a brittle single-CDN allowlist, while rejecting local/private destinations, credentials, fragments, unusual ports, bare share pages, HTML responses, and non-resumable files.
- Send.now jobs use one connection and keep issued URLs private. Synology and Chrome regression suites pass; real provider/NAS verification and Docker synchronization remain release gates.

## What's new in 0.9.23

- **Delete now safely stops a running job and automatically removes it afterward when using a compatible client.** You no longer need to pause the job and then press Delete again. The server waits for the worker and file writes to finish before deleting the job's private temporary files and record. Published files and extracted output folders are preserved.
- Pending deletion locks conflicting actions. Cleanup failures preserve the record, and service restarts never replay deletion automatically.
- Requires a client that supports safe stop-and-delete (Android 0.8.16 or later). Updating the SPK alone does not change the Delete button in older clients, the current web dashboard or Chrome companion; they retain the previous strict deletion behavior. Live DSM and updated Android integration verification remains pending.

## What's new in 0.9.22

- Removed temporary diagnostic labels from user-facing errors. Clear explanations remain; signed URLs, credentials and remote error contents are never shown.
- VikingFile also accepts signed regional file servers on a single subdomain of `vikingfile.com` (such as `ko.vikingfile.com`), using the provider's `expires`/`md5` URL fields. The observed 6.27 GB sample returned HTTP 200 with byte-range support; full transfer on this newly supported route still requires installation and testing.
- Includes the VikingFile pinned-account bucket compatibility fix and the unique-byte progress accounting fix from 0.9.21, plus bounded AkiraBox transient-transfer recovery from 0.9.20.
- The user confirmed the previously failing VikingFile link works after installing 0.9.21. AkiraBox completed a real NAS download; forced-disconnection recovery has been tested locally, not on the live provider.
- Install the SPK manually. After updating, open Settings and select your download folder again. Browser-assisted downloads still require the user to complete any provider verification and click Download. No Chrome extension update is bundled with this server release.

## What's new in 0.9.21 (local test build)

- Fixed progress double-counting while a temporary fragment is copied into a committed part. Progress uses unique byte coverage and excludes response headers and rejected response bodies.
- VikingFile now accepts different bucket names within its observed, pinned R2 account instead of requiring one bucket hostname. Other R2 accounts, nested/lookalike domains, internal addresses and non-HTTPS destinations remain blocked. Signature expiry, redirect bounds and range validation are unchanged.
- Browser-assisted Viking samples of 356 MB and 1.26 GB completed on the user's NAS with 0.9.20. This does not establish large-file compatibility: the newly accepted bucket route still requires testing after installing 0.9.21. User verification and a real Download click remain part of the supported browser flow.

## What's new in 0.9.20 (local test build)

- AkiraBox can retry a validated partial transfer up to three times, after 10, 20 and 30 seconds, for selected transient curl transport errors. Every resumed fragment is range-validated before being committed. HTTP rejections, redirects, invalid ranges and local write failures are not automatically retried.
- Browser-handoff failures now distinguish fixed, secret-free inspection reasons (such as an unapproved redirect host or an invalid range response) and numeric transfer diagnostics. A generic transfer failure is no longer presented as proof that a link expired.
- Provider host allowlists, redirect restrictions, single-connection browser transfers and GoFile concurrency remain unchanged. No CAPTCHA or provider access restrictions are bypassed.
- Local regression tests do not establish real-provider compatibility. Full NAS download, stop/resume and DSM update verification remain pending user installation. This build has not been published as a GitHub release.

## What's new in 0.9.19 (preview)

- Fixed browser handoff inspection for observed AkiraBox and VikingFile redirect flows. Only explicitly verified provider file hosts are allowed; unrelated R2 tenants, other hosts, credentials, HTTP and unusual ports remain blocked.
- GET-signed links that reject HEAD with HTTP 403 can now be inspected with a bounded range request. Missing HEAD range metadata also triggers a range check. Inspection reads no file body and rejects servers that ignore the range.
- Jobs store the validated final transfer URL privately, including for restart/resume. File transfers still refuse unexpected redirects and use one connection per job.
- Chrome extension 0.4.2 remains compatible; no extension update is required. Obtain a fresh official link and register a new job when testing a previously failed or expired link.
- Local tests reproduce both provider response flows. Full downloads on the user's NAS remain unverified.

## What's new in 0.9.18 (local test build)

- Experimental Chrome browser handoff for AkiraBox and VikingFile. Open the original share page, wait for its official download button, and use the compatible NASDrop extension to send that link to the NAS. Pasting a share URL alone is not supported.
- The NAS inspects the direct link without browser cookies and downloads with one connection. Expired, restricted, redirected, or non-resumable links are rejected with a new-link instruction. This does not bypass CAPTCHA, provider restrictions, or IP-bound tokens.
- Signed URLs are kept out of public job metadata. Failed temporary-file cleanup now retains the job record; deleting completed history never deletes published output.
- Local regression tests do not prove provider/NAS compatibility. Real NAS downloads, including whether a provider requires additional normal browser activation, still need user testing. See [the handoff test guide](docs/BROWSER_HANDOFF.md).

## What's new in 0.9.17

- Added authenticated per-job extraction options for compatible clients. Check `job_processing_options` in `/api/status` before using the processing endpoint.
- Options can change before disk processing starts, including during downloading. Paused jobs remain paused. Verification, extraction, publication, stopping, and completed states reject changes.
- Password-waiting jobs can retry extraction or publish the retained original archive after integrity verification. Disabling extraction removes only the archive password.
- See [the processing API contract](docs/JOB_PROCESSING_API.md). Live NAS/extension verification remains pending.

## What's new in 0.9.16

- The Synology web form now saves GigaFile links immediately as **Checking file information**, then resolves filenames in the background. Multi-file pages become individual download jobs after inspection.
- Pending links keep their destination and extraction options. Inspection errors can be retried; paused inspections cannot launch downloads. After a restart, unfinished inspections are retained as resumable paused jobs.
- Inspection uses the existing scheduler limits, with at most one link inspection at a time. Filename verification remains intact. This changes perceived submission latency, not provider response speed.
- Existing `/api/inspect` clients (including previously installed Android apps and browser extensions) retain their original behavior until updated to use `/api/enqueue` for GigaFile.

## What's new in 0.9.15

- Fixed archive password delivery: remove the bare `-p` option and let 7-Zip read the password from stdin. Passwords remain absent from command-line arguments.
- After updating, re-enter the password on an existing password-waiting job. Actual NAS verification is still required.

## What's new in 0.9.14

### GoFile connection limit

GoFile now uses up to **2 segments per file** in segmented mode; other providers retain their existing layout. Single-connection mode remains single. Existing 8-segment GoFile downloads retain their saved ranges to protect resume data, but transfer only two segments at a time. This is a per-file limit: enabling simultaneous GoFile jobs increases the total connections. Reducing connections does not immediately lift an existing provider rate limit; the shared HTTP 429 cooldown remains in effect.

See the [GoFile request policy](docs/GOFILE_REQUEST_POLICY.md) before changing provider request handling.

## What's new in 0.9.13

- Long multilingual filenames are limited by UTF-8 byte length instead of character count. Names exceeding 240 bytes are shortened with a stable hash while preserving extensions, including `.tar.gz`.
- Temporary segments and assembly files now use only the short job ID, never the original title. Existing named segments are migrated on resume without silently overwriting conflicting files.
- Destination collision names also respect the byte limit. For jobs failed with `File name too long`, install the update and resume the failed job; no NAS files are deleted by the update itself.

## What's new in 0.9.12

- Interrupted range responses are validated and checkpointed before resuming. Each job keeps its transfer mode, and tiny files no longer request empty ranges.
- Pause now shows **Stopping** until the worker exits. Resume/delete cannot race the previous worker, and stopped verification cannot publish a completed download.
- Package shutdown stops transfer process groups and interrupts disk processing before saving paused jobs. DSM hardware update/restart verification is still required; power loss and forced termination cannot guarantee a completed checkpoint.
- GoFile file-server HTTP 429 responses now delay queued and running GoFile transfers using a shared cooldown, including `Retry-After`. Other providers remain eligible subject to the normal disk/concurrency limits. Failed transfer requests no longer make eight immediate curl retries; resume retries preserved ranges, while GoFile cooldown retries are scheduled automatically.
- Download-response filename headers are captured from the actual transfer when HEAD discovery fails. Raw cookies and response headers are not kept after processing.
- Password-entry forms and expanded verification details survive list refreshes. An expired session returns to login; malformed non-object JSON requests receive an error.
- Opening DSM through a private address uses the NASDrop HTTP listener. Public domains still preserve the HTTP/HTTPS protocol used to open DSM; HTTP is unencrypted, so use HTTPS through a reverse proxy for untrusted networks.

> [!IMPORTANT]
> Old unfinished `.more` fragments without a validated response range cannot safely be reused and may be downloaded again. Completed valid segments are retained. A locally calculated SHA-256 alone does not prove equality with the provider's original file; comparison requires a provider-supplied checksum.

## What's new in 0.9.11

- Distributed sign-in failures now trigger only a five-second global pause after 30 failures in 60 seconds; the existing per-client five-failure/15-minute protection remains unchanged.
- Settings now include an explicit DSM reverse-proxy mode. It trusts the rightmost forwarded client address only from a loopback proxy and applies changes without restarting NASDrop.
- When a loopback proxy sends forwarded headers while the mode is disabled, NASDrop warns in both Settings and the service log that clients share one login-throttle bucket.
- GigaFile pages containing multiple files now queue each original file instead of the provider-generated combined ZIP, and resolve each file's real response name before it enters the queue whenever possible.
- GigaFile markup variations and malformed size metadata now fail safely, while large batches are staggered without an artificial three-file or combined-size limit.
- Provider page and header probes now have bounded timeouts, stalled transfers stop cleanly and can be resumed, and redirects cannot escape to another host or protocol.
- Web responses now include browser security headers, and the temporary inspection cache is bounded to prevent unrestrained memory growth.

## What's new in 0.9.10

- Pixeldrain metadata requests now identify the active NASDrop package version instead of the obsolete `NAS Download Portal/0.4.2` value.
- Invalid ID and password rules and login-throttle wait times now have dedicated English, Korean, Japanese, and Chinese error messages.

## What's new in 0.9.9

- NASDrop API and saved job failures now carry stable error categories, so English, Japanese, and Chinese users see localized errors instead of Korean-only backend text.
- DSM launcher account-reset authority is limited to the first five minutes of its one-hour automatic-login session, and the in-memory session registry is capped at 256 entries.
- Provider downloads now refuse redirects from HTTPS to plain HTTP. 7-Zip archive passwords are supplied through standard input instead of appearing in the process command line.

## What's new in 0.9.8

- Public hostnames opened over HTTP now show a clear warning before login and inside the dashboard while preserving certificate-free HTTP access.

## What's new in 0.9.7

- DSM icon handoff values are now single-use: the browser exchanges one for a short-lived launcher session and the server rotates the handoff immediately.
- Login handling now rejects malformed request lengths, safely handles non-ASCII login input, bounds stale failure records, and ignores forwarded client addresses unless a local reverse proxy is explicitly trusted.
- API routes now behave consistently when a query string is present, job state files use restricted permissions, extraction has a six-hour safety timeout, and concurrent settings writes are serialized.

## What's new in 0.9.6

- Restores Korean CP949, Japanese Shift-JIS, and Chinese GB18030 filenames when legacy ZIP archives omit the UTF-8 filename flag, while preserving UTF-8 names and archive path-safety checks.

## What's new in 0.9.5

- Buzzheavier signed direct links copied with **Copy download link** are now accepted by the web portal and Android client.
- Buzzheavier link tokens are removed from the public job source and stored separately with restricted permissions so they do not appear in the job list or `jobs.json`.
- Expired Buzzheavier links now produce a provider-specific message asking for a newly copied link.
- The settings screen now combines parallel-download and per-file transfer controls into one compact half-width card with a single warning and save action.
- The DSM launcher now preserves the protocol used to open DSM, so an HTTP domain opens NASDrop over HTTP instead of forcing HTTPS.

## What's new in 0.9.3

- Downloads, segmented-file assembly, verification, and extraction now run inside a hidden `.nasdrop-tmp` workspace. Only the completed file or extracted folder is moved to the selected destination.
- ZIP (including AES-encrypted ZIP), 7z, RAR, and TAR-family archives can be extracted automatically. Extraction can be selected for each job, and an archive password can be entered when adding a job or after NASDrop detects that one is required.
- Disk protection can pause new downloads while verification or extraction is using the disk heavily.
- GigaFile filenames are resolved from the real download metadata so the queue can show the final filename before completion whenever the provider supplies it.
- The DSM launcher is validated during packaging so its desktop label remains `NASDrop`.

> [!NOTE]
> **ALZip EGG archives are not supported for extraction.** If an `.egg` file is downloaded, NASDrop saves it in its original `.egg` form even when extraction was requested. Extract it later with a separate EGG-compatible application.

## Features

- Validates GigaFile, GoFile, Pixeldrain, and Buzzheavier signed direct links and displays file names and sizes
- Queues multiple download jobs
- Supports a per-job destination folder and a configurable default folder
- Offers either an 8-part verified download or a lower-disk-I/O single-connection download
- Keeps partial files and assembly work inside a hidden `.nasdrop-tmp` workspace, then publishes only complete results
- Can extract ZIP (including AES), 7z, RAR, and TAR-family archives with an optional per-job password
- Pauses new downloads during verification and extraction when disk protection is enabled
- Displays progress, failure details, and SHA-256 results
- Supports pausing, resuming, and deleting jobs, plus clearing completed jobs in bulk
- Protects direct browser and client-app access with an ID, hashed password, login throttling, and time-limited sessions
- Detects GoFile rate limits and uses a persistent cooldown circuit breaker
- Runs as either a native Synology SPK or a multi-platform Docker container on amd64 and arm64 hosts

### Download method option

The default **8-part download + verification** mode downloads eight byte ranges in parallel, combines them locally, checks the final size, tests ZIP archives, and calculates SHA-256. It provides stronger integrity checking but can require substantial disk I/O after a large download finishes.

The optional **Single connection** mode writes one resumable temporary file without splitting or merging it. The shared post-processing pipeline still checks the final size and SHA-256 and performs archive validation when applicable. This lowers connection pressure while preserving integrity checks. The selected mode applies to new and resumed jobs.

## Repository layout

- `backend.py`: Authentication, link inspection, and the storage-local download queue
- `gofile_wt.mjs`: Helper for generating GoFile web tokens
- `synology/`: DSM SPK metadata, web UI, lifecycle scripts, and build tools
- `chrome-extension/`: Manifest V3 Chrome extension for sending browser links to NASDrop
- `Dockerfile`, `compose.yaml`, and `docker/`: Portable container image, Compose example, and startup/account utilities
- `config.example.json`: Example package configuration
- `runtime/`: Hashed account credentials, sessions, configuration, logs, and job state; excluded from Git
- `tests/`: Python and Node.js regression tests for providers, packaging, authentication, extraction, and the rendered UI
- `docs/`: Release notes, the consolidated [provider/security policy](docs/PROVIDER_AND_SECURITY_POLICY.md), and focused regression guides
- `assets/`: Documentation screenshots and translated setup guides
- `.github/`: Release and container publishing workflows

## Install a prebuilt release

1. Open the [latest GitHub release](https://github.com/littleweirdlab0514-web/NASDROP/releases/latest) and download the `x86_64.spk` asset.
2. In DSM, open **Package Center > Manual Install**.
3. Select the downloaded SPK and review the manual-install warning and license.
4. Complete the installation, then grant the NASDrop package account access to a destination folder as described below.

The package supports DSM 7.1 or later on Intel/AMD 64-bit (`x86_64`) Synology NAS models. DSM 7.1 and DSM 7.2 have both been verified on real hardware. ARM models are not supported yet. Because this is not an official Package Center listing, GitHub releases are the only supported distribution channel and updates are installed manually.

NASDrop does not select a default download folder during installation. A download cannot start until a writable destination is selected either as the default destination or for that individual job.

> [!IMPORTANT]
> **After every update, open NASDrop Settings and select the default download folder again before adding new jobs.** Even if the previous path still appears, reselect it once so NASDrop can confirm that the package account still has write permission.

When upgrading from an older release, the former automatically assigned `/volume2/downloads` value is cleared. A different destination that was explicitly selected by the administrator may remain visible, but it should still be selected again after the update as described above.

## Run with Docker

The Docker image is suitable for Synology Container Manager, ordinary Linux servers, home servers, and Docker Desktop. Published images target both `linux/amd64` and `linux/arm64`.

For complete instructions for Synology Container Manager, Linux, Windows, macOS, permissions, updates, backups, offline images, and troubleshooting, see the **[Docker installation guide](docs/DOCKER_INSTALL.md)**. A **[Korean guide](docs/DOCKER_INSTALL.ko.md)** is also available.

### Docker Compose quick start

1. Download `docker/compose.release.yaml` and save it as `compose.yaml`. Copy `docker/compose.env.example` beside it as `.env` when you want to override the defaults. The root `compose.yaml` includes a local `build:` block for source development and is not the standalone installation file.
2. If you created `.env`, set `NASDROP_CONFIG_DIR` and `NASDROP_DOWNLOAD_DIR` to persistent host folders.
3. On Linux or Synology, set `PUID` and `PGID` to the numeric user and group that can write to the download folder. You can find them with `id your-user`.
4. Start NASDrop and open `http://SERVER-IP:8791`:

   ```sh
   docker compose up -d
   ```

5. On a new `/config` volume, sign in with the temporary ID `nasdrop` and password `nasdrop`. The web interface permits only minimal account/status reads, changing the ID/password, or signing out until you save a new password of 10–128 characters. The short bootstrap password cannot be reused as the replacement. Existing custom credentials are preserved, and a legacy untouched `nasdrop` / `nasdrop` account has its mandatory-change flag restored without changing the credentials.
6. Docker already defaults to `/downloads`. After changing the login, opening **Settings** and selecting `/downloads` once is recommended to verify write access.

The default Compose configuration persists application state in `./nasdrop-config`, mounts `./downloads` as `/downloads`, and stores partial files in `/downloads/.nasdrop-tmp`. Recreating or updating the container does not remove those host folders.

To reset the login later, run the account command against the running container and restart it:

```sh
docker compose exec nasdrop nasdrop-account set owner
docker compose restart nasdrop
```

### Additional storage folders

Containers can only browse host folders explicitly mounted into them. To expose more destinations, add each bind mount and list every container path in `NAS_PORTAL_STORAGE_ROOTS`:

```yaml
services:
  nasdrop:
    environment:
      NAS_PORTAL_NAS_TARGET: /downloads
      NAS_PORTAL_STORAGE_ROOTS: /downloads,/media,/archive
    volumes:
      - /srv/downloads:/downloads
      - /srv/media:/media
      - /mnt/archive:/archive
```

NASDrop never recursively changes permissions on mounted download folders. If the container reports that a folder is not writable, adjust the host folder for the configured `PUID:PGID`; do not run the service as a privileged container. Only `/config` is automatically assigned to that numeric account.

### Docker update and HTTPS

Update without deleting persistent data:

```sh
docker compose pull
docker compose up -d
```

After an update, open **Settings** and select the default download folder again. For access outside the local network, place NASDrop behind an HTTPS reverse proxy and do not expose plain HTTP port `8791` directly to the internet.

## Opening NASDrop and setting up client login

- Sign in to DSM with an administrator account, then launch NASDrop from the DSM desktop or Package Center icon. The icon creates a 30-second, one-use authenticated handoff without placing credentials in a static launcher file.
- After installing or updating, use that DSM icon launch to create the first NASDrop ID and password under **Settings > Client connection**. If an account already exists, changing it still requires the current NASDrop password; DSM launch does not bypass that check.
- Opening the service address directly, using another browser, or connecting a client app requires that ID and password.
- If the ID or password is forgotten, it cannot be displayed or reset through the DSM launcher in this security build. Recovery requires a separate administrator-controlled procedure; do not weaken the current-password requirement as a shortcut.
- Passwords are stored only as salted PBKDF2-SHA256 hashes. Successful logins receive a time-limited session token; changing the account credentials revokes existing sessions.
- Five consecutive failed login attempts from the same client IP trigger a 15-minute login block.

The DSM launcher CGI validates the current DSM administrator session and creates an HMAC-signed handoff that expires after 30 seconds and is accepted only once. The web UI removes it from the address immediately after exchange. Static launcher files contain no reusable API credential.

## Chrome extension

The optional Manifest V3 extension in `chrome-extension/` automatically connects recognized download controls on supported provider pages to NASDrop. Sign in once, then click the site's download button. Buzzheavier's **Download File** and **Copy download link** controls both resolve the signed link and send it to NASDrop. On Send.now, finish verification and Continue normally, then click the actual **Download [size]** button on the next page; only that later button arms the same-tab Chrome-download handoff. Reload provider pages after installing or updating the extension. The popup and context menu remain available as secondary entry points.

For local installation, open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select the `chrome-extension` directory. Chrome requests access to supported provider sites for button detection and to the configured NASDrop host for API calls. The extension saves the session token but never the password. See [`chrome-extension/README.md`](chrome-extension/README.md) for behavior and verification limits.

### Client login creation and reset examples

The following guides show how an authorized DSM user creates the first NASDrop ID and password and how the DSM icon launch can reset existing credentials.

<details open>
<summary><strong>English</strong></summary>

![English NASDrop ID creation and reset guide](assets/client-login-guide-en.png)

</details>

<details>
<summary><strong>Korean</strong></summary>

![NASDrop account setup and reset guide in Korean](assets/client-login-guide-ko.png)

</details>

<details>
<summary><strong>日本語 (Japanese)</strong></summary>

![日本語 NASDrop ID作成・再設定ガイド](assets/client-login-guide-ja.png)

</details>

<details>
<summary><strong>简体中文 (Simplified Chinese)</strong></summary>

![简体中文 NASDrop ID创建和重置指南](assets/client-login-guide-zh-cn.png)

</details>

## Build from source

Build the SPK with Windows PowerShell and Python 3.11 or later. The build tool packages DSM shell scripts with LF line endings and executable permissions, then validates the resulting archive.

```powershell
.\synology\build-spk.ps1
```

The output is `synology/dist/nasdrop-0.9.26-5-x86_64.spk`. Building from source does not make the package an official Synology Package Center application.

Release validation details are in [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md). The consolidated [provider and security policy](docs/PROVIDER_AND_SECURITY_POLICY.md), provider filename handling in [docs/PROVIDER_FILENAME_GUIDE.md](docs/PROVIDER_FILENAME_GUIDE.md), and DSM launcher-title rules in [docs/DSM_LAUNCHER_GUIDE.md](docs/DSM_LAUNCHER_GUIDE.md) are mandatory references for future changes.

## Configuring a download folder

1. In DSM, open **Control Panel > Shared Folder**.
2. Create a shared folder or select an existing one, then click **Edit > Permissions**.
3. Change the permission category to **System internal user**.
4. Find the NASDrop package account, commonly displayed as `sc-nasdownloadportal`, and grant it **Read/Write** permission.
5. Open NASDrop, go to **Settings > Default destination > Change**, and select the writable shared folder.

Folders without package-account permission appear locked or cannot be selected. If an encrypted shared folder is used, mount it before starting NASDrop. You can also leave the default empty and choose a writable destination separately for each download job.

See Synology's official guides for [creating a shared folder](https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/file_share_create?version=7) and [assigning shared-folder permissions](https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/file_share_privilege?version=7).

## Languages

English is the default interface language. NASDrop automatically follows the browser language when it is Korean, Japanese, or Chinese. It falls back to English when the language is unsupported or cannot be detected.

Users can manually select English, Korean, Japanese, or Chinese on the login screen or from the top navigation. The selection is stored in the browser. DSM Package Center descriptions support the same four languages.

The interface and categorized server errors are translated into all four supported languages. Unclassified provider diagnostics use a localized generic fallback outside the Korean interface.

## Configuring HTTPS with DSM Reverse Proxy

NASDrop listens on plain HTTP port `8791` inside the NAS. For internet access, keep that application port private and terminate HTTPS with DSM's built-in reverse proxy.

1. Open **Control Panel > Login Portal > Advanced > Reverse Proxy** and click **Create**.
2. Configure the source:
   - Protocol: `HTTPS`
   - Hostname: your public hostname, such as `nas.example.com`
   - Port: `8443`
3. Configure the destination:
   - Protocol: `HTTP`
   - Hostname: `127.0.0.1`
   - Port: `8791`
4. Save the rule.
5. Open **NASDrop > Settings > Service address**, enable **Use DSM reverse proxy**, confirm that NAS port `8791` is not exposed directly to the internet, and save the connection settings. This separates login throttling by the client address supplied by the local DSM proxy.
6. Open **Control Panel > Security > Certificate > Settings** and assign a valid certificate for the public hostname to the new reverse-proxy service.

### Real-world example from the maintainer's environment

The screenshots below show the configuration currently used in the maintainer's own environment. They are provided as a working reference, not as values that must be copied exactly. Replace the hostname and NAS IP address with the values for your own network.

In this environment, the router forwards external port `8791` to port `8443` on the NAS at `192.168.1.157`. The router is set to `BOTH`; TCP alone is sufficient for NASDrop.

The DSM reverse-proxy rule receives HTTPS on port `8443` and forwards it to the NASDrop HTTP service at `192.168.1.157:8791`.

Select a language to view both configuration screens. The localized copies are visual translations of the same settings; menu wording may differ slightly depending on the router firmware and DSM version.

<details open>
<summary><strong>English</strong></summary>

![Router port forwarding example in English](assets/router-port-forwarding-example-en.png)

![DSM reverse proxy example in English](assets/dsm-reverse-proxy-example-en.png)

</details>

<details>
<summary><strong>Korean</strong></summary>

![Router port-forwarding example in Korean](assets/router-port-forwarding-example.png)

![DSM reverse proxy example in Korean](assets/dsm-reverse-proxy-example.png)

</details>

<details>
<summary><strong>日本語 (Japanese)</strong></summary>

![日本語のルーターポート転送設定例](assets/router-port-forwarding-example-ja.png)

![日本語のDSMリバースプロキシ設定例](assets/dsm-reverse-proxy-example-ja.png)

</details>

<details>
<summary><strong>简体中文 (Simplified Chinese)</strong></summary>

![简体中文路由器端口转发设置示例](assets/router-port-forwarding-example-zh-cn.png)

![简体中文 DSM 反向代理设置示例](assets/dsm-reverse-proxy-example-zh-cn.png)

</details>

The actual source hostname has been hidden in the screenshot. Enter your own certificate hostname in that field. A matching wildcard certificate, such as `*.example.com`, can be assigned to the rule. For the destination hostname, either `127.0.0.1` (recommended) or your NAS LAN address can be used.

If the public address must remain `https://nas.example.com:8791`, configure the router to forward external TCP `8791` to NAS TCP `8443`. The complete request path is:

```text
Internet HTTPS :8791 -> router -> NAS HTTPS :8443 -> DSM Reverse Proxy -> HTTP 127.0.0.1:8791
```

If the router uses a different external port, such as `8795`, open **NASDrop > Settings > Service address** and set **DSM icon external port** to the same value. The DSM icon will then open `https://your-public-hostname:8795`, while private LAN launches continue to use the internal NASDrop port `8791`.

### DSM icon external port setting

The following screenshots show the new port setting in all four supported interface languages. The public hostname is intentionally hidden.

<details open>
<summary><strong>English</strong></summary>

![English DSM icon external port setting](assets/dsm-icon-port-setting-en.png)

</details>

<details>
<summary><strong>Korean</strong></summary>

![DSM launcher external port settings in Korean](assets/dsm-icon-port-setting-ko.png)

</details>

<details>
<summary><strong>日本語 (Japanese)</strong></summary>

![日本語 DSM アイコン外部ポート設定](assets/dsm-icon-port-setting-ja.png)

</details>

<details>
<summary><strong>简体中文 (Simplified Chinese)</strong></summary>

![简体中文 DSM 图标外部端口设置](assets/dsm-icon-port-setting-zh-cn.png)

</details>

Do not forward any external port directly to NAS port `8791`; that would expose login credentials and portal traffic over unencrypted HTTP.

After saving the configuration, test the exact HTTPS address from outside the local network. A request beginning with `http://` will return `400 Bad Request` because plain HTTP was sent to an HTTPS listener.

The DSM launcher preserves the protocol used to open DSM. It uses port `8791` for private hosts and the external icon port selected in NASDrop settings for public hostnames. See Synology's official [DSM Reverse Proxy documentation](https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/system_login_portal_advanced?version=7).

Login throttling uses the direct peer address by default and does not trust `X-Forwarded-For`. Behind DSM Reverse Proxy, enable **Use DSM reverse proxy** under **NASDrop > Settings > Service address**; otherwise every proxied client shares the loopback address and therefore one login-throttle bucket. NASDrop accepts the rightmost forwarded address only from a loopback proxy and records both peer and selected client addresses in its log. Docker users can set `NASDROP_TRUST_FORWARDED_FOR=true` instead. Never enable this mode when untrusted clients can reach NASDrop port `8791` directly.

Five consecutive failures from one client still block that client for 15 minutes. Separately, a distributed burst of 30 failed sign-ins within 60 seconds pauses all new sign-in attempts for only five seconds; it never creates a global 15-minute account lock.

## Verification

```powershell
python -m py_compile backend.py
python -m unittest discover -s tests -p "test_*.py"
node --test tests/rendered-html.test.mjs tests/gofile-wt-sandbox.test.mjs
```

## Security guidelines

- Keep runtime credentials and device-specific configuration private.
- Never commit `runtime/`, `.env*`, signing keys, or device-specific secrets.
- The local `service.log` records timestamps, client IP addresses, HTTP methods, endpoint paths without query strings, and response status codes for diagnostics. Each log file is limited to 1 MiB and only two rotated backups are retained (about 3 MiB maximum total).
- Use HTTPS whenever the portal is accessible from the internet.
- When NASDrop is opened over HTTP on a public hostname, the login screen and dashboard show an unencrypted-connection warning. HTTP remains available for certificate-free or trusted-network setups; the warning does not appear for private IP addresses, localhost, single-label NAS names, or `.local` hosts.
- Consider an additional access-control layer beyond the NASDrop account login for internet-facing deployments.
- NASDrop does not require DSM administrator passwords or NAS account credentials in the web interface.
- Only submit links and download files that you own or are authorized to access. You are responsible for complying with the source service's terms and applicable law.

### Operational limits

- JSON API request bodies are limited to 16 KiB and idle request handling times out after 30 seconds.
- Login failure tracking retains inactive entries for 15 minutes and is capped at 4,096 client addresses.
- Browser sessions, including a session obtained through the DSM launcher, last seven days. The DSM CGI handoff used to obtain that session expires after 30 seconds and is single-use.
- Archive extraction is stopped after six hours. Archive safety checks also cap entries at 100,000 and extracted data at 1 TiB.
- Individual source files are limited to 300 GiB, and the global download scheduler runs at most three jobs concurrently.

## Supported links and rate-limit protection

NASDrop currently supports standard GigaFile links, GoFile share links, Pixeldrain file-share links, and Buzzheavier signed direct links copied from the provider page. The Chrome companion additionally supports user-assisted AkiraBox, VikingFile, and Send.now handoff when the server advertises the matching capability. For Pixeldrain, NASDrop compares the SHA-256 value reported by the public API with the final downloaded file hash. Provider-specific input, concurrency, expiry, retry, and security rules are maintained in the [provider and security policy](docs/PROVIDER_AND_SECURITY_POLICY.md).

### Send.now browser-assisted downloads

Send.now share pages can require Cloudflare or hCaptcha verification, so pasting the page URL directly into NASDrop is not supported. Install or reload the compatible Chrome companion, sign in to your NASDrop server, and then:

1. Open the normal `https://send.now/FILE_ID` or `https://send.now/d/FILE_ID` page in Chrome.
2. Complete any provider verification yourself. NASDrop does not solve, click, or bypass it.
3. On the current `/d/FILE_ID` challenge page, click **CONTINUE** after verification. The extension does not click or intercept it.
4. On the following page, click the actual **Download [size]** button. For at most one minute after that exact final-button action, the extension watches the same tab for the resulting Chrome download. It cancels the matching browser download, removes its Chrome history entry and submits the original share address plus the issued file address to your NASDrop server. Unrelated downloads are ignored.
5. NASDrop verifies that the destination is public HTTPS, rejects private/local addresses and unsafe URL forms, confirms a resumable file response, and downloads it with one connection.

Do not copy advertisement links, and do not publish the issued direct URL: it may contain a private, expiring token. Because Send.now may use changing public delivery hosts, NASDrop does not pin one CDN hostname; it still rejects HTTP, credentials, fragments, unusual ports, local/private destinations, HTML responses, and non-resumable files. A completed local regression suite does not prove the current provider page flow, so a real user-assisted download must pass before this support is released or synchronized to Docker.

### Buzzheavier signed direct links

A normal Buzzheavier share URL such as `https://buzzheavier.com/FILE_ID` opens the provider page; it is not the direct file URL that NASDrop needs. Use the following steps:

1. Open the normal `https://buzzheavier.com/FILE_ID` share page in a regular browser.
2. On the real Buzzheavier file page, select **Copy download link**. Do not copy an advertisement button or the browser address bar URL again.
3. Confirm that the copied address begins with HTTPS, uses a Buzzheavier download host, contains `/d/FILE_ID`, and still includes its complete `?v=...` query value.
4. Paste that copied address into the NASDrop web portal or Android app. You may then choose a destination folder and extraction option normally.
5. Add the job promptly. NASDrop inspects the signed link and the NAS downloads the file directly; the browser or phone does not relay the file data.

The address accepted by NASDrop has a form similar to:

```text
https://DOWNLOAD-SERVER.buzzheavier.com/d/FILE_ID?v=SIGNED_TOKEN
```

For example, submit the copied `https://ts.buzzheavier.com/d/...?...` style address—not the original `https://buzzheavier.com/...` page address. Do not remove or shorten the query string: the complete `v` value is required to authorize the file request.

Verified Buzzheavier responses provide the final filename through `Content-Disposition`, the file size through `Content-Length`, and byte-range support for segmented downloads and resume.

The `v` value is a signed, potentially time-limited token. If NASDrop reports that the link has expired, is unauthorized, or no longer resolves to a file, return to the original share page, select **Copy download link** again, and submit the newly generated address. Repeatedly retrying the expired address will not refresh it.

> [!CAUTION]
> Treat the complete copied URL as private while it remains valid. Do not post it in public issues, screenshots, chat logs, or documentation. When reporting a problem, remove the entire query string or replace the token with `?v=REDACTED`. Keep the original share-page address so you can generate a fresh signed link later.

NASDrop does not automate Buzzheavier's advertisement page or imitate clicks on the provider page. The user obtains the final link in a normal browser, while the NAS performs only the resulting direct file transfer. Only download files that you own or are authorized to access.

When GoFile returns HTTP 429, NASDrop immediately blocks additional GoFile requests and stores the cooldown deadline in persistent state. The cooldown survives service restarts, preventing repeated retries from making an IP restriction worse. Link-inspection logic may require updates when an external service changes its website or API behavior.

### Warning: excessive requests can cause access restrictions

External download services may rate-limit or block the NAS public IP when they receive too many link inspections, download attempts, parallel connections, or rapid retries. This can result in HTTP 429 responses, temporary access restrictions, or a longer IP-based block. NASDrop cannot remove a restriction imposed by an external service.

To reduce the risk:

- Keep parallel downloads from the same service disabled unless they are necessary.
- Do not repeatedly submit the same link or restart NASDrop to bypass a displayed cooldown.
- When NASDrop reports a protection pause, wait until the displayed cooldown has fully expired.
- Avoid testing the same external service simultaneously from multiple tools or devices on the same public IP.
- If access is already restricted, stop all automated requests and allow sufficient time for the external service to release the restriction.

NASDrop processes jobs from the same provider sequentially by default and preserves GoFile cooldown state across service restarts. These protections reduce request volume, but they cannot guarantee that an external service will not apply its own limits.

## Support and reporting issues

- For installation problems, provider compatibility, and other non-security bugs, open a [GitHub issue](https://github.com/littleweirdlab0514-web/NASDROP/issues).
- For vulnerabilities or reports containing sensitive details, follow [SECURITY.md](SECURITY.md) and do not open a public issue.
- Include the NAS model, DSM version, NASDrop version, relevant logs with account credentials, session tokens, and private URLs removed, and clear reproduction steps.

External services may change without notice. Compatibility fixes are provided on a best-effort basis, and this unofficial package has no support relationship with Synology or the supported download services.

## License

NASDrop is released under the [MIT License](LICENSE). Bundled third-party components retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
