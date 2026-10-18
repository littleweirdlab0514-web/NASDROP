# NASDrop 0.9.29-2 — split archives from separate links

NASDrop now keeps an unmistakably numbered split-archive volume in the private work queue even when that part is registered through its own supported-service link. Later parts join the same set only when the provider, destination, and normalized filename family match exactly.

When the currently available contiguous volumes look complete but 7-Zip asks for a later volume, NASDrop returns every member to the waiting state and preserves the verified temporary files. Registering the next part automatically triggers another extraction attempt. Only the completed extracted result is published; partial RAR, ZIP, or 7-Zip volumes are not copied to the destination.

The existing layouts remain supported: `.7z.001`, `.zip.001`, `.rar.001`, classic split ZIP (`.z01` plus `.zip`), modern RAR (`.part01.rar`), and legacy RAR (`.rar` plus `.r00`). Duplicate volume numbers remain isolated because their membership is ambiguous.

The NASDrop dashboard now shows active split sets in a dedicated waiting board. Ordinary single archives still extract immediately. The settings page also presents the Buy Me a Coffee banner as the sole support destination.
