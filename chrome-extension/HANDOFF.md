# Browser-resolved provider handoff

Status: extension-side classification and forwarding are implemented. Use a [NASDrop](https://github.com/littleweirdlab0514-web/NASDROP) server whose `/api/status` advertises the selected provider in `browser_handoff_providers`; AkiraBox/VikingFile support began in 0.9.19, while Send.now requires the newer `sendnow` capability. End-to-end Send.now receipt on a real NAS remains unverified. This developer-mode extension is not an official Chrome Web Store release and does not install or update the server. Installation/update steps are in [README.md](README.md).

## Browser observations

- AkiraBox share: `https://akirabox.to/SHARE_ID/file`. Once prepared, `a#download.download-button[aria-disabled="false"]` contains `https://akirabox.com/download/OPAQUE_TOKEN/FILENAME?expiration=UNIX_TIME&signature=HEX_SIGNATURE`.
- Viking share: `https://vik1ngfile.site/f/SHARE_ID`. After preparation, `a#download-link.button` contains `https://vikingfile.com/d/OPAQUE_ID/FILENAME`.
- Send.now shares use `https://send.now/SHARE_ID` and the current `https://send.now/d/SHARE_ID` form. Live Chrome inspection of `/d/1pBGp` showed a **Security verification** page whose same-origin POST control is `input[type="submit"][name="download_a"]` with the visible value **CONTINUE**. The extension leaves that control and the challenge untouched. After Continue, the browser lands on `https://send.now/`, retains the `/d/SHARE_ID` page in `document.referrer`, and displays the actual file action as `button#downloadbtn` with no href. Clicking that final button starts a Chrome download from a rotating `usercdn.com` host. Only that final click arms a one-minute same-tab watch; unrelated downloads are ignored.
- The user reports AkiraBox opens advertisements on the first two clicks and downloads on the third. This is not treated as a reliable protocol or a counter to automate. The extension matches the prepared official anchor and validates its actual href at click time. If an accepted URL is already present, interception may occur on the first click. Advertisement popup timing is not proof that an address is a file.
- The inspected browser session produced both links without manual CAPTCHA interaction. Other sessions may require the user to complete a challenge. The extension does not solve challenges or generate links before the site is ready.

AkiraBox and VikingFile retain their provider-specific host/path checks. Send.now file delivery hosts may rotate, so the extension deliberately does not pin a single observed CDN hostname. It requires the exact final `button#downloadbtn`, a canonical Send.now share referrer, HTTPS on the default port, no credentials or fragment, a non-local DNS hostname and a resulting same-tab download with a root Send.now referrer. The matching browser download is cancelled and erased from Chrome history before handoff. The NAS server must independently enforce public-address, redirect and file-response validation. These checks identify a candidate URL, not its actual content or ownership. Opaque URL tokens cannot establish that a file matches a share ID.

Chrome's `downloads.onCreated` item does not expose the originating tab ID. Version 0.5.5 therefore permits only one pending Send.now final-button handoff across the browser. The short-lived pending record is held in `chrome.storage.session` so a suspended Manifest V3 service worker does not lose it. A second tab is rejected while the first is waiting, and only a download with the expected root Send.now referrer and a structurally safe final HTTPS URL can consume that pending handoff.

GigaFile download keys use a separate capability and request field. When `/api/status` reports `gigafile_download_key: true`, a protected official `download(file, true, false)` control may register through `POST /api/enqueue` with the original GigaFile URL and a separate `download_key` field. Protected and unprotected GigaFile registrations do not use the inspection-then-start sequence. The key is never appended to the URL. A job in `download_key_required` accepts a retry through `POST /api/jobs/<job-id>/download-key`. Older servers are not intercepted for protected GigaFile clicks.

## Agreed server contract

`GET /api/status` must advertise `browser_handoff_providers`. If absent, the extension displays an unsupported-server notice and does not call inspect/start for these providers. Capability advertisement is not evidence of a completed live-NAS transfer.

`POST /api/inspect` retains Bearer authentication and accepts:

```json
{
  "url": "https://akirabox.to/SHARE_ID/file",
  "resolved_url": "https://akirabox.com/download/OPAQUE_TOKEN/FILENAME?expiration=...&signature=...",
  "provider": "akirabox"
}
```

Send.now uses the same shape with its original `send.now` share URL, the final URL from the user-triggered Chrome download in `resolved_url`, and `"provider":"sendnow"`.

The server independently derives the provider from the original share URL; the client field is only a hint and must agree. Response remains `{file:{url,name,size,provider,inspection_id,...}}` with the **share** URL, not the issued URL. `/api/start` uses the existing cached inspection contract. An expired/missing inspection must not silently re-fetch an unsupported share page or publish an unvalidated file.

## Live observations and remaining NAS verification

Cookie-free desktop probes observed AkiraBox redirecting to `us1.akirabox.com` with a valid final file response, and Viking redirecting to its specific R2 storage host. The Viking final signed URL rejected HEAD with 403 but returned 206 to a minimal Range GET. NASDrop 0.9.19 handles only its explicitly allowed destinations; the extension still forwards the initial official URL and needs no R2/regional-host permissions. Browser cookies are not transferred, and no CAPTCHA solving or advertisement-click automation is included.

- Verify cookie-free access from the NAS address, bodyless HEAD or bounded Range 0-0, actual filename/size, Range 206/resume behavior, and expiration responses.
- Reject HTML/ad/error responses. Validate every redirect destination against observed provider-specific hosts and public-address restrictions; never add arbitrary host or URL support.
- Prefer the final `Content-Disposition` filename per repository rules; page labels and URL filenames are not authoritative.
- Determine what evidence can bind an opaque issued URL to the source share and file metadata. Do not claim cryptographic verification of provider signatures.
- Keep issued links out of logs, jobs' public source, API responses and browser persistence. Only use the restricted private job secret store where needed.
- If cookies or client-IP binding prevent NAS access, report the restriction. Do not clone browser challenge cookies.

The extension tests cover classification, mock click interception, challenge/Continue non-interaction, the exact final Send.now download button, scoped Chrome-download capture, unauthorized messages, independent capability gating and the request contract. They do not demonstrate a completed AkiraBox, VikingFile or Send.now download on a NAS.
