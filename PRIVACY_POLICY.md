# NASDrop Android Privacy Policy

Effective date: September 4, 2026

NASDrop Android is provided by LittleWeirdLab as a companion app for a user-controlled NASDrop Server. This policy explains how the Android app handles information.

## Self-hosted NASDrop data

NASDrop Android connects directly to the NASDrop Server address entered by the user. LittleWeirdLab does not operate that server and does not receive the server address, login credentials, download links, destination paths, archive passwords, job details, or downloaded files.

The app stores the configured server address, user name, destination preference, and a time-limited session token locally on the device so it can reconnect to the selected NASDrop Server. The server password is sent only to the configured server during sign-in and is not retained by the Android app. Archive passwords, when supplied for a download job, are sent to the configured server for that job and are not sent to LittleWeirdLab.

Users are responsible for operating and securing their NASDrop Server. HTTPS is recommended, especially when connecting over the internet. If a user deliberately configures an HTTP address, traffic to that server is not encrypted in transit.

## Advertising

The free version displays ads using the Google Mobile Ads SDK. According to Google's SDK disclosure, the SDK may automatically collect and share:

- an IP address, which may be used to estimate approximate location;
- app interactions, such as app launches, taps, and ad video views;
- diagnostic information about app and SDK performance; and
- device or account identifiers, including the Android advertising ID and app set ID.

Google states that this information is used for advertising, analytics, and fraud prevention and is encrypted in transit. Depending on the user's location, NASDrop presents Google's consent or privacy-options interface before requesting ads. Users can also reset or delete their advertising ID in Android settings.

For details about Google's handling of this information, see the Google Privacy Policy and Google Mobile Ads SDK data disclosure.

## In-app purchases

NASDrop offers an optional one-time purchase to remove ads. Purchases are processed by Google Play. LittleWeirdLab does not receive or store payment-card or bank-account details. The app receives purchase status and related identifiers from Google Play only as needed to provide and restore the purchased feature.

## Data retention and deletion

Local app data can be removed by signing out where available, clearing the app's storage in Android settings, or uninstalling the app. Data stored on a self-hosted NASDrop Server is controlled by that server's owner and must be managed or deleted there.

Advertising and purchase information handled by Google is retained and deleted according to Google's policies and the controls available in the user's Google account and Android settings.

## Children

NASDrop is a technical utility intended for adults who operate or administer a compatible self-hosted server. It is not designed for or directed to children.

## Changes

This policy may be updated when the app, its SDKs, or legal requirements change. The effective date at the top of this page will be revised when material changes are made.

## Contact

Questions about this policy may be submitted through the NASDrop GitHub issue tracker:

https://github.com/littleweirdlab0514-web/NASDROP/issues

## Related links

- NASDrop Server source and installation: https://github.com/littleweirdlab0514-web/NASDROP
- Google Privacy Policy: https://policies.google.com/privacy
- Google Mobile Ads SDK data disclosure: https://developers.google.com/admob/android/privacy/play-data-disclosure
