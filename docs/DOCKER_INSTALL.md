# NASDrop Docker installation guide

NASDrop publishes one multi-platform image for `linux/amd64` and `linux/arm64`. Docker automatically selects the correct architecture. The image contains the same server and web application as the Synology package.

## Requirements

- Docker Engine 24 or later with Docker Compose v2, Docker Desktop, or Synology Container Manager
- Two persistent host folders: one for NASDrop configuration and one for downloads
- TCP port `8791`, or another unused host port
- At least 1 GB of temporary memory for large archive operations; more may be required for unusually large archives

The official image is:

```text
ghcr.io/littleweirdlab0514-web/nasdrop:0.9.23-3
```

Use the numbered tag for reproducible installations. Use `latest` only when you intentionally want the newest release during updates.

## Install with Docker Compose

Create an empty `nasdrop` directory and save the repository's `compose.yaml` in it. Create a `.env` file beside it:

```dotenv
PUID=1000
PGID=1000
TZ=Asia/Seoul
NASDROP_CONFIG_DIR=./nasdrop-config
NASDROP_DOWNLOAD_DIR=./downloads
NASDROP_PORT=8791
NASDROP_BIND_ADDRESS=0.0.0.0
```

On Linux, find the account IDs that own the download folder:

```sh
id your-user
```

Set `PUID` to the reported `uid` and `PGID` to the reported `gid`. Ensure that account can write to both host folders. NASDrop never recursively changes permissions on a download folder.

Pull the image and start NASDrop:

```sh
docker compose pull
docker compose up -d
```

Open `http://SERVER-IP:8791`. On a new `/config` folder, sign in with temporary ID `nasdrop` and temporary password `nasdrop`. NASDrop immediately opens the account form and blocks downloads, folders, settings, and job APIs until you save a new ID and a password of 10–128 characters. The short temporary password is accepted only for this initial login/current-password check; it cannot be saved as the new password. Existing `credentials.json` files are never overwritten. After changing the login, select `/downloads` as the default destination so NASDrop can verify that the mounted folder is writable.

Check startup state and logs:

```sh
docker compose ps
docker compose logs --tail=100 nasdrop
```

## Synology Container Manager

The Docker image works on both Intel/AMD and ARM Synology models that support Container Manager, even though the native SPK is currently x86_64 only.

1. In File Station, create `/volume1/docker/nasdrop/config` and a download folder such as `/volume1/downloads`.
2. If SSH is enabled, run `id your-dsm-user` and record its numeric UID and GID. Give that DSM user read/write permission to the download shared folder.
3. Open **Container Manager > Project > Create**.
4. Name the project `nasdrop`, select `/volume1/docker/nasdrop` as its path, and paste the Compose configuration below.
5. Build the project.
6. Open `http://NAS-IP:8791`, sign in with temporary credentials `nasdrop` / `nasdrop`, change both credentials when prompted, and choose `/downloads` under **Settings**.

```yaml
services:
  nasdrop:
    image: ghcr.io/littleweirdlab0514-web/nasdrop:0.9.23-3
    container_name: nasdrop
    restart: unless-stopped
    init: true
    stop_grace_period: 60s
    read_only: true
    ports:
      - "8791:8791"
    environment:
      PUID: "1026"
      PGID: "100"
      TZ: "Asia/Seoul"
      NAS_PORTAL_NAS_TARGET: /downloads
      NAS_PORTAL_STORAGE_ROOTS: /downloads
    volumes:
      - /volume1/docker/nasdrop/config:/config
      - /volume1/downloads:/downloads
    tmpfs:
      - /tmp:size=1g,mode=1777
    security_opt:
      - no-new-privileges:true
```

Replace the example `1026:100` IDs with the values from your NAS. The temporary credentials are created only when `/config/credentials.json` is absent.

If the native Synology package already uses port `8791`, change the Docker mapping to `8792:8791` and open `http://NAS-IP:8792`.

## Windows and macOS with Docker Desktop

Create a folder for the project, save `compose.yaml`, then run the same three Compose commands in PowerShell, Windows Terminal, or macOS Terminal. Relative mounts create `nasdrop-config` and `downloads` next to the Compose file.

```powershell
docker compose pull
docker compose up -d
```

If Docker Desktop cannot mount the selected drive, allow that drive or folder in Docker Desktop's file-sharing settings. Use `http://localhost:8791` on the same computer.

## Install without Compose

Create persistent folders first, then create the account and start the service:

```sh
mkdir -p nasdrop-config downloads
docker pull ghcr.io/littleweirdlab0514-web/nasdrop:0.9.23-3
docker run -d --name nasdrop --restart unless-stopped --init \
  --read-only --security-opt no-new-privileges:true \
  --tmpfs /tmp:size=1g,mode=1777 \
  -p 8791:8791 \
  -e PUID=1000 -e PGID=1000 -e TZ=Asia/Seoul \
  -e NAS_PORTAL_NAS_TARGET=/downloads \
  -e NAS_PORTAL_STORAGE_ROOTS=/downloads \
  -v "$PWD/nasdrop-config:/config" \
  -v "$PWD/downloads:/downloads" \
  ghcr.io/littleweirdlab0514-web/nasdrop:0.9.23-3
```

## Additional download folders

Every destination must be mounted and listed in `NAS_PORTAL_STORAGE_ROOTS`:

```yaml
environment:
  NAS_PORTAL_NAS_TARGET: /downloads
  NAS_PORTAL_STORAGE_ROOTS: /downloads,/media,/archive
volumes:
  - /srv/downloads:/downloads
  - /srv/media:/media
  - /mnt/archive:/archive
```

Use container paths such as `/media` in NASDrop Settings. Host paths such as `/srv/media` do not exist inside the container.

## Update, back up, and restore

To update to a newer image, change the numbered image tag in `compose.yaml`, then run:

```sh
docker compose pull
docker compose up -d
```

After an update, select the default download folder again in Settings so NASDrop rechecks write access. The `/config` and `/downloads` mounts survive container replacement.

Back up the host configuration folder while the container is stopped:

```sh
docker compose stop
tar -czf nasdrop-config-backup.tgz nasdrop-config
docker compose start
```

Restore by stopping NASDrop, replacing the configuration folder from the backup, confirming ownership, and starting it again. Back up the download folder separately if its contents also need protection.

## Reset the login

Run the account command inside the active container, then restart it:

```sh
docker compose exec nasdrop nasdrop-account set owner
docker compose restart nasdrop
```

Changing the account invalidates existing sessions.

## Offline image installation

Download the matching release TAR on a connected computer, copy it to the Docker host, and import it:

```sh
docker load -i NASDrop-0.9.23-amd64.tar
```

For an ARM64 host, use `NASDrop-0.9.23-arm64.tar`. Run `docker image ls` after loading and use the loaded image name in `compose.yaml`. Release TARs are optional; a normal connected installation should use GHCR so Docker selects the architecture automatically.

## Troubleshooting

**The web page does not open:** run `docker compose ps` and `docker compose logs --tail=100 nasdrop`. Check that the host port is unused and allowed by the host firewall.

**The download folder is locked or not writable:** verify the bind-mount path, `PUID`, `PGID`, and host permissions. Test from inside the container with `docker compose exec nasdrop sh -c 'id; test -w /downloads && echo writable'`.

**The container restarts repeatedly:** inspect the logs and confirm that `/config` is writable by `PUID:PGID`. Do not remove the read-only or no-new-privileges settings merely to hide a mount-permission error.

**The wrong architecture is reported:** `docker image inspect ghcr.io/littleweirdlab0514-web/nasdrop:0.9.23-3 --format '{{.Architecture}}'` shows the local image architecture. Remove a manually imported image for the wrong CPU and pull the multi-platform GHCR tag again.

**Port 8791 is occupied:** set `NASDROP_PORT=8792` in `.env`, or change the mapping to `8792:8791`.

## Network security

Port `8791` serves plain HTTP. Keep it on a trusted local network. For remote access, use an HTTPS reverse proxy or a private VPN and do not forward port `8791` directly from the internet. Set `NASDROP_TRUST_FORWARDED_FOR=true` only when requests can reach NASDrop exclusively through a trusted local reverse proxy.
