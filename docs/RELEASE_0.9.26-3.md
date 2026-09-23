# NASDrop 0.9.26-3 DSM launcher login fallback

This Synology package revision restores the DSM icon flow for existing installations whose DSM browser session cannot be validated through Synology's cookie-based `authenticate.cgi`.

## Change

- When DSM authentication succeeds, the existing administrator-only, short-lived, one-use handoff remains in place.
- If DSM authentication yields no usable username and a NASDrop account is already configured, the icon opens the tokenless NASDrop login page. The user signs in with the NASDrop ID and password; no DSM identity or session is inferred.
- An unconfigured installation still requires DSM administrator authentication for initial account creation. This build does not weaken first-run account ownership checks.
- Direct browser, Android, Chrome-extension, and Docker authentication are unchanged.

## Test gate

Install the SPK manually. On an installation with a configured NASDrop account, open the DSM icon from a browser that shows DSM API error 119 and verify it reaches the NASDrop login page. Sign in with the configured NASDrop credentials. Also verify that an unconfigured installation cannot create its first account through this fallback.

## Test asset

- File: `nasdrop-0.9.26-3-x86_64.spk`
- SHA-256: `09EBE17F6EA9533F7654234CBFAB2AD93489AB7BDB9DEEA2D8291BD08E92F74D`
