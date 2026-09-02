# Security Policy

## Supported versions

Security fixes are provided for the latest NASDrop release only. Before reporting a problem, reproduce it with the newest SPK from the [releases page](https://github.com/littleweirdlab0514-web/NASDROP/releases/latest) when it is safe to do so.

## Reporting a vulnerability

Please do not disclose vulnerabilities, account credentials, session tokens, private download URLs, NAS addresses, logs containing secrets, or exploit details in a public issue.

Use GitHub's [private vulnerability reporting form](https://github.com/littleweirdlab0514-web/NASDROP/security/advisories/new). Include:

- the affected NASDrop version and DSM version;
- the affected endpoint or component;
- reproduction steps and the expected security impact;
- relevant logs or screenshots with unrelated personal data removed; and
- any suggested mitigation, if known.

You should receive an acknowledgement within seven days. Please allow reasonable time for investigation and a coordinated fix before public disclosure.

## Non-security issues

Installation questions, unsupported NAS architectures, provider website changes, rate limits, and ordinary bugs belong in the public [issue tracker](https://github.com/littleweirdlab0514-web/NASDROP/issues) after removing account credentials, session tokens, private URLs, and device-specific information.

## Deployment note

NASDrop is distributed as an unofficial Synology DSM package and a Docker image. Keep port `8791` private, use DSM Reverse Proxy or another trusted HTTPS reverse proxy for internet access, choose a unique strong password, and consider an additional authentication layer for public deployments. Docker deployments should use a non-root `PUID:PGID`, mount only required storage folders, and must not use privileged mode.
