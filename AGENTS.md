# NASDrop repository instructions

- Public GitHub README text, release titles, and release notes must be written in English. Keep user-facing app localization separate from release-document language.

## Component ownership and compatibility

- Treat the Synology package server implementation as the canonical NASDrop behavior. Docker must package the same `backend.py`, `transfer_parts.py`, `gofile_wt.mjs`, and `synology/web` files; do not maintain a Docker-only fork of provider or API behavior.
- Keep the Synology package version, backend default version, Docker build argument, Compose build argument, and release tag aligned. Packaging tests must fail on drift.
- Android and Chrome clients must enable optional behavior from explicit `/api/status` capabilities, never by comparing server version strings.
- Additive API changes must retain a safe fallback for clients that do not advertise support. Destructive behavior such as active-job deletion must remain opt-in through its capability.
- A server release is not complete until Synology packaging tests, Docker source-parity and multi-architecture smoke tests, Android contract tests, and Chrome extension contract tests have recorded compatible results.
- Record the supported component matrix and release gate in `docs/COMPONENT_COMPATIBILITY.md` whenever a server or client contract changes.
- For provider work that changes both the canonical server and the Chrome companion, finish and test those two components first. Only after both relevant regression suites and a real provider flow succeed may the Docker maintainer synchronize and verify the same canonical implementation. Never publish or maintain a Docker-only provider fork.

## Shared Synology and Docker bootstrap identity invariant

- A new Docker `/config` or Synology package state must use the documented temporary credentials `nasdrop` / `nasdrop`. Store the password only as a salted PBKDF2 hash; never write plaintext credentials to the configuration file. Preserve any existing custom account on update.
- The bootstrap account must always carry `must_change_password: true`. After it signs in, allow only the minimal account/status reads, credential replacement, and logout. Block downloads, folders, settings, inspection, and job operations until both the ID and password are replaced.
- Accept the short `nasdrop` password only for bootstrap authentication and the current-password confirmation. Never allow it as the replacement password; normal passwords remain subject to the 10–128 character policy. A bootstrap user must replace the ID as well as the password.
- Preserve custom credentials across container restarts. If an existing account still verifies as exactly `nasdrop` / `nasdrop`, restore the mandatory-change flag and revoke existing sessions without rotating or randomizing the credentials.
- Do not replace this fixed bootstrap flow with a random password, environment-generated password, or log-only secret unless the user explicitly changes this product requirement. Security comes from immediate API confinement and forced credential replacement.
- Keep regression coverage for initial creation, legacy-flag restoration, API confinement, replacement, old-session revocation, logout, and preservation of custom credentials.

## Mandatory component handoff and release workflow

- Chrome extension work is owned by the dedicated Codex task named `NASDROP_크롬확장`. Hand every Chrome extension implementation, fix, packaging, documentation, and Chrome-specific verification request to that task. The primary NASDrop task coordinates the server contract and reviews the returned result; it must not silently absorb Chrome-owned work.
- Every Synology NASDrop code update must end with the appropriate automated regression tests and a newly built versioned SPK. Report the SPK path, package version, and SHA-256. A source-only Synology update is not a finished update.
- Do not install the SPK on the user's NAS unless the user explicitly requests installation. The user normally installs and performs the real DSM/provider test.
- Keep Docker on the same canonical source contract, but do not ask the Docker maintainer to publish or release a new image merely because the Synology source changed.
- After the user explicitly reports that the updated Synology package passed the real test, hand the exact Synology changes, API capabilities, version, tests, and any migration notes to the Docker maintainer. Require the Docker implementation to preserve feature parity and pass Docker source-parity and smoke tests.
- The required sequence is: Synology implementation and automated tests -> versioned SPK build -> user installs and reports real-test success -> Docker maintainer synchronizes and verifies the same update. Chrome-owned work is routed through `NASDROP_크롬확장` at the stage where it is needed.
- A normal `v*` tag may automatically build and push only `candidate-<package-version>`. It must never move the version, minor, or `latest` Docker tags. After the required user and Docker verification succeeds, use the manual promotion workflow to retag that exact candidate digest without rebuilding it.

## Provider filename invariant

- Before changing any provider adapter, host rule, concurrency/retry policy, or provider security boundary, read and update `docs/PROVIDER_AND_SECURITY_POLICY.md`. It is the consolidated provider and security baseline; narrower provider guides remain authoritative where they impose stricter rules.

- Never treat a provider page's visible filename as authoritative. Providers may mask, replace, localize, or duplicate it.
- For every file type—not only archives—prefer the final download response's RFC 5987 `Content-Disposition: filename*`, then `filename`, and only then inspected page/API metadata.
- Parse the last `Content-Disposition` header after redirects. Sanitize the result against separators, control characters, traversal names, excessive length, and destination collisions.
- Resolve the actual filename before archive detection, extraction-folder naming, final publication, and the public job-name update.
- When the provider supports a bodyless HEAD request, resolve the actual filename during link inspection so the correct name is present before the job enters the queue. Keep transfer-time header capture as a fallback.
- Capture response headers only inside the job's hidden `.nasdrop-tmp/<job-id>` workspace. Do not persist cookies, authorization headers, tokens, or response headers after processing.
- Filename discovery must not download the file body a second time. Use a supported HEAD request or headers captured from the real transfer; failure must fall back safely without failing the download.
- Preserve the GigaFile masked-name regression fixture exactly:
  `●ファイル名が置換されました※DLしたファイルは、原題まま表示されます。●`
- On a GigaFile multi-file page, queue every individual file rather than the synthesized bundle ZIP. Resolve each child's response filename before queueing; if that probe fails, use a neutral child-ID label and let transfer-time headers correct it—never expose the masked fixture as a filename and never block the download only because name discovery failed.
- Any provider or download-pipeline change must test at least one ordinary file and one archive, multilingual `filename*`, redirects or repeated headers, missing headers, malicious path-like names, and duplicate destinations.

See `docs/PROVIDER_FILENAME_GUIDE.md` for the rationale and release checklist.

## DSM launcher identity invariant

- The DSM desktop launcher title is the non-localized brand literal `NASDrop`. Never replace it with an i18n token such as `nasdrop:title`; DSM can render the unresolved token before application texts are loaded.
- Keep `"texts": "texts"` in `ui/config`. Any localized launcher description must be listed in `preloadTexts`.
- Package builds must inspect the generated `package.tgz`, not only source files, and fail unless the launcher title is exactly `NASDrop` and no `nasdrop:title` title value is present.
- Every release must test the DSM desktop/start-menu label before and after opening the app, including a browser refresh or new DSM session.

See `docs/DSM_LAUNCHER_GUIDE.md` for the packaging rule and regression checklist.

The DSM icon is a navigation shortcut only. It opens the ordinary NASDrop login page and never creates a DSM-authenticated NASDrop session. Do not restore `launcher.cgi`, SynoToken exchange, static bearer tokens, HMAC launcher handoffs, or their API endpoints without a new explicit product decision. Package validation must reject the obsolete CGI and handoff path.

## Transfer lifecycle invariants

- Release 0.9.22 supersedes the older diagnostic-label rule below: public handoff errors must use fixed, secret-free human-readable explanations without diagnostic tags. Numeric transfer markers remain internal only. Viking redirects may additionally use a single subdomain of `vikingfile.com` with validated `expires`/`md5` fields; HTTPS, expiry checks, redirect bounds and range validation remain mandatory.

- Browser-handoff errors must not equate every interruption with link expiry. Emit only fixed reason codes and numeric transfer diagnostics; never include signed URLs, arbitrary hosts, headers or remote error text. AkiraBox retries are limited to three attempts after 10/20/30 seconds and only selected transient curl errors with successfully validated/committed partial data. Do not retry HTTP rejection, invalid ranges, redirects or local writes, and do not apply this policy to GoFile or VikingFile implicitly. Test real shell retry bounds and resumed offsets, not just generated strings.

- Browser handoff must validate every redirect against provider-specific HTTPS file hosts. Akira hosts stay exact. Viking permits a single bucket label only under pinned R2 account 04b3d96d52475741e6b10f97f0a84a16, as approved after official redirects exposed different buckets. Never allow all R2 tenants, nested/lookalike suffixes or internal addresses. HEAD 403 can mean a GET-only signature, not a dead file: use a bounded Range bytes=0-0 probe, do not read the body, and require a valid 206 range response. Persist the verified final URL privately and keep transfer-time redirects disabled. Test redirects, GET-signed URLs, missing HEAD metadata, hostile/looping redirects and secret redaction before claiming provider compatibility.
- Progress must count unique covered bytes, not the sum of a committed part and its overlapping .more fragment during copying. Exclude headers/error bodies and use persisted layout plus validated range offsets. Do not hide accounting errors with a monotonic percentage clamp.

- Archive passwords must be supplied through stdin, never argv. Do not append a bare `-p`: 7-Zip 26.02 treats it as an empty password. Verify with real encrypted ZIP (ZipCrypto/AES) fixtures, including synthetic punctuation passwords, rather than only mocking subprocess success. Never commit a user's actual archive password.

- Before changing GoFile inspection, scheduling, retries, or transfer concurrency, read `docs/GOFILE_REQUEST_POLICY.md`. Preserve the per-file two-connection cap and shared HTTP 429 cooldown. Do not restore eight concurrent GoFile segments as a generic performance optimization.

- Never resume a `.more` fragment without validating its HTTP range. Replay at its original offset, not by blind append. Preserve validated data on local I/O errors and strip secret headers.
- Persist the transfer layout per job. Collect every child exit code; do not use a bare shell `wait` as proof of successful transfer.
- Pause is not complete until the worker exits. Block resume/delete while stopping, check cancellation after postprocessing gates and before publication, and never run the same job ID twice.
- Safe-delete opt-in (`job_safe_delete` / `stop_active:true`) may accept deletion while stopping, but cleanup must wait for worker/process ownership to end. Preserve published output, reject symlink workspaces, retain records on cleanup failure, and never replay destructive requests after restart. Legacy delete remains strict. See `docs/SAFE_JOB_DELETE.md`.
- On service shutdown, stop scheduling, terminate process groups, interrupt disk processing, then persist recoverable state. Test real DSM stop/update separately from local tests.
- GoFile transfer HTTP 429 responses must use the same service cooldown as metadata requests. Do not blindly retry all segments into a rate limit.
- Polling must preserve password form nodes, focus and verification detail state without storing passwords in browser persistence.
- Run `tests/test_transfer_reliability.py` and `tests/job-refresh.test.mjs` alongside the full regression suite after changing these paths.
- Bound stored filenames by UTF-8 bytes, not character count. Preserve extensions and deterministic disambiguation when shortening; enforce the same bound on collision suffixes. Temporary parts must use only a short job ID. Test legacy part migration and long Korean/emoji ordinary files and archives (`tests/test_filename_length.py`).
