# Browser-resolved provider handoff

Status: extension-side classification and forwarding are implemented. Use [NASDrop](https://github.com/littleweirdlab0514-web/NASDROP) server **0.9.19 or later** for the validated redirect and Range-probe implementation. End-to-end receipt on a real NAS remains unverified. This developer-mode extension is not an official Chrome Web Store release and does not install or update the server. Installation/update steps are in [README.md](README.md).

## Browser observations

- AkiraBox share: `https://akirabox.to/SHARE_ID/file`. Once prepared, `a#download.download-button[aria-disabled="false"]` contains `https://akirabox.com/download/OPAQUE_TOKEN/FILENAME?expiration=UNIX_TIME&signature=HEX_SIGNATURE`.
- Viking share: `https://vik1ngfile.site/f/SHARE_ID`. After preparation, `a#download-link.button` contains `https://vikingfile.com/d/OPAQUE_ID/FILENAME`.
- The user reports AkiraBox opens advertisements on the first two clicks and downloads on the third. This is not treated as a reliable protocol or a counter to automate. The extension matches the prepared official anchor and validates its actual href at click time. If an accepted URL is already present, interception may occur on the first click. Advertisement popup timing is not proof that an address is a file.
- The inspected browser session produced both links without manual CAPTCHA interaction. Other sessions may require the user to complete a challenge. The extension does not solve challenges or generate links before the site is ready.

Exact hosts, HTTPS, default port, expected paths, query fields, expiration and official button identity are required. Userinfo, control characters, path-like filenames, domain lookalikes, arbitrary query fields and unknown controls are rejected. These checks identify a candidate URL, not its actual content or ownership. Opaque URL tokens cannot establish that a file matches a share ID.

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

The server independently derives the provider from the original share URL; the client field is only a hint and must agree. Response remains `{file:{url,name,size,provider,inspection_id,...}}` with the **share** URL, not the issued URL. `/api/start` uses the existing cached inspection contract. An expired/missing inspection must not silently re-fetch an unsupported share page or publish an unvalidated file.

## Live observations and remaining NAS verification

Cookie-free desktop probes observed AkiraBox redirecting to `us1.akirabox.com` with a valid final file response, and Viking redirecting to its specific R2 storage host. The Viking final signed URL rejected HEAD with 403 but returned 206 to a minimal Range GET. NASDrop 0.9.19 handles only its explicitly allowed destinations; the extension still forwards the initial official URL and needs no R2/regional-host permissions. Browser cookies are not transferred, and no CAPTCHA solving or advertisement-click automation is included.

- Verify cookie-free access from the NAS address, bodyless HEAD or bounded Range 0-0, actual filename/size, Range 206/resume behavior, and expiration responses.
- Reject HTML/ad/error responses. Validate every redirect destination against observed provider-specific hosts and public-address restrictions; never add arbitrary host or URL support.
- Prefer the final `Content-Disposition` filename per repository rules; page labels and URL filenames are not authoritative.
- Determine what evidence can bind an opaque issued URL to the source share and file metadata. Do not claim cryptographic verification of provider signatures.
- Keep issued links out of logs, jobs' public source, API responses and browser persistence. Only use the restricted private job secret store where needed.
- If cookies or client-IP binding prevent NAS access, report the restriction. Do not clone browser challenge cookies.

The extension tests cover classification, mock click interception, unauthorized messages, capability gating and the request contract. They do not demonstrate a completed AkiraBox/Viking download on a NAS.
