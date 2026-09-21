# Experimental browser handoff — 0.9.19

Install the local 0.9.19-1 SPK and compatible Chrome extension 0.4.2 or later. Existing 0.4.2 does not need replacement.
Refresh the extension connection after updating the NAS.
Open the original AkiraBox or VikingFile share page and wait for its official Download button to become ready.
Use the extension interception/forwarding flow on that official button, not an advertisement.
The extension's Auto extract preference applies to newly submitted jobs.

The authenticated status endpoint advertises browser_handoff_providers with akirabox and vikingfile.
POST /api/inspect accepts url (original share), resolved_url (issued direct URL) and provider.
Only the public inspection ID/name/size/share URL are returned. POST /api/start consumes that inspection ID through the existing contract.

The server independently validates exact HTTPS hosts, path formats, credentials, ports and signature expiry.
AkiraBox direct URLs require expiration and signature. VikingFile direct URLs must use vikingfile.com/d/id/filename without a query.
Cross-provider URLs are rejected. Redirect inspection is manual, bounded to three hops and restricted to exact provider hosts.
Observed AkiraBox final host: us1.akirabox.com, with an access query. No wildcard regional hosts are allowed.
Observed VikingFile final host: vikingfile.04b3d96d52475741e6b10f97f0a84a16.r2.cloudflarestorage.com. Other R2 buckets/tenants are not allowed.
Every destination must use HTTPS/443 without credentials or fragments. Redirect loops are rejected before another request.
HEAD is preferred; HTTP 403/405/501 or missing size/range metadata can fall back to Range bytes=0-0 without reading the body.
GET fallback requires HTTP 206 with Content-Range bytes 0-0/total and Content-Length 1. Ignored ranges are rejected immediately.
Positive file size and byte-range support are required. HTML/JSON responses are not treated as files.
The original share page is the Referer; this is not proof of browser activation and does not transfer browser cookies.
Transfers use one connection per job. Multiple jobs may still run together if enabled in NAS settings.
Validated final links are persisted only in private job secret storage and revalidated on resume; expired links require a newly registered job.
Transfers target that final address with redirects disabled. A fresh official link/new job is recommended after upgrading from 0.9.18.

## User verification still required

- Real NAS receipt, pause/resume, original filename, archive extraction and optional password.
- Whether a link is bound to browser cookies, public IP or a separate normal download-button activation.
- Whether the provider changes redirect destinations or signature behavior. Do not broaden the allowlist blindly.
- No full provider download or NAS installation was performed during local implementation.
- If submission fails, report the sanitized NASDrop error, not the signed URL, cookies or passwords.

## Deletion behavior

Stop an active job and wait for its worker to exit before deleting it.
Deletion removes its exact private workspace; failures retain the record for retry.
Symbolic-link workspaces are rejected. Published output is never deleted by history deletion.
For bulk deletion, earlier workspace cleanup may have succeeded before a later failure; all records remain when workspace cleanup fails.
