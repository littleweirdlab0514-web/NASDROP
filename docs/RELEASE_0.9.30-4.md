# NASDrop 0.9.30-4 — ApexDrive compatibility candidate

This candidate fixes valid ApexDrive transfers that Chrome and Synology Download Station can download directly but NASDrop previously rejected.

- Treats the complete ApexDrive `verify` value as opaque instead of interpreting a timestamp or signature structure locally.
- Uses the delivery response `Content-Disposition` filename as authoritative even when it differs from the display-only `fn` query value.
- Keeps the exact delivery host/path/query contract, public-address DNS pinning, bounded metadata checks, single-connection transfer, and private in-memory credential handling.
- Updates the capability-gated Chrome companion to 0.5.15 with the matching opaque-value forwarding rule.
- Verified on PC Docker with successful metadata inspection and a 10,940,416-byte live transfer before the test job was paused; the signed URL was absent from persisted configuration, public jobs, and container logs.

The candidate also includes the GoFile DNS compatibility, destination-capacity protection, X-Share retry/reauthentication, split-archive waiting board, reverse-proxy launcher setting, and Buy Me a Coffee integration from the preceding 0.9.30 line.
