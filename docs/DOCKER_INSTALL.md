# NASDrop Docker installation guide

NASDrop publishes one multi-platform image for `linux/amd64` and `linux/arm64`. Docker automatically selects the correct architecture. The image contains the same server and web application as the Synology package.

## Requirements

- Docker Engine 24 or later with Docker Compose v2, Docker Desktop, or Synology Container Manager
- Two persistent host folders: one for NASDrop configuration and one for downloads
- TCP port `8791`, or another unused host port
- At least 1 GB of temporary memory for large archive operations; more may be required for unusually large archives

The official image is:

```text
ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-2
```

Use the numbered tag for reproducible installations. Use `latest` only when you intentionally want the newest release during updates.

## Install with Docker Compose

Create an empty `nasdrop` directory. Download [`docker/compose.release.yaml`](../docker/compose.release.yaml) and save it as `compose.yaml`; this installation file pins the numbered image tag and contains no local `build:` block. Also copy [`docker/compose.env.example`](../docker/compose.env.example) beside it as `.env`, then edit the values:

```dotenv
PUID=1000
PGID=1000
TZ=Asia/Seoul
NASDROP_CONFIG_DIR=./nasdrop-config
NASDROP_DOWNLOAD_DIR=./downloads
NASDROP_PORT=8791
NASDROP_BIND_ADDRESS=0.0.0.0
# Keep false unless NASDrop is reachable only through a trusted local reverse proxy.
NASDROP_TRUST_FORWARDED_FOR=false
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

Open `http://SERVER-IP:8791`. On a new `/config` folder, sign in with temporary ID `nasdrop` and temporary password `nasdrop`. NASDrop immediately opens the account form and blocks downloads, folders, settings, inspection, and job APIs until you save a new ID and a password of 10–128 characters. The short temporary password is accepted only for this initial login/current-password check; it cannot be saved as the new password. Existing custom credentials are preserved. If an existing account still verifies as the exact default `nasdrop` / `nasdrop`, every Docker start restores the mandatory-change flag without rotating the credentials. `/downloads` is already the default destination through the container environment. After changing the login, opening **Settings** and selecting `/downloads` once is recommended as a write-access check, but is not required to establish the default.

Check startup state and logs:

```sh
docker compose ps
docker compose logs --tail=100 nasdrop
```

## Synology Container Manager

The Docker image works on both Intel/AMD and ARM Synology models that support Container Manager, even though the native SPK is currently x86_64 only.

1. In File Station, create `/volume1/docker/nasdrop/config` and a download folder such as `/volume1/downloads`.
2. Record the numeric UID and GID of the DSM user that owns the download folder. If SSH is disabled, temporarily enable it under **Control Panel > Terminal & SNMP**, run `id your-dsm-user`, then disable SSH again. Do not assume the example IDs match your NAS. Give that DSM user read/write permission to the download shared folder.
3. Open **Container Manager > Project > Create**.
4. Name the project `nasdrop`, select `/volume1/docker/nasdrop` as its path, and paste the Compose configuration below.
5. Build the project.
6. Open `http://NAS-IP:8791`, sign in with temporary credentials `nasdrop` / `nasdrop`, change both credentials when prompted, and choose `/downloads` under **Settings**.

```yaml
services:
  nasdrop:
    image: ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-2
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

Replace the example `1026:100` IDs with the values from your NAS. The fixed temporary credentials `nasdrop` / `nasdrop` are created when `/config/credentials.json` is absent. An existing exact default account is also marked for mandatory replacement on every Docker start without changing its password; custom credentials are left unchanged.

If the native Synology package already uses port `8791`, change the Docker mapping to `8792:8791` and open `http://NAS-IP:8792`.

## Windows and macOS with Docker Desktop

Create a folder for the project, save the release Compose file as `compose.yaml`, then run these three commands in PowerShell, Windows Terminal, or macOS Terminal. Relative mounts create `nasdrop-config` and `downloads` next to the Compose file.

```powershell
docker compose pull
docker compose up -d
docker compose ps
```

If Docker Desktop cannot mount the selected drive, allow that drive or folder in Docker Desktop's file-sharing settings. Use `http://localhost:8791` on the same computer.

## Install without Compose

Create persistent folders first, then create the account and start the service:

```sh
mkdir -p nasdrop-config downloads
docker pull ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-2
docker run -d --name nasdrop --restart unless-stopped --init \
  --read-only --security-opt no-new-privileges:true \
  --tmpfs /tmp:size=1g,mode=1777 \
  -p 8791:8791 \
  -e PUID=1000 -e PGID=1000 -e TZ=Asia/Seoul \
  -e NAS_PORTAL_NAS_TARGET=/downloads \
  -e NAS_PORTAL_STORAGE_ROOTS=/downloads \
  -v "$PWD/nasdrop-config:/config" \
  -v "$PWD/downloads:/downloads" \
  ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-2
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

After an update, selecting the default download folder again in Settings is recommended so NASDrop rechecks write access. The `/config` and `/downloads` mounts survive container replacement.

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

In Synology Container Manager, open the running `nasdrop` container's **Terminal**, create a shell, run `nasdrop-account set owner`, and then restart the container from the **Action** menu.

## Offline image installation

NASDrop does not attach Docker TAR files to GitHub releases. On a connected computer, pull the required architecture and create the transfer file yourself:

```sh
docker pull --platform linux/amd64 ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-2
docker save -o nasdrop-0.9.26-2-amd64.tar ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-2
```

For an ARM64 host, replace `linux/amd64` and `amd64.tar` with `linux/arm64` and `arm64.tar`. Copy the TAR and the installation files to the offline host, then load and start them:

```sh
docker load -i nasdrop-0.9.26-2-amd64.tar
docker compose up -d
```

Use the ARM64 filename when applicable. Skip `docker compose pull` on the offline host; the loaded image retains the numbered GHCR tag used by `compose.yaml`. A normal connected installation should pull from GHCR so Docker selects the architecture automatically.

## Troubleshooting

**The web page does not open:** run `docker compose ps` and `docker compose logs --tail=100 nasdrop`. Check that the host port is unused and allowed by the host firewall.

**The download folder is locked or not writable:** verify the bind-mount path, `PUID`, `PGID`, and host permissions. Test as the same numeric account used by the service, rather than as container root:

```sh
docker compose exec nasdrop sh -c 'gosu "$PUID:$PGID" sh -c "id; test -w /downloads && echo writable || { echo not-writable; exit 1; }"'
```

**The container restarts repeatedly:** inspect the logs and confirm that `/config` is writable by `PUID:PGID`. Do not remove the read-only or no-new-privileges settings merely to hide a mount-permission error.

**The wrong architecture is reported:** `docker image inspect ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-2 --format '{{.Architecture}}'` shows the local image architecture. Remove a manually imported image for the wrong CPU and pull the multi-platform GHCR tag again.

**Port 8791 is occupied:** set `NASDROP_PORT=8792` in `.env`, or change the mapping to `8792:8791`.

## Network security

Port `8791` serves plain HTTP. Keep it on a trusted local network. For remote access, use an HTTPS reverse proxy or a private VPN and do not forward port `8791` directly from the internet. Set `NASDROP_TRUST_FORWARDED_FOR=true` only when requests can reach NASDrop exclusively through a trusted local reverse proxy.
