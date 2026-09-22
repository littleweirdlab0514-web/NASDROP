# NASDrop 0.9.23-2

NASDrop 0.9.23-2 adds the official Docker distribution alongside the Synology package. Both distributions use the same server and web application.

## Downloads

- Synology DSM 7.1 or later on x86_64: `nasdrop-0.9.23-2-x86_64.spk`
- Docker: `ghcr.io/littleweirdlab0514-web/nasdrop:0.9.23-2`
- Offline Docker images: `NASDrop-0.9.23-amd64.tar` and `NASDrop-0.9.23-arm64.tar`

The Docker image supports `linux/amd64` and `linux/arm64`. Docker automatically selects the correct image when pulling from GHCR. See the [Docker installation guide](DOCKER_INSTALL.md) or the [Korean Docker installation guide](DOCKER_INSTALL.ko.md).

## Verification

- Full Python regression suite: 183 tests passed on amd64 and arm64 (one platform-dependent test skipped)
- JavaScript regression suite: 59 tests passed on amd64 and arm64
- Authentication, mounted storage, file permissions, restart persistence, graceful shutdown, ZipCrypto, AES ZIP, 7z, RAR4, and RAR5 verified
- Live GigaFile encrypted ZIP and GoFile RAR downloads completed and extracted successfully on amd64
- Docker image core and web files matched the canonical Synology server sources

The native Synology SPK remains x86_64 only. ARM Synology systems can use the Docker image through Container Manager when supported by the NAS model.
