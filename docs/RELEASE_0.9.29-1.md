# NASDrop 0.9.29-1 — split archive sets

NASDrop now recognizes complete split archive sets returned together by one GigaFile or GoFile multi-file inspection. Each volume is downloaded and verified in its own private workspace. Extraction starts only after every expected volume is present, and only the completed extracted result is published to the selected destination.

Supported naming layouts are `.7z.001`, `.zip.001`, `.rar.001`, classic split ZIP (`.z01` plus `.zip`), modern RAR (`.part01.rar`), and legacy RAR (`.rar` plus `.r00`). Volume numbers must be contiguous and start at the format's first index. Incomplete sets and volumes submitted through unrelated single-link requests are never combined by filename alone; normal single-file handling remains in effect.

The first archive volume owns password retry for the set. Deleting one grouped job safely stops and removes the whole private set so the remaining jobs cannot wait forever. Existing single archives and ordinary files retain their previous behavior.
