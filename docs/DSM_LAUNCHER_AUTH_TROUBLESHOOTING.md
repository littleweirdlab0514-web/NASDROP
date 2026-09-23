# DSM launcher authentication: error 119 and auto-launch

## Intended behavior

Opening NASDrop from the DSM desktop as a signed-in administrator must create a short-lived NASDrop session without asking for a second NASDrop login. A direct visit to NASDrop still uses its own ID and password. A signed-out or non-administrator DSM request must not obtain a launcher handoff.

The old static launcher embedded a reusable login token in a web-served file. That was unsafe even though it made the DSM icon appear to log in automatically. Never restore a bearer token or equivalent credential to `launcher.html`, `postinst`, or `postupgrade`.

## What the 0.9.26 regression taught us

`authenticate.cgi` can execute successfully yet return a JSON error instead of a username. In this incident the response was `{"error":{"code":119},"success":false}`. Treat 119 as an authentication/session rejection to investigate, not as proof that a DSM desktop is signed out and not as a username. On a DSM setup with CSRF protection, a missing SynoToken is a likely cause; do not assume it is the only possible cause without checking the request context.

The `0.9.26-1` and `0.9.26-2` changes focused on the child process exit status. That did not establish whether stdout was a valid username. The `0.9.26-3` fallback opened the ordinary NASDrop login for configured accounts, which preserved access but broke the DSM-icon auto-launch requirement and hid the authentication failure. A fallback that changes the product contract is not a fix.

## Required diagnosis and implementation sequence

1. Read and classify the actual authenticator response before changing exit-code or fallback logic. A nonempty stdout value is not necessarily an identity. JSON, HTML, multiline text, controls, and malformed usernames must be rejected.
2. Confirm that the launcher CGI receives the DSM request context: an `id` cookie, source address, and the appropriate SynoToken. Report only presence/absence or fixed diagnostic categories. Never print or log cookie, SynoToken, session ID, full CGI environment, or signed handoff values.
3. Try DSM's available `authenticate.cgi` locations with the original request environment. If no valid username is returned, call DSM `login.cgi` with the same cookie and source-address environment to obtain the current session's SynoToken. Validate that its JSON reports success and that the token has a bounded safe format.
4. Retry `authenticate.cgi` with `SynoToken=<token>` in `QUERY_STRING` and `HTTP_X_SYNO_TOKEN`. The token is transient in memory only. Accept only a valid username, then independently verify membership in the DSM `administrators` group.
5. Only after these checks create the 30-second, one-use HMAC handoff. If any check fails, stop with a non-cacheable error and a secret-free category. Do not redirect the DSM icon to a separate NASDrop login and do not infer authentication from a visible DSM page.

If both direct authenticator paths return empty output, 0.9.26-5 also tries a bounded request to the DSM HTTP listener on `127.0.0.1` with the same cookie, first without and then with a SynoToken obtained from `login.cgi`. This is a testable fallback, **not proof** that DSM 7.2+ cannot run the authenticator directly. Disable proxy use and redirects before forwarding the DSM cookie, accept a token only from a successful login response, and retain the administrator-group check. Unit tests cannot establish that this fallback works on a real DSM installation.

Synology's [DSM Developer Guide](https://global.download.synology.com/download/Document/Software/DeveloperGuide/Firmware/DSM/6.0/enu/DSM_Developer_Guide_6_0.pdf) documents supplying SynoToken when CSRF protection is enabled and obtaining it from `login.cgi`. Its [DSM Login Web API Guide](https://kb.synology.com/en-us/DG/DSM_Login_Web_API_Guide/2) also describes SynoToken as a request parameter when that protection is enabled. The exact behavior still needs a real DSM test for each supported DSM line.

## Regression and release gate

- Unit-test cookie-only success, JSON 119, missing/invalid token, token-assisted success, malformed stdout, missing authenticator path, non-admin user, and absence of secrets in diagnostics. Cover loopback port bounds, nested login tokens, successful-login requirement, proxy and redirect blocking, and bounded responses.
- Inspect the generated SPK's `package.tgz` for the authenticated CGI and a tokenless static launcher; source-file inspection alone is insufficient.
- On a real DSM 7.1 and 7.2 installation, test signed-in administrator icon auto-launch, signed-out rejection, non-admin rejection, refresh/new session, and direct NASDrop login separately. Also check a remote-domain DSM session if the issue was reported there.
- Do not mark an auto-launch fix confirmed, promote Docker, or describe the release as verified until the real DSM icon flow passes. If it fails, capture only the safe diagnostic category and investigate the next boundary (cookie/token delivery, authenticator output, administrator lookup, secret-file permission, or handoff exchange) in that order.
