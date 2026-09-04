# NASDrop repository instructions

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
