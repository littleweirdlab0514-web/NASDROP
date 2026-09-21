# Chrome Web Store Listing — NASDrop for Chrome

> Last Updated: 2026-09-21

## Store Listing

**Extension Name**

NASDrop for Chrome

**Short Description**

Send supported file-host downloads to your own NASDrop server and manage their progress from Chrome.

**Detailed Description**

NASDrop for Chrome sends supported file-host downloads to a NASDrop server that you operate.

FEATURES
• Recognizes official download controls on supported GigaFile, GoFile, Pixeldrain, Buzzheavier, AkiraBox and VikingFile pages
• Sends downloads to your NAS instead of saving them through the browser
• Shows current progress and lets you pause, resume or delete individual jobs
• Supports automatic archive extraction and optional archive passwords
• Supports English, Korean, Simplified Chinese and Japanese, with English as the fallback

HOW TO USE
1. Install and configure NASDrop Server on your own NAS or Docker host.
2. Open the extension and sign in with your NASDrop server address and account.
3. Allow access to that server address when Chrome asks.
4. Open a supported share page and click its official download button.
5. Open the extension to monitor or control the job.

PRIVACY
The extension sends credentials, download links and job commands only to the NASDrop server address you choose. The developer does not operate an intermediary download service and does not receive this information. Passwords are not retained by the extension. The extension contains no advertising or analytics.

PERMISSIONS
Access to supported provider pages is used only to recognize their official download controls. Access to your NASDrop server is requested interactively for the server address you enter. Notifications report password-required jobs, download submissions and errors. Storage is used for the server address, access token, username, language and extraction preference.

SUPPORT
Report sanitized issues at https://github.com/littleweirdlab0514-web/NASDROP/issues or email littleweirdlab0514@gmail.com. Never include passwords, session tokens, private download links or an unredacted NAS address in a public report.

Version 0.5.1 — Adds inline per-file controls and archive-password entry while preserving automatic progress updates.

**Category**

Productivity

**Single Purpose**

Sends supported file-host downloads to a user-operated NASDrop server and manages those download jobs.

**Primary Language**

English

## Graphics & Assets

| Asset | Dimensions | Status | Filename |
|-------|-----------:|--------|----------|
| Store Icon | 128×128 PNG | ⬜ Not created | Use `chrome-extension/icons/nasdrop-256.png` as the source |
| Screenshot 1 | 1280×800 or 640×400 | ⬜ Not created | Popup: connected job list with one expanded job |
| Screenshot 2 | 1280×800 or 640×400 | ⬜ Not created | Supported provider page with NASDrop result notice |
| Screenshot 3 | 1280×800 or 640×400 | ⬜ Not created | Login and first-host-permission flow |
| Small Promo Tile | 440×280 | ⬜ Not created | |
| Marquee Promo Tile | 1400×560 | ⬜ Not created | |

### Screenshot Notes

- Use only synthetic filenames and a private test NAS address that has been fully redacted.
- Show the current 0.5.1 popup, including collapsed controls by default and one expanded password form.
- Capture each image at an accepted exact size; do not scale a mobile screenshot into the store frame.
- Do not show credentials, session tokens, signed provider URLs, cookies or real private hostnames.

## Permissions Justification

| Permission | Type | Justification |
|------------|------|---------------|
| `alarms` | permissions | Checks active jobs at a low frequency while the popup is closed so a password-required notification can be shown without continuous polling. |
| `activeTab` | permissions | Reads the currently active supported share URL only after the user opens the extension or chooses the current-tab action. |
| `contextMenus` | permissions | Adds an explicit user-invoked command for sending a supported link to NASDrop. |
| `notifications` | permissions | Alerts the user when an archive is waiting for a password and reports download submissions or errors. |
| `storage` | permissions | Stores the chosen NASDrop address, access token, username, language and extraction preference locally. Passwords and signed handoff URLs are not stored. |
| `http://*/*` | optional_host_permissions | Allows the user to grant access at sign-in to a self-hosted NASDrop server on a private HTTP address. The extension requests only the entered server origin at runtime. |
| `https://*/*` | optional_host_permissions | Allows the user to grant access at sign-in to a self-hosted NASDrop server on an arbitrary HTTPS hostname. The extension requests only the entered server origin at runtime. |
| Listed GigaFile, GoFile, Pixeldrain, Buzzheavier, AkiraBox and VikingFile URL patterns | content script matches | Detects only the supported sites' official download controls and forwards a user-clicked download to the user's NASDrop server. |

## Privacy & Data Use

### Data Collection

**Does the extension collect user data?** Yes. It handles limited data needed for the requested feature and transmits it only to the NASDrop server selected and operated by the user. The developer does not receive it.

| Data Type | Collected? | Transmitted Off-Device? | Purpose | Shared with Third Parties? |
|-----------|------------|-------------------------|---------|----------------------------|
| Personally identifiable info | Limited | To the user's NASDrop server | Stores and submits the NASDrop username used by that server | No |
| Health info | No | No | Not used | No |
| Financial info | No | No | Not used | No |
| Authentication info | Yes | To the user's NASDrop server | Signs in and stores the returned access token locally; the password is not retained | No |
| Personal communications | No | No | Not used | No |
| Location | No | No | Not used | No |
| Web history | Limited | To the user's NASDrop server after an explicit download action | Submits the selected supported share URL | No |
| User activity | Limited | To the user's NASDrop server | Sends explicit pause, resume, delete and settings commands | No |
| Website content | Limited | To the user's NASDrop server | Sends provider download metadata or a short-lived signed link required for the selected download | No |

### Data Use Certification

- [x] Data is NOT sold to third parties
- [x] Data is NOT used for purposes unrelated to the extension's core functionality
- [x] Data is NOT used for creditworthiness or lending purposes

## Privacy Policy

**Privacy Policy URL**

https://github.com/littleweirdlab0514-web/NASDROP/blob/main/chrome-extension/PRIVACY.md

The policy is maintained in `chrome-extension/PRIVACY.md` on the public `main` branch. Verify the URL in a signed-out browser before submission.

## Distribution

**Visibility**: Public
**Regions**: All regions, subject to Chrome Web Store availability

## Developer Info

**Publisher Name**

LittleWeirdLab

**Contact Email**

littleweirdlab0514@gmail.com

**Support URL / Email**

https://github.com/littleweirdlab0514-web/NASDROP/issues

**Homepage URL**

https://github.com/littleweirdlab0514-web/NASDROP

## Version History

| Version | Date | Changes | Status |
|---------|------|---------|--------|
| 0.5.1 | 2026-09-21 | Inline per-file controls, archive-password entry, polling preservation and four-language UI | Draft |

## Review Notes

### Submission Readiness

- [x] Manifest V3 and extension version 0.5.1
- [x] English default with Korean, Simplified Chinese and Japanese locales
- [x] Automated Chrome extension tests pass
- [x] Public GitHub prerelease contains `NASDrop-Chrome-0.5.1.zip`
- [ ] Publish the Chrome-specific privacy policy on the public default branch
- [ ] Create the exact 128×128 store icon
- [ ] Capture at least one exact-size store screenshot with synthetic/redacted data
- [ ] Complete an installed-extension run in Chrome with DevTools MCP after restarting Codex and enabling Chrome remote debugging
- [ ] Complete live NAS end-to-end checks for Buzzheavier, AkiraBox and VikingFile
- [ ] Verify the publisher name and contact email in the Chrome Web Store developer account
- [ ] Prepare reviewer instructions and a safe reviewer-accessible NASDrop test environment if Google requests credentials

### Known Issues / Limitations

- A running user-operated NASDrop server is required; the extension is not a standalone downloader.
- AkiraBox and VikingFile require NASDrop Server 0.9.19 or later and depend on third-party page behavior that may change.
- The first connection requests host access for the entered NASDrop origin. After approval, the popup closes and the user may need to reopen it and sign in again.
- The optional host-permission patterns are broad because a self-hosted server can use any private IP or hostname, but the extension requests only the origin entered by the user.
- The current public distribution is a GitHub prerelease for developer-mode installation, not yet a Chrome Web Store listing.

### Rejection History

None.
