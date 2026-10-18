# NASDrop 0.9.29-2 — split-archive waiting and DSM proxy launcher

NASDrop now keeps an unmistakably numbered split-archive volume in the private work queue even when that part is registered through its own supported-service link. Later parts join the same set only when the provider, destination, and normalized filename family match exactly.

When the currently available contiguous volumes look complete but 7-Zip asks for a later volume, NASDrop returns every member to the waiting state and preserves the verified temporary files. Registering the next part automatically triggers another extraction attempt. Only the completed extracted result is published; partial RAR, ZIP, or 7-Zip volumes are not copied to the destination.

The existing layouts remain supported: `.7z.001`, `.zip.001`, `.rar.001`, classic split ZIP (`.z01` plus `.zip`), modern RAR (`.part01.rar`), and legacy RAR (`.rar` plus `.r00`). Duplicate volume numbers remain isolated because their membership is ambiguous.

The NASDrop dashboard now shows active split sets in a dedicated waiting board. Ordinary single archives still extract immediately. The settings page also presents Buy Me a Coffee's official yellow website button as the sole support destination; the full banner is a keyboard-accessible link to the project page.

Synology users can now set a complete HTTPS reverse-proxy address for the DSM desktop icon, such as `https://nasdrop.example.com/`. That address takes priority over the adaptive DSM-hostname and port calculation; clearing it restores the existing behavior. NASDrop stores the normalized address in the package configuration and rewrites the static DSM launcher without adding any authentication material.

Chrome companion 0.5.11 is published separately for developer-mode installation. It retains 0.5.10's ordered, duplicate-safe GoFile click queue and capability-gated asynchronous enqueue, shortens the connected-site guidance, and adds the bundled official Buy Me a Coffee button. The extension does not send credentials, tokens, job details, or provider links to the support site.

Automated validation passed 253 Python tests with one skip and 83 JavaScript/Chrome tests. The x86_64 Synology package and Chrome ZIP are supplied with SHA-256 checksum files. Tagging this release starts the immutable amd64/arm64 Docker candidate workflow; stable Docker tags remain on the previously promoted digest until the separate promotion gate is completed.
