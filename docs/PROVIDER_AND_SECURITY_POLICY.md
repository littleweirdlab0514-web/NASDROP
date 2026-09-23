# NASDrop provider behavior and security policy

Last updated: 2026-09-23
Applies to: NASDrop Server 0.9.26-6 credential-bootstrap test build

This document is the implementation and maintenance baseline for supported download providers and the security controls shared by the Synology and Docker distributions. The Synology package is canonical; Docker must package the same provider and API implementation rather than carrying provider-specific forks.

Provider websites are external systems and may change without notice. “Supported” means that NASDrop implements the documented validation and transfer path; it does not guarantee that every link, region, account, challenge, or provider-side rate limit will remain available.

## Shared download behavior

- NASDrop accepts only the provider URL shapes listed below. It is not a generic arbitrary-URL downloader.
- Every job is written under the hidden `.nasdrop-tmp/<job-id>` workspace. Only a verified completed file or successfully extracted result is published to the selected destination.
- The final response filename is preferred in this order: RFC 5987 `Content-Disposition: filename*`, ordinary `filename`, then inspected API/page metadata. Names are sanitized for traversal, control characters, separators, reserved names, excessive UTF-8 byte length, and destination collisions.
- The normal segmented mode uses up to eight byte ranges, except where a provider-specific limit below overrides it. Single-connection mode remains resumable and still receives final size, integrity, and archive checks.
- At most three jobs run globally. Same-provider work defaults to one job at a time. The optional same-provider setting permits the configured limit, normally two; provider-specific connection and cooldown rules still take precedence.
- Files discovered from one folder or multi-file share become separate jobs. Their start times are staggered by 20 seconds so bulk registration does not immediately burst every request.
- ZIP, AES ZIP, 7z, RAR, and TAR-family archives may be extracted in the private workspace. EGG is downloaded unchanged and is not extracted. Passwords are stored separately from public job state and supplied to 7-Zip through standard input, not the command line.
- Provider tokens, cookies, signed URLs, download keys, archive passwords, authorization headers, and response-header captures must never appear in public job objects or user-facing errors.

## Provider matrix

| Provider | Accepted input | Registration path | Transfer policy | Typical recovery |
| --- | --- | --- | --- | --- |
| GigaFile | Official `https://<node>.gigafile.nu/<id>` share | Web, Android, Chrome; inspection is queued asynchronously | User-selected single/segmented mode; multi-file shares create individual jobs | Enter a required 1–4 character download key, wait after provider throttling, or enqueue a fresh share |
| GoFile | Official `https://gofile.io/d/<id>` share | Server API/page inspection | Maximum two connections per file; persistent provider-wide cooldown on 429/network bursts | Do not force retries; wait for the displayed cooldown and reduce same-provider concurrency |
| Pixeldrain | Official `/u/<id>` share on recognized Pixeldrain domains | Server metadata API | User-selected single/segmented mode; provider SHA-256 is verified | Retry only after checking availability; a hash mismatch is an integrity failure |
| Buzzheavier | Signed `https://<delivery>.buzzheavier.com/d/<id>?v=<token>` from **Copy download link** | Direct paste or Chrome’s official Download/Copy control | User-selected single/segmented mode; Range support is mandatory | Generate a fresh signed link when it expires or returns 401/403/404 |
| AkiraBox | Official share plus the prepared signed file URL | Chrome browser handoff only | Forced single connection; bounded transient resume retries | Complete any site interaction yourself, prepare a fresh official button, then submit again |
| VikingFile | Official share plus its prepared file URL | Chrome browser handoff only | Forced single connection; strict redirect/account allowlist and Range validation | Use a fresh official button/link; do not broaden the host allowlist to make one sample pass |
| Send.now | Official share plus the final browser-created download URL | Chrome user-assisted handoff only | Forced single connection; DNS validation and IP pinning | Complete verification and Continue yourself, then click the final `Download [size]` button again |

## GigaFile

### Characteristics

- A share may contain one file, many individual files, or a provider-generated bundle ZIP.
- NASDrop deliberately selects every individual file rather than the synthesized bundle ZIP. This preserves the real names and allows independent resume, verification, extraction, and failure handling.
- The provider can display a masked placeholder filename. Page text is therefore not authoritative; NASDrop probes response metadata when possible and corrects the queue name again from the real transfer headers.
- Link inspection is queued instead of blocking the enqueue request. Up to 100 inspection placeholders may wait, and only one inspection-pending job is processed at a time.
- A protected share can require a separate 1–4 character GigaFile download key. This is not an archive password.

### Required response

- Keep the official node hostname and same-host redirect boundary; do not accept lookalike domains or cross-host redirects.
- Keep download keys out of URLs, logs, browser persistence, public jobs, and `jobs.json`. Remove the key after the download URL has been resolved.
- If no key was supplied, hold the job in `download_key_required` rather than discarding resumable data. Reject incorrect keys without automatic repeated attempts.
- If filename probing fails, retain a neutral file-ID label and let transfer-time headers correct it. Do not block a valid download only because early name discovery failed.
- Bulk page changes must be tested with both a single file and an unlimited multi-file share; never reintroduce the provider bundle ZIP as the default selection.

## GoFile

### Characteristics

- NASDrop uses a guest account token, a short-lived website token, and the GoFile contents API.
- Shared folders are traversed recursively and paginated. Files become separate jobs while validated relative folder structure is recreated below the selected destination.
- GoFile has shown HTTP 429 and temporary IP restrictions under high request/concurrency pressure.

### Required response

- Preserve the two-connection maximum per file even when global segmented mode is eight parts. Single mode uses one connection.
- Serialize metadata calls with at least a two-second interval. Do not query an entire bulk queue simultaneously or refresh metadata unnecessarily.
- A 429 in metadata or file transfer trips the same persistent provider cooldown. Honor bounded `Retry-After` guidance; the default rate-limit cooldown is 30 minutes, network cooldown is 5 minutes, and the maximum is 6 hours.
- Do not blindly retry every segment, force-resume waiting jobs, or raise connection counts as a performance workaround.
- Remote GoFile JavaScript runs only in the isolated WT helper described under the security policy. Never execute it in the main server process.

See [GOFILE_REQUEST_POLICY.md](GOFILE_REQUEST_POLICY.md) for the dedicated request-volume rules.

## Pixeldrain

### Characteristics

- NASDrop resolves metadata through the official file information API and downloads through the official file endpoint.
- The API supplies the filename, size, availability state, and SHA-256.

### Required response

- Accept only the recognized Pixeldrain domains and exact `/u/<id>` share form.
- Require a valid positive size and a 64-character SHA-256 before queueing.
- Treat a final SHA-256 mismatch as corruption: do not publish the file. A retry must start from data that still passes range and integrity checks.
- Surface the provider’s fixed availability explanation without exposing arbitrary remote response bodies.

## Buzzheavier

### Characteristics

- A normal share page is not itself a downloadable input. NASDrop needs the signed URL produced by **Copy download link**, or the equivalent result obtained after the user clicks an official control through the Chrome companion.
- Signed links expire and may use rotating first-party delivery subdomains.

### Required response

- Require HTTPS, the default port, the exact `/d/<id>` form, one `v` token, no credentials, and no fragment.
- Permit redirects only within validated Buzzheavier delivery hosts. Require non-HTML metadata, a valid size, and byte-range support.
- Store the signed URL only in restricted job-secret state. Public job source remains the canonical unsigned share.
- On 401, 403, or 404, ask for a newly generated Copy link; do not hammer an expired token.

## AkiraBox

### Characteristics

- The share page may show advertisements or require user interaction before its official button contains a signed file URL.
- A pasted share URL alone is insufficient. The Chrome companion observes only the prepared official control after a real user click and sends the share plus issued URL to NASDrop.

### Required response

- Never automate advertisement clicks, counters, CAPTCHA, or Cloudflare. The user performs site interaction.
- Validate the share and signed URL separately, including scheme, host, path, expiration, signature shape, and every redirect destination.
- Verify metadata with HEAD or a bodyless Range `0-0` fallback. Reject HTML/error bodies and non-resumable responses.
- Use one download connection. Only selected transient transport interruptions may retry, at most three times after 10/20/30 seconds and only from already validated byte ranges. HTTP rejection, invalid ranges, redirects, and local write errors are not transient retries.

## VikingFile

### Characteristics

- VikingFile also requires an official browser-prepared URL. Some valid signed objects reject HEAD but accept a minimal Range request.
- Observed delivery may use regional `vikingfile.com` hosts or one bucket label beneath the pinned Cloudflare R2 account used by VikingFile.

### Required response

- Keep the exact regional-host and pinned-R2-account rules. Never allow arbitrary R2 tenants, nested subdomains, or a broad “any public host” fallback.
- When HEAD returns 403/405/501, issue only `Range: bytes=0-0`, read no file body, and require a correct 206/`Content-Range` response.
- Validate signed expiration fields, redirects, filename, size, and range support before queueing. Persist the final issued URL privately and disable transfer-time redirects.
- Use one connection. Do not copy AkiraBox’s special retry policy to VikingFile without separate evidence and tests.

## Send.now

### Characteristics

- Send.now uses a user-assisted browser flow. The user completes security verification and presses Continue normally. Only the later final `Download [size]` action is handed to NASDrop.
- Chrome temporarily observes the resulting same-tab download, cancels the local copy after matching it, removes that Chrome download-history entry, and submits the final HTTPS URL. Because Chrome does not expose the originating tab ID in this event, only one Send.now handoff may wait at a time.
- Delivery hosts rotate, so a brittle static CDN allowlist is unsuitable.

### Required response

- Never solve or bypass CAPTCHA/security verification, copy challenge cookies, or treat Continue as the final file action.
- Require an authenticated NASDrop session, a canonical Send.now share/referrer, HTTPS/default port, no credentials or fragment, a non-share file path, valid file metadata, and byte-range support.
- Resolve every candidate hostname and require every returned address to be globally routable. Reject loopback, private, link-local, reserved, `.local`, and mixed public/private answer sets.
- Connect inspection directly to a validated address while retaining the original hostname for TLS SNI. Disable ambient proxies for this check. Revalidate immediately before transfer and pin curl with `resolve` so the hostname cannot be rebound to an internal address.
- Use one connection. On interruption, keep verified partial data and ask the user to generate a fresh final link if the issued URL has expired.

## Unsupported and deferred services

- X-Share, UsersDrive, Nitroflare, Viking lookalikes, arbitrary direct URLs, and other hosts not listed above are not accepted by the current server.
- A service that requires browser execution, CAPTCHA, account cookies, advertisement navigation, or a short-lived issued URL is not made “generic” by relaxing validation. It needs a provider-specific, user-initiated adapter and server-side validation contract.
- CAPTCHA automation, challenge bypass, copied browser cookies, and unrestricted remote-browser control are outside the supported design.
- A new provider must define its canonical share form, official user action, final host/redirect rules, expiration evidence, size/name/range validation, concurrency policy, safe error behavior, and live test gate before capability advertisement.

## Security policy introduced in 0.9.26

### DSM launcher and first-run account

- The DSM icon is only a shortcut to the ordinary NASDrop login page. It does not accept DSM cookies or SynoToken and does not create a NASDrop session.
- A new Synology package state creates the same temporary `nasdrop` / `nasdrop` login as Docker, stored as a salted PBKDF2 hash. Both ID and password must be replaced before downloads, folders, settings, or jobs can be used.
- Existing custom credentials remain unchanged through package updates. An untouched legacy default account regains the mandatory-change flag and has its prior sessions revoked.
- The old `launcher.cgi`, handoff endpoints, web token-fragment exchange, and `dsm_launcher_secret` are removed. The upgrade script deletes the obsolete secret and any stale CGI at the exact package path. Package validation rejects their return.
- The login form uses semantic controls, browser password autofill, and a visible HTTP warning. Internet-facing installations should use HTTPS through a trusted reverse proxy.

### GoFile remote-script containment

- GoFile’s remote WT script is never executed in the main Python server.
- The helper uses a null-prototype VM context with string and Wasm code generation disabled. Injected `navigator` values are created inside that context, not passed as host-realm objects.
- Node starts under the permission model with read access only to the helper entry file and no file-write, child-process, worker, native-addon, or WASI permissions.
- Regression tests must retain both the host `Date` constructor and `navigator.constructor.constructor` escape probes.
- `node:vm` is not treated as a complete security boundary. New host objects must not be injected, permission restrictions must not be relaxed, and any new escape report is release-blocking.

### Send.now SSRF and DNS-rebinding defense

- URL syntax checks alone are insufficient. All DNS answers are validated as public, inspection uses the validated IP directly, proxies are bypassed, TLS still verifies the original hostname, and the transfer pins a newly validated IP.
- Redirects are inspected one at a time with a strict bound. A provider page, local address, credentials, fragments, unusual ports, HTML, invalid ranges, or oversized files are rejected.

### Account and session security

- Passwords use PBKDF2-HMAC-SHA-256 with a per-account random salt and 600,000 iterations. Comparisons are constant-time.
- Sessions are random, time-limited, bounded in memory, and revoked when credentials change.
- Five failed logins from one client produce a 15-minute client block. A short global cooldown limits distributed bursts without becoming the primary authentication control.
- Both Synology and Docker intentionally start new configurations with `nasdrop` / `nasdrop`, stored only as a salted hash and marked `must_change_password`. Until both credentials are replaced, only minimal account/status reads, credential replacement, and logout are allowed. Normal download, folder, settings, inspection, and job APIs return `password_change_required`.
- The short Docker bootstrap password is accepted only for initial authentication/current-password confirmation and cannot be saved as the replacement password. Custom credentials are preserved; an untouched legacy default regains the mandatory-change flag without password randomization.

### Filesystem, archive, and secret boundaries

- Destination paths must remain within configured storage roots and be writable by the package/container account. Folder traversal hides system/internal entries and never grants NAS permissions automatically.
- Job workspaces and secret files use restricted state paths. Deletion is scoped to the exact non-symlink job workspace and never follows links or removes published output.
- Archive entries reject absolute paths, `..` traversal, symlinks, and unsafe link-like metadata. Entry count, expanded size, extraction time, and publication paths are bounded. Extraction passwords never appear in argv.
- Maximum accepted file size is 300 GiB. Provider metadata, Range responses, final size, and available hashes are checked before publication.

### Web and API boundaries

- API responses carrying authentication or job state use `Cache-Control: no-store`.
- Web responses use a restrictive Content Security Policy, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, frame denial, and a restrictive Permissions Policy.
- Request bodies, inspection cache, sessions, handoffs, redirects, and retries are bounded.
- Browser handoff errors use fixed secret-free messages. Never return signed URLs, tokens, headers, remote response bodies, or arbitrary hostnames to the public UI or logs.
- Plain HTTP remains available for explicitly chosen local/private deployments and HTTP-origin DSM launches, but it does not provide transport confidentiality. Internet-facing access should use HTTPS through a correctly configured reverse proxy.

## Change and release rules

1. Read this document and the provider-specific references before changing parsing, hosts, retries, concurrency, filenames, or authentication.
2. Do not loosen a provider rule merely because one sample fails. Capture the official flow, add a narrow rule, and retain hostile/lookalike tests.
3. Update this document whenever a provider contract or security boundary changes.
4. Run provider unit tests, transfer reliability tests, authentication tests, JavaScript/Chrome contract tests, and SPK packaging inspection.
5. Build a versioned SPK and have the user complete the real Synology flow. Only after success should Docker be synchronized and smoke-tested from the same canonical source.
6. Never claim a provider flow is verified solely from mocked DOM/API tests; record the exact real-NAS test separately.
