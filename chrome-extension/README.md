# NASDrop for Chrome

This Manifest V3 extension connects supported sites' download controls to an existing NASDrop server. After signing in once, click a recognized download button on the provider page. NASDrop receives the link and the page shows the result.

Version 0.5.0 adds English, Korean, Simplified Chinese and Japanese across the popup, job statuses, site notices, context menus and notifications, with a persistent language selector. It retains job pause/resume/deletion, extraction/password controls and automatic progress updates. AkiraBox and Viking require NASDrop 0.9.19 or later with the matching browser-handoff capability. See [HANDOFF.md](HANDOFF.md) for the contract and outstanding live-NAS verification.

Server, Synology packages and setup instructions: [NASDrop project](https://github.com/littleweirdlab0514-web/NASDROP). This extension requires a running NASDrop server; it does not download files independently. This is a developer-mode distribution, not an official Chrome Web Store release.

## Languages

Choose **Automatic (browser)** or English, 한국어, 中文（简体）, 日本語 at the top of the popup, before or after login. Unknown, unavailable and unsupported browser languages fall back to **English**. The choice persists locally and applies to subsequent page actions and notifications. Chrome's extension-management description follows Chrome's own language. Server-supplied diagnostic errors and filenames are preserved verbatim rather than machine-translated. Changing language does not change extraction defaults or existing jobs.

- Buzzheavier: **Download File** and **Copy download link** use the page's same-origin link-generation endpoint. The extension reads its signed `HX-Redirect` header and sends the result to NASDrop, without following the file URL in Chrome. No clipboard-reading permission is needed. The Copy action sends to NASDrop instead of copying to the clipboard.
- GigaFile: inline `download(...)` controls and direct download links submit the individual file ID.
- GoFile: `data-action="download"` controls submit the row's file ID, or the current share when no file row is present.
- Pixeldrain: direct `/api/file/ID?download` links and viewer download controls submit the file share. Version 0.2.1 recognizes both the current Svelte sidebar download button and the no-preview panel's download button, including clicks on their icons or labels.

Controls inserted after page load are supported. Only genuine, unmodified primary clicks are redirected; Ctrl/Command/Shift/Alt clicks retain the site's behavior. Unknown controls and advertisements are left alone. Failed NASDrop requests remain visible and never automatically start a local download. Check the NASDrop queue before retrying an uncertain result.

## Install locally

1. Extract the downloaded extension ZIP into a permanent directory, then open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked** and choose the extracted directory containing `manifest.json` (or this `chrome-extension` directory when using the source repository).
4. Open the NASDrop extension, enter the full NASDrop address (for example, `http://192.168.1.10:8791`), and sign in.
5. Reload already-open provider pages after installation or extension updates. Click the site's download control; opening the extension each time is unnecessary.

To update, replace the files in the same installed extension directory, click the extension's **Reload** button in `chrome://extensions`, then refresh provider tabs. Keeping the same installed directory preserves its local preferences. Do not load a second copy alongside the first.

Chrome requests access to the listed provider sites for automatic button detection and separately requests access to the NASDrop host when connecting (Chrome host permissions are not port-scoped). The extension stores the server address, session token, username, language and extraction preferences in Chrome local storage, restricted to trusted extension contexts. Provider content scripts cannot read this storage; they receive only readiness/capability and resolved language. Passwords and signed source links are not persisted by the extension. Browser cookies are never copied or sent to the NAS.

The NASDrop server must already have a writable default destination configured. Per-job destination selection remains available in the full NASDrop web portal.

## Job controls

- Press Enter in the sign-in password field to connect.
- **Automatically extract archives**, immediately right of Refresh, is an extension-local default for all newly submitted jobs, including manual links, page/context-menu actions, multi-file shares and supported browser handoffs. Existing saved preferences are preserved across login and popup reopening; new installations retain the previous enabled default. This toggle never changes NAS global settings or existing jobs. When space is limited, Clear completed wraps below the refresh/toggle group.
- Click a registered job to reveal its extraction checkbox and archive-password field. Changing an existing job's extraction options requires a server advertising `job_processing_options: true`. Jobs already in postprocessing or a terminal state cannot be edited. Older servers still support password-required retries through the existing password endpoint.
- An empty password preserves the server's existing archive password when extraction stays enabled. Disabling extraction removes that archive password. Password values are never stored by the extension, returned from the server, or restored into the form.
- Progress refreshes every 5 seconds while jobs are active and every 15 seconds when idle. Requests do not overlap; failures back off to 60 seconds. Refreshing preserves the selected job's password input and focus.
- With the popup closed, the `alarms` permission enables approximately once-per-minute checks only while work remains active. Network failures back off up to 5 minutes. Newly password-required jobs trigger one notification per waiting episode, subject to Chrome/OS notification settings.
- **Clear completed** beside Refresh removes completed job records after confirmation. It does not delete downloaded files from the NAS.
- Click a job to reveal **Pause**, **Resume** and **Delete**. Pausing retains partial downloads for resumption. While the server reports `stopping`, resume/delete stay locked; wait until the worker has exited. Extraction/publication cannot be interrupted through these controls.
- Deleting an unfinished stopped job confirms removal of its temporary files as well as its record. Deleting a completed job removes its record only and keeps published NAS output. Server-side cleanup failure handling requires the updated server; the extension preserves the job on API errors. No filesystem path is supplied by the extension.

## Verification limits

The Buzzheavier live page inspected on 2026-09-21 uses `a.download-btn[hx-get]` and `a.copy[onclick]` targeting the same `/FILE_ID/download?t=...` endpoint. Its public script reads `HX-Redirect`; clicking Download File reached the file host in Chrome, where this test browser reported `ERR_BLOCKED_BY_CLIENT`. Full installed-extension-to-NAS transfer has not been verified. Automated tests cover the observed control shapes, signed-link validation, click cancellation, duplicate clicks, login errors, restricted worker messages, polling/backoff, Enter submission, password-input preservation, processing options, and completed-history clearing. Popup interaction tests use a mocked DOM, not an installed Chrome extension. Other providers' live DOM variants may require adapter updates.
