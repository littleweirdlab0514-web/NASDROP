# Privacy Policy for NASDrop for Chrome

Last updated: September 22, 2026

NASDrop for Chrome is a companion extension for a NASDrop Server selected and operated by the user. The developer does not operate an intermediary download service and does not receive the user's NAS credentials, download links, files or job history.

## Data handled by the extension

The extension handles only the information needed to connect to the user's NASDrop Server and perform user-requested downloads:

- NASDrop Server address
- NASDrop username and time-limited access token
- Interface language and automatic-extraction preference
- Supported share-page URLs and download metadata selected by the user
- Pause, resume, delete and processing-option commands
- A NASDrop login password, archive password or GigaFile download key while the relevant request is being sent

The extension does not collect health, financial, location or personal-communication data. It contains no advertising, analytics or tracking SDK.

## Local storage

The server address, username, access token, language and extraction preference are stored in Chrome's local extension storage so the extension can reconnect and retain the user's settings. This data is restricted to trusted extension contexts.

Login passwords, archive passwords and GigaFile download keys are not persisted in extension storage. A GigaFile download key is cleared from its page or popup field immediately when it is submitted and is sent in a separate request field, never in the share URL. Login and archive-password fields may remain in the open popup while a request is pending or needs correction; closing the popup discards them. Short-lived provider handoff URLs are not persisted by the extension.

## Data sent to the user's NASDrop Server

When the user signs in, the extension sends the entered username and password to the NASDrop Server address chosen by the user. When the user starts or controls a download, the extension may send the selected share URL, provider download metadata, extraction preference, an archive password supplied by the user, a separately supplied GigaFile download key and job-control commands to that same server.

The server is controlled by the user, not by the extension developer. The user's server may retain its own account, job and file records according to the NASDrop Server configuration and privacy practices chosen by the user.

## Supported provider sites

The extension runs only on the supported GigaFile, GoFile, Pixeldrain, Buzzheavier, AkiraBox, VikingFile and Send.now page patterns listed in its package. It observes the page only to recognize an official download control and respond to the user's click. For providers that issue a short-lived download URL, the extension may request that URL from the provider and send it to the user's NASDrop Server. On Send.now, the verification and Continue steps are left untouched. Only after the user clicks the later final `Download [size]` button does the extension temporarily watch that tab's Chrome download, cancel the matching download, remove its browser download-history entry and send the final HTTPS address to the user's NASDrop Server. Unrelated downloads are ignored. It does not solve or bypass CAPTCHA, Cloudflare or other security-verification steps, and it does not copy browser cookies to the server.

## Chrome permissions

The extension requests access to supported provider pages so it can recognize their official download controls. Access to the user's NASDrop Server is requested interactively for the origin entered during sign-in. Chrome host permissions are origin-based and cannot be limited to a specific port.

Notifications report that an archive requires a password, confirm download submissions and report errors. Alarms are used for low-frequency job checks while work is active. Local storage is used for the settings and access token described above. The downloads permission is used only for the time-limited, user-initiated Send.now handoff; matching local browser downloads are cancelled and their Chrome history entries are removed after NASDrop accepts the handoff attempt.

## Data sharing and sale

The developer does not receive, sell, rent or share the data handled by the extension. The extension does not use data for advertising, profiling, creditworthiness, lending or any purpose unrelated to sending downloads to the user's NASDrop Server and controlling those jobs.

## Security and user choices

Users should prefer HTTPS when connecting over an untrusted network. Plain HTTP should be limited to a trusted private network. The extension does not bypass browser certificate warnings.

The user can sign out to remove the locally stored access token and username. Removing the extension clears its local extension storage. Downloaded files and server-side job records remain on the user's NASDrop Server until the user removes them there or through available job controls.

## Changes to this policy

This policy may be updated if the extension's features or data practices change. The date above identifies the current version. Material data-practice changes will be reflected in the Chrome Web Store disclosure before an updated extension is submitted.

## Contact

Privacy questions may be sent to littleweirdlab0514@gmail.com or submitted through the public NASDrop repository:

https://github.com/littleweirdlab0514-web/NASDROP/issues
