# NASDrop 0.9.26-2 DSM launcher compatibility hotfix

This Synology-only package revision fixes a false signed-out result in the hardened DSM launcher introduced in 0.9.26-1.

## Fix

- DSM authentication now follows Synology's documented contract: a non-empty username from `authenticate.cgi` indicates an authenticated DSM session. The launcher no longer rejects a valid username solely because an undocumented child-process exit status is nonzero on a particular DSM release.
- Username length and control-character validation remain enforced.
- Membership in DSM's `administrators` group remains mandatory.
- Signed-out users still receive no NASDrop handoff, and the short-lived, one-use HMAC handoff design is unchanged.

## Test gate

Install the SPK manually and verify that a signed-in DSM administrator can open NASDrop, a signed-out user is rejected, and a signed-in non-administrator is rejected. Direct browser, Android, and Chrome-extension login continue to use the configured NASDrop ID and password and are unaffected by this launcher-only change.

## Test asset

- File: `nasdrop-0.9.26-2-x86_64.spk`
- SHA-256: `2CE81A134D90C072B4CD00DA76A1B9FE7775D87C668AB29D3BC70E416BDEB4F7`
