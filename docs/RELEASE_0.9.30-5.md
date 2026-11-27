# NASDrop 0.9.30-5 — VikingFile rotating-domain candidate

VikingFile moved the supplied share from its previous `.site` address to `vik1ngf1le.online`. The canonical `vikingfile.com/f/<id>` address redirects to the same new mirror, whose page retains the official Turnstile-gated generated-download flow.

- Recognizes share hosts only when the complete hostname is the exact `vikingfile`, `vik1ngfile`, or `vik1ngf1le` label followed by one alphabetic TLD.
- Rejects nested domains and unrelated lookalikes.
- Keeps generated links and redirects inside the existing VikingFile direct, regional, pinned Cloudflare R2, and signed OVH Object Storage contracts.
- Adds `vik1ngf1le.online` directly to Chrome 0.5.16.
- Lets future matching mirrors work without another domain-list release: opening the extension on that page temporarily injects only the packaged detector into the active tab.
- Does not request permanent access to every website and does not bypass Turnstile or automate the provider's verification.
