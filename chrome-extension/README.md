# NASDrop for Chrome

This Manifest V3 extension connects supported sites' download controls to an existing NASDrop server. After signing in once, click a recognized download button on the provider page. NASDrop receives the link and the page shows the result.

Version 0.5.1 supports English, Korean, Simplified Chinese and Japanese across the popup, job statuses, site notices, context menus and notifications, with a persistent language selector. It retains job pause/resume/deletion, extraction/password controls and automatic progress updates. AkiraBox and Viking require NASDrop 0.9.19 or later with the matching browser-handoff capability. See [HANDOFF.md](HANDOFF.md) for the contract and outstanding live-NAS verification.

Server, Synology packages and setup instructions: [NASDrop project](https://github.com/littleweirdlab0514-web/NASDROP). This extension requires a running NASDrop server; it does not download files independently. This is a developer-mode distribution, not an official Chrome Web Store release.

## Languages

Choose **Automatic (browser)** or English, 한국어, 中文（简体）, 日本語 at the top of the popup, before or after login. Unknown, unavailable and unsupported browser languages fall back to **English**. The choice persists locally and applies to subsequent page actions and notifications. Chrome's extension-management description follows Chrome's own language. Server-supplied diagnostic errors and filenames are preserved verbatim rather than machine-translated. Changing language does not change extraction defaults or existing jobs.

- Buzzheavier: **Download File** and **Copy download link** use the page's same-origin link-generation endpoint. The extension reads its signed `HX-Redirect` header and sends the result to NASDrop, without following the file URL in Chrome. No clipboard-reading permission is needed. The Copy action sends to NASDrop instead of copying to the clipboard.
- GigaFile: inline `download(...)` controls and direct download links submit the individual file ID.
- GoFile: `data-action="download"` controls submit the row's file ID, or the current share when no file row is present.
- Pixeldrain: direct `/api/file/ID?download` links and viewer download controls submit the file share. Version 0.2.1 recognizes both the current Svelte sidebar download button and the no-preview panel's download button, including clicks on their icons or labels.

Controls inserted after page load are supported. Only genuine, unmodified primary clicks are redirected; Ctrl/Command/Shift/Alt clicks retain the site's behavior. Unknown controls and advertisements are left alone. Failed NASDrop requests remain visible and never automatically start a local download. Check the NASDrop queue before retrying an uncertain result.

## Install locally

Version 0.5.1 keeps file controls collapsed by default. Click a file to expand Pause, Resume, Delete and the archive-password field together below its progress display; click again to collapse. Automatic extraction is configured only in the toolbar. Long filenames wrap within the card.

Detailed Korean instructions: [한국어 설치 및 사용 안내](INSTALL.ko.md).

First-login permission instructions with translated examples: [English / 한국어 / 日本語 / 简体中文](FIRST_LOGIN.md).

### 1. Prepare the NAS

Install and start NASDrop on the NAS. Open its web portal, create or confirm your account, and select a writable default download destination. The extension uses the same NASDrop account, which may differ from your DSM account. Use server 0.9.19 or later for AkiraBox/Viking forwarding. This remains a preview with live-NAS end-to-end verification pending.

### 2. Download and extract the extension

Open the [Chrome extension release](https://github.com/littleweirdlab0514-web/NASDROP/releases/tag/chrome-v0.5.1) and download **NASDrop-Chrome-0.5.1.zip** under Assets. This is different from GitHub's automatically generated **Source code (zip)** and the Synology `.spk` installer.

Extract the entire ZIP into a permanent folder such as `C:\Tools\NASDrop-Chrome`. Do not run files inside the ZIP or select the ZIP itself. The folder you will select must contain `manifest.json`, `background.js`, `popup.html`, `icons` and `_locales` directly. If there is an extra nested folder, select that inner folder. Keep this directory in place while the extension is installed.

### 3. Load in desktop Chrome

1. Type `chrome://extensions` in Chrome's address bar and press Enter.
2. Turn on **Developer mode** in the upper-right corner.
3. Click **Load unpacked** and select the extracted folder containing `manifest.json`.
4. Confirm the **NASDrop for Chrome** card appears and is enabled, with version **0.5.1**.
5. Open Chrome's puzzle-piece Extensions menu and pin NASDrop to the toolbar for easy access.

These steps follow [Chrome's official unpacked-extension instructions](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked). This package is not a Chrome Web Store installation. Managed work/school Chrome may prohibit developer-mode extensions; ask the administrator rather than bypassing the policy. This guide is for desktop Chrome, not mobile Chrome.

### 4. Connect and test

1. Click the NASDrop toolbar icon. Select your language or leave **Automatic (browser)** enabled; unsupported languages use English.
2. Enter the complete NASDrop address, including `http://` or `https://` and its port when needed. Example: `http://192.168.1.10:8791`. Replace the example with your own address; do not use the DSM control-panel address unless it actually serves NASDrop.
3. Enter the same username/password used in the NASDrop web portal and click **Connect**, or press Enter in the password field.
4. On the first login, Chrome may request additional permission for the NAS address. Verify that it is your NAS and click **Allow**. Then click the NASDrop toolbar icon to reopen the extension and **sign in again** (re-enter your password if needed). Granting permission is not the same as completing login. See the [four-language illustrated guide](FIRST_LOGIN.md). Do not bypass certificate or browser security warnings; fix HTTPS configuration first.
5. Check that the destination shown is correct. Set **Automatically extract archives** beside Refresh as desired.
6. Reload any provider tabs that were open before installation. Open a supported share page and wait for its official download button to be ready. For AkiraBox/Viking, use that page button rather than pasting a share URL into manual entry.
7. Click the official download button once, wait for the NASDrop result, then open the extension to inspect the queue. Buzzheavier also supports **Copy download link**. Do not click advertisements or retry an uncertain submission until you check the queue.

To update, replace the files in the same installed extension directory, click the extension's **Reload** button in `chrome://extensions`, then refresh provider tabs. Keeping the same installed directory preserves its local preferences. Do not load a second copy alongside the first.

### Troubleshooting and removal

- **Manifest missing / could not load:** extract the ZIP fully and select the directory directly containing `manifest.json`, not its parent or the ZIP.
- **No NASDrop icon:** check that the extension is enabled and pin it from Chrome's Extensions menu.
- **Cannot connect:** open the same NASDrop address in a normal tab, confirm that the service is running and reachable from this computer, and check host permission. Do not post account passwords, session tokens or private signed links when reporting errors.
- **Download button does nothing / context invalidated after update:** reload the provider page after reloading the extension. Check the extension's site-access settings and ensure you clicked a supported official button.
- **Server unsupported:** verify the NASDrop server version. A new extension alone does not upgrade the NAS. After a server update, refresh the connection and open a fresh share page.
- **Expired link or failed older job:** obtain a newly prepared link from the share page and register a new job; check the list first to avoid duplicates. Site/browser/IP restrictions may still prevent NAS access.
- **No password notification:** check Chrome and operating-system notification permissions; the popup also shows password-required jobs.
- **Uninstall:** use **Remove** on the extension card. This removes the extension's local preferences, not the NASDrop server or its already registered jobs. Stop/delete NAS jobs explicitly if desired. Do not remove the unpacked folder until the extension is removed.

Chrome requests access to the listed provider sites for automatic button detection and separately requests access to the NASDrop host when connecting (Chrome host permissions are not port-scoped). The extension stores the server address, session token, username, language and extraction preferences in Chrome local storage, restricted to trusted extension contexts. Provider content scripts cannot read this storage; they receive only readiness/capability and resolved language. Passwords and signed source links are not persisted by the extension. Browser cookies are never copied or sent to the NAS.

The NASDrop server must already have a writable default destination configured. Per-job destination selection remains available in the full NASDrop web portal.

## Job controls

- Press Enter in the sign-in password field to connect.
- **Automatically extract archives**, immediately right of Refresh, is an extension-local default for all newly submitted jobs, including manual links, page/context-menu actions, multi-file shares and supported browser handoffs. Existing saved preferences are preserved across login and popup reopening; new installations retain the previous enabled default. This toggle never changes NAS global settings or existing jobs. When space is limited, Clear completed wraps below the refresh/toggle group.
- Click a registered job to expand its controls and password form inside the same card. Only one job is expanded at a time. Clicking it again closes the form and clears the unsaved password. Automatic polling preserves the open form, input and focus.
- An empty password preserves the existing archive password. Password submission preserves that job's saved extraction setting; it does not apply the toolbar default retroactively. Password values are never stored by the extension, returned from the server, or restored into the form. Password entry is disabled when extraction is off or the job cannot be edited.
- Progress refreshes every 5 seconds while jobs are active and every 15 seconds when idle. Requests do not overlap; failures back off to 60 seconds. Refreshing preserves the selected job's password input and focus.
- With the popup closed, the `alarms` permission enables approximately once-per-minute checks only while work remains active. Network failures back off up to 5 minutes. Newly password-required jobs trigger one notification per waiting episode, subject to Chrome/OS notification settings.
- **Clear completed** beside Refresh removes completed job records after confirmation. It does not delete downloaded files from the NAS.
- **Pause**, **Resume** and **Delete** are hidden until the file is clicked. They appear above the password field in that file's card. Pausing retains partial downloads for resumption. While the server reports `stopping`, resume/delete stay locked; wait until the worker exits. Extraction/publication cannot be interrupted here. Completed jobs show **Delete record**, which keeps NAS output files.
- Deleting an unfinished stopped job confirms removal of its temporary files as well as its record. Deleting a completed job removes its record only and keeps published NAS output. Server-side cleanup failure handling requires the updated server; the extension preserves the job on API errors. No filesystem path is supplied by the extension.

## Verification limits

The Buzzheavier live page inspected on 2026-09-21 uses `a.download-btn[hx-get]` and `a.copy[onclick]` targeting the same `/FILE_ID/download?t=...` endpoint. Its public script reads `HX-Redirect`; clicking Download File reached the file host in Chrome, where this test browser reported `ERR_BLOCKED_BY_CLIENT`. Full installed-extension-to-NAS transfer has not been verified. Automated tests cover the observed control shapes, signed-link validation, click cancellation, duplicate clicks, login errors, restricted worker messages, polling/backoff, Enter submission, password-input preservation, processing options, and completed-history clearing. Popup interaction tests use a mocked DOM, not an installed Chrome extension. Other providers' live DOM variants may require adapter updates.
