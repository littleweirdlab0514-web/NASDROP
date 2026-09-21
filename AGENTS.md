# NASDrop repository instructions

- Public GitHub README text, release titles, and release notes must be written in English. Keep user-facing app localization separate from release-document language.

## Provider filename invariant

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

## Transfer lifecycle invariants

- Browser handoff must validate every redirect against provider-specific exact HTTPS file hosts; never allow arbitrary regional subdomains or all R2 tenants. HEAD 403 can mean a GET-only signature, not a dead file: use a bounded Range bytes=0-0 probe, do not read the body, and require a valid 206 range response. Persist the verified final URL privately and keep transfer-time redirects disabled. Test redirects, GET-signed URLs, missing HEAD metadata, hostile/looping redirects and secret redaction before claiming provider compatibility.

- Archive passwords must be supplied through stdin, never argv. Do not append a bare `-p`: 7-Zip 26.02 treats it as an empty password. Verify with real encrypted ZIP (ZipCrypto/AES) fixtures, including synthetic punctuation passwords, rather than only mocking subprocess success. Never commit a user's actual archive password.

- Before changing GoFile inspection, scheduling, retries, or transfer concurrency, read `docs/GOFILE_REQUEST_POLICY.md`. Preserve the per-file two-connection cap and shared HTTP 429 cooldown. Do not restore eight concurrent GoFile segments as a generic performance optimization.

- Never resume a `.more` fragment without validating its HTTP range. Replay at its original offset, not by blind append. Preserve validated data on local I/O errors and strip secret headers.
- Persist the transfer layout per job. Collect every child exit code; do not use a bare shell `wait` as proof of successful transfer.
- Pause is not complete until the worker exits. Block resume/delete while stopping, check cancellation after postprocessing gates and before publication, and never run the same job ID twice.
- On service shutdown, stop scheduling, terminate process groups, interrupt disk processing, then persist recoverable state. Test real DSM stop/update separately from local tests.
- GoFile transfer HTTP 429 responses must use the same service cooldown as metadata requests. Do not blindly retry all segments into a rate limit.
- Polling must preserve password form nodes, focus and verification detail state without storing passwords in browser persistence.
- Run `tests/test_transfer_reliability.py` and `tests/job-refresh.test.mjs` alongside the full regression suite after changing these paths.
- Bound stored filenames by UTF-8 bytes, not character count. Preserve extensions and deterministic disambiguation when shortening; enforce the same bound on collision suffixes. Temporary parts must use only a short job ID. Test legacy part migration and long Korean/emoji ordinary files and archives (`tests/test_filename_length.py`).
