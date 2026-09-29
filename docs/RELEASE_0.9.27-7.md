# NASDrop 0.9.27-7 X-Share bugfix candidate

NASDrop 0.9.27-7 fixes the first real X-Share browser-to-NAS transfer reaching the job list but failing before receiving file data.

It also tracks AkiraBox's September 2026 download-page change: the server accepts the new four-field first-party signature, validates the newly observed exact European delivery host, and uses the browser-shaped identity required by that delivery edge without copying browser cookies or challenge data.

X-Share's Cloudflare edge returns HTTP 403 to curl's default user agent. The public metadata request already used an explicit NASDrop user agent and succeeded, while the keyed file request omitted it. This revision applies the same product user agent to the one-shot file request and requests an unencoded binary response.

The security boundary is unchanged: the browser still completes Turnstile and the provider wait, NASDrop receives only the same-file one-time URL, DNS remains pinned to validated public addresses, and NASDrop does not forward browser cookies, Referer, Turnstile tokens, or unrelated page data. The keyed URL is used for one full GET without preflight, redirect, retry, or resume.
