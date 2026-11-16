# NASDrop 0.9.30-2 — storage capacity candidate

- Shows free and total capacity for the filesystem containing the selected download folder.
- Checks space before starting a download, including temporary parts, final-file assembly, a safety reserve, and older active jobs on the same filesystem.
- Reports `insufficient_storage` when preflight fails or the operating system reports a full disk, allowing web and Android clients to show a clear recovery message.
- Retains the X-Share retry and reauthentication workflow from 0.9.30-1.

This is a Synology test candidate. Install it manually on DSM, confirm the capacity shown for the selected volume, and verify that a job can be resumed after freeing space.
