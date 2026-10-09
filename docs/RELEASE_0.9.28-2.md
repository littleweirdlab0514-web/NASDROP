# NASDrop 0.9.28-2 — VikingFile OVH delivery

VikingFile now delivers some files through OVH Object Storage instead of its earlier Cloudflare R2 and regional hosts. NASDrop accepts this route while retaining a provider-specific trust boundary.

The server requires a single OVH bucket label, a regional S3 endpoint, VikingFile's pinned AWS V4 signing credential, a credential scope whose region matches the hostname, the S3 service, host-only signed headers, an unsigned payload declaration, a bounded unexpired lifetime, and a 64-character hexadecimal signature. Other OVH tenants, nested or lookalike hosts, cross-region scopes, and non-S3 services remain blocked.

The browser handoff API and Chrome extension permissions are unchanged. Automated redirect tests cover accepted rotation and rejected tenant/scope variants. A live metadata and byte-range inspection of the reported 550,659,711-byte object succeeded without downloading the file body.
