# NASDrop Docker 설치 안내서

NASDrop Docker 이미지는 `linux/amd64`와 `linux/arm64`를 함께 제공합니다. GHCR에서 이미지를 받으면 Docker가 호스트 CPU에 맞는 이미지를 자동으로 선택합니다. Docker판의 서버와 웹 화면은 시놀로지 SPK와 동일합니다.

## 준비 사항

- Docker Engine 24 이상과 Docker Compose v2, Docker Desktop 또는 Synology Container Manager
- 설정을 보존할 폴더와 다운로드를 저장할 폴더
- 기본 TCP 포트 `8791`
- 대용량 압축 해제를 위한 임시 메모리 1GB 이상

공식 이미지 주소는 다음과 같습니다.

```text
ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-3
```

버전을 고정하려면 위 태그를 사용합니다. 업데이트할 때마다 최신 버전을 자동으로 받으려는 경우에만 `latest`를 사용하세요.

## Docker Compose로 설치

빈 `nasdrop` 폴더를 만듭니다. [`docker/compose.release.yaml`](../docker/compose.release.yaml)을 내려받아 `compose.yaml`로 저장하세요. 이 설치용 파일은 번호 태그를 고정하며 로컬 `build:` 블록이 없습니다. [`docker/compose.env.example`](../docker/compose.env.example)도 같은 위치에 `.env`라는 이름으로 복사한 뒤 값을 수정합니다.

```dotenv
PUID=1000
PGID=1000
TZ=Asia/Seoul
NASDROP_CONFIG_DIR=./nasdrop-config
NASDROP_DOWNLOAD_DIR=./downloads
NASDROP_PORT=8791
NASDROP_BIND_ADDRESS=0.0.0.0
# 신뢰하는 로컬 리버스 프록시를 통해서만 접속할 때만 true로 변경합니다.
NASDROP_TRUST_FORWARDED_FOR=false
```

리눅스와 시놀로지에서는 다운로드 폴더를 소유한 계정의 숫자 UID와 GID를 확인합니다.

```sh
id 사용자이름
```

출력된 `uid`를 `PUID`, `gid`를 `PGID`에 입력하고 해당 계정에 다운로드 폴더 쓰기 권한을 부여합니다. NASDrop은 마운트한 다운로드 폴더의 권한을 재귀적으로 변경하지 않습니다.

이미지를 받은 뒤 NASDrop을 실행합니다.

```sh
docker compose pull
docker compose up -d
```

`http://서버-IP:8791`을 열고 임시 ID `nasdrop`, 임시 비밀번호 `nasdrop`으로 로그인합니다. 로그인 직후에는 최소한의 계정·상태 조회, 계정 변경, 로그아웃만 가능하며, 새 ID와 10~128자의 새 비밀번호를 저장할 때까지 다운로드·폴더·설정·검사·작업 API가 차단됩니다. 짧은 임시 비밀번호는 최초 로그인과 현재 비밀번호 확인에만 허용되며 새 비밀번호로 다시 저장할 수 없습니다. 기존 사용자 지정 계정은 보존합니다. 기존 설치가 정확히 `nasdrop` / `nasdrop`을 그대로 사용 중이면 시작할 때 비밀번호를 바꾸지 않고 필수 변경 상태만 복구합니다. `/downloads`는 컨테이너 환경변수로 이미 기본 목적지입니다. 계정 변경 후 **설정**에서 `/downloads`를 한 번 선택하는 것은 쓰기 권한 확인을 위한 권장 단계이며, 기본값 지정에 필수는 아닙니다.

상태와 로그는 다음 명령으로 확인합니다.

```sh
docker compose ps
docker compose logs --tail=100 nasdrop
```

## 시놀로지 Container Manager

Docker판은 Container Manager를 지원하는 인텔/AMD 및 ARM 시놀로지에서 사용할 수 있습니다. 현재 네이티브 SPK는 x86_64 전용이지만 Docker판은 ARM64도 지원합니다.

1. File Station에서 `/volume1/docker/nasdrop/config`와 `/volume1/downloads` 같은 다운로드 폴더를 만듭니다.
2. 다운로드 폴더를 소유할 DSM 사용자의 숫자 UID와 GID를 확인합니다. SSH가 꺼져 있으면 **제어판 > 터미널 및 SNMP**에서 잠시 활성화하고 `id DSM사용자이름`을 실행한 뒤 다시 끄세요. 예시 ID가 자신의 NAS와 같다고 가정하면 안 됩니다. 그 DSM 사용자에게 다운로드 공유 폴더 읽기/쓰기 권한을 줍니다.
3. **Container Manager > 프로젝트 > 생성**을 엽니다.
4. 프로젝트 이름은 `nasdrop`, 경로는 `/volume1/docker/nasdrop`으로 지정하고 아래 Compose 내용을 입력합니다.
5. 프로젝트를 생성합니다.
6. `http://NAS-IP:8791`을 열어 `nasdrop` / `nasdrop`으로 로그인하고 안내에 따라 ID와 비밀번호를 변경한 뒤 **설정**에서 `/downloads`를 선택합니다.

```yaml
services:
  nasdrop:
    image: ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-3
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

예시의 `1026:100`은 NAS에서 확인한 실제 UID:GID로 바꿔야 합니다. `/config/credentials.json`이 없으면 고정 임시 계정 `nasdrop` / `nasdrop`을 생성합니다. 기존 계정이 정확히 이 기본값이면 비밀번호를 바꾸지 않고 Docker 시작 때마다 반드시 변경하도록 표시하며, 사용자 지정 계정은 변경하지 않습니다.

시놀로지 SPK가 이미 `8791` 포트를 사용한다면 포트 매핑을 `8792:8791`로 바꾸고 `http://NAS-IP:8792`로 접속하세요.

## Windows와 macOS Docker Desktop

프로젝트 폴더에 `compose.yaml`을 저장하고 PowerShell, Windows Terminal 또는 macOS 터미널에서 실행합니다.

```powershell
docker compose pull
docker compose up -d
docker compose ps
```

상대 경로를 사용하면 Compose 파일 옆에 `nasdrop-config`와 `downloads` 폴더가 만들어집니다. Docker Desktop이 폴더를 마운트하지 못하면 Docker Desktop 파일 공유 설정에서 해당 드라이브나 폴더를 허용하세요. 같은 컴퓨터에서는 `http://localhost:8791`로 접속합니다.

## 다운로드 폴더 추가

추가 목적지는 모두 컨테이너에 마운트하고 `NAS_PORTAL_STORAGE_ROOTS`에도 등록해야 합니다.

```yaml
environment:
  NAS_PORTAL_NAS_TARGET: /downloads
  NAS_PORTAL_STORAGE_ROOTS: /downloads,/media,/archive
volumes:
  - /srv/downloads:/downloads
  - /srv/media:/media
  - /mnt/archive:/archive
```

NASDrop 설정에서는 `/media` 같은 컨테이너 내부 경로를 선택합니다.

## 업데이트와 백업

Compose의 이미지 태그를 새 버전으로 변경하고 다음 명령을 실행합니다.

```sh
docker compose pull
docker compose up -d
```

업데이트 후 설정에서 기본 다운로드 폴더를 다시 선택해 쓰기 권한을 재확인하는 것을 권장합니다. 컨테이너를 교체해도 `/config`와 `/downloads` 마운트의 데이터는 유지됩니다.

설정 백업은 컨테이너를 중지한 상태에서 호스트의 설정 폴더를 복사하면 됩니다.

```sh
docker compose stop
tar -czf nasdrop-config-backup.tgz nasdrop-config
docker compose start
```

로그인을 재설정하려면 다음 명령을 실행합니다.

```sh
docker compose exec nasdrop nasdrop-account set owner
docker compose restart nasdrop
```

시놀로지 Container Manager에서는 실행 중인 `nasdrop` 컨테이너의 **터미널**에서 셸을 만든 다음 `nasdrop-account set owner`를 실행하고, **작업** 메뉴에서 컨테이너를 재시작합니다.

## 오프라인 이미지 설치

GitHub 릴리스에는 Docker TAR 파일이 첨부되지 않습니다. 인터넷이 연결된 PC에서 필요한 아키텍처의 이미지를 받은 뒤 전송용 TAR를 직접 만듭니다.

```sh
docker pull --platform linux/amd64 ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-3
docker save -o nasdrop-0.9.26-3-amd64.tar ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-3
```

ARM64 호스트에서는 `linux/amd64`와 `amd64.tar`를 각각 `linux/arm64`와 `arm64.tar`로 바꿉니다. 만든 TAR와 설치 파일을 오프라인 호스트로 복사한 다음 이미지를 불러와 실행합니다.

```sh
docker load -i nasdrop-0.9.26-3-amd64.tar
docker compose up -d
```

ARM64 환경에서는 해당 파일명을 사용하세요. 오프라인 호스트에서는 `docker compose pull`을 실행하지 않습니다. 불러온 이미지는 `compose.yaml`에서 사용하는 번호 태그를 유지합니다. 인터넷 연결 환경에서는 GHCR에서 직접 받으면 Docker가 아키텍처를 자동 선택합니다.

## 문제 해결

- **웹 화면이 열리지 않음:** `docker compose ps`와 `docker compose logs --tail=100 nasdrop`을 확인하고 포트 충돌과 방화벽을 점검합니다.
- **다운로드 폴더가 잠김:** 바인드 마운트 경로, `PUID`, `PGID`, 호스트 폴더 권한을 확인합니다. 컨테이너 root가 아니라 실제 서비스 숫자 계정으로 검사하세요.

```sh
docker compose exec nasdrop sh -c 'gosu "$PUID:$PGID" sh -c "id; test -w /downloads && echo writable || { echo not-writable; exit 1; }"'
```
- **컨테이너가 계속 재시작됨:** `/config`가 `PUID:PGID`로 쓰기 가능한지 확인합니다. 권한 문제를 숨기려고 읽기 전용이나 보안 옵션을 제거하지 마세요.
- **8791 포트 충돌:** `.env`에서 `NASDROP_PORT=8792`로 변경하거나 포트 매핑을 `8792:8791`로 바꿉니다.

## 외부 접속 보안

`8791` 포트는 일반 HTTP입니다. 신뢰하는 내부 네트워크에서 사용하세요. 외부 접속에는 HTTPS 리버스 프록시나 사설 VPN을 사용하고 인터넷 공유기에서 `8791`을 직접 포트 포워딩하지 마세요. `NASDROP_TRUST_FORWARDED_FOR=true`는 신뢰할 수 있는 로컬 리버스 프록시만 NASDrop에 접근할 수 있을 때만 설정합니다.
