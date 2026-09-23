# NASDrop 0.9.26 릴리스 체크리스트

## 0.9.26 security hardening

- [x] Static DSM launcher files contain no bearer token or reusable credential.
- [x] DSM launcher uses `authenticate.cgi`, requires the administrators group, and returns no cacheable response.
- [x] Launcher handoffs are HMAC-signed, expire after 30 seconds, and are accepted once.
- [x] Existing NASDrop credentials still require the current password when opened through DSM.
- [x] GoFile navigator-constructor and Date-constructor escape regressions are blocked.
- [x] GoFile helper runs with Node permission restrictions.
- [x] Send.now inspection and transfer pin the validated public destination address.
- [x] Docker bootstrap remains `nasdrop` / `nasdrop`, is PBKDF2-hashed at rest, and is confined to minimal account/status operations until mandatory replacement.
- [x] `docs/PROVIDER_AND_SECURITY_POLICY.md` records every supported provider's input, transfer limits, failure response, browser responsibilities, and current security boundaries.
- [ ] Install 0.9.26-5 on DSM and verify admin auto launch without a NASDrop login, signed-out rejection, non-admin rejection, initial setup, and existing-account password protection. If auto launch still fails, capture only the safe launcher diagnostic category; never share cookies, session IDs, or tokens.
- [ ] Complete one real GoFile and one real Send.now download on DSM.
- [ ] After DSM confirmation, synchronize and smoke-test Docker, then promote the exact candidate digest.

## 0.9.25 GigaFile protected downloads

- [x] Download keys and archive passwords use separate fields and server state.
- [x] Missing or rejected keys pause with `download_key_required` and are never retried automatically.
- [x] The web portal and Chrome 0.5.5 can submit a key without putting it in a URL, log, public job response, or browser storage.
- [x] A paused job can accept a corrected key and resume without deleting verified download work.
- [x] The job secret is removed when it is rejected, no longer needed, or the job is deleted.
- [x] A real protected GigaFile page was detected as requiring a key without exposing the key.
- [ ] Complete a protected GigaFile download on the target NAS using the correct key.
- [ ] Verify wrong-key recovery, service restart, and package update on DSM.

## 0.9.24 Send.now browser handoff

- [x] The extension intercepts only a prepared official final link after user verification.
- [x] CAPTCHA and Cloudflare controls are not automated or bypassed.
- [x] The server rejects private/local destinations and unsafe URL forms while allowing changing public HTTPS delivery hosts.
- [x] Python and Chrome extension regression suites pass together.
- [ ] Complete a real user-assisted Send.now download on the target NAS.
- [ ] After the real flow passes, synchronize Docker and run source-parity and multi-architecture smoke tests.

## 0.9.23 Safe stop-and-delete

- [x] Capability-gated stop-and-delete waits for worker/process completion.
- [x] Completed output is preserved; only the selected private workspace and record are removed.
- [x] Cleanup failure retains the record; restart does not replay destructive requests.
- [ ] Verify the updated Android client and SPK together on DSM, including extraction cancellation.

## 0.9.14 GoFile 연결 제한

- [x] 새 GoFile 분할 작업은 최대 2분할이며 단일 연결 설정은 유지한다.
- [x] 기존 8분할 작업은 범위를 보존하고 두 연결씩 전송하도록 스크립트를 생성한다.
- [x] 2분할 조각 결합 및 일반 파일/압축파일 회귀 테스트를 통과한다.
- [ ] 실제 NAS에서 새 GoFile 작업과 기존 작업 이어받기를 확인한다.
- [ ] 동일 서비스 동시 작업 설정에 따라 전체 연결 수가 증가함을 확인한다.

## 0.9.13 감사 수정 검증

- [ ] 로컬 범위 응답을 강제로 끊고 재개해 원본 바이트와 정확히 일치한다.
- [ ] 검증된 미완료 조각은 재사용하고 I/O 오류 후에도 복구할 수 있다.
- [ ] 응답 범위를 모르는 이전 `.more` 조각 재다운로드 제한을 안내한다.
- [ ] 중지 중인 작업은 재개·삭제할 수 없고 워커 종료 후 일시정지로 전환된다.
- [ ] GoFile 파일 전송의 429가 같은 공급자의 모든 대기 작업을 지연시킨다.
- [ ] 암호 입력 중 목록 조회가 도착해도 입력값·포커스·펼친 검증 정보가 유지된다.
- [ ] 실제 DSM에서 다운로드·검증·압축 해제 도중 패키지 중지 후 자식 프로세스가 남지 않는다.
- [ ] 실제 DSM 업데이트 후 이어받기와 암호 대기 작업 재개를 확인한다.
- [ ] 미인증 DSM 정적 URL 및 일반 NAS 계정에서 launcher.html/handoff를 읽을 수 있는지 별도 권한 검증을 수행한다.

자동 테스트 통과와 DSM 실기기 테스트는 구분해서 기록한다. 이번 변경은 런처 handoff 권한 경계를 재설계하지 않는다.

## 공급자 파일명 회귀 방지

- [ ] 웹페이지 표시명이 아니라 최종 `Content-Disposition`의 `filename*` → `filename` 순서로 실제 이름을 선택한다.
- [ ] GigaFile 일본어 치환 안내문 사례에서 일반 MP4가 원래 UTF-8 이름으로 저장된다.
- [ ] 동일 사례의 압축파일이 원래 이름의 폴더로 해제된다.
- [ ] 리디렉션·헤더 없음·악성 경로·동일 이름 충돌 테스트가 통과한다.
- [ ] 응답 헤더와 인증 정보가 작업 폴더·로그·API에 잔류하지 않는다.

세부 규칙은 `docs/PROVIDER_FILENAME_GUIDE.md`를 따른다.

## DSM 런처 이름 회귀 방지

- [ ] 설치 직후 앱을 열기 전에도 아이콘 이름이 `NASDrop`으로 표시된다.
- [ ] `ui/config`의 제목은 고정값 `NASDrop`이며 `nasdrop:title`을 사용하지 않는다.
- [ ] `texts` 경로와 `preloadTexts`에 다국어 설명 키가 설정되어 있다.
- [ ] 최종 SPK 내부 `package.tgz`의 `ui/config`도 빌드 단계에서 검사한다.
- [ ] DSM 새로고침과 새 로그인 세션 후에도 번역 키가 그대로 노출되지 않는다.

세부 규칙은 `docs/DSM_LAUNCHER_GUIDE.md`를 따른다.

## Synology 패키지

- [ ] DSM 7.1 이상 x86_64 NAS에서 수동 설치 성공
- [ ] 대괄호·괄호·공백·한글 파일의 분할 다운로드 진행률이 증가하고 완료 후 결합·검증 상태가 표시됨
- [ ] 패키지 시작 후 포털 접속 성공
- [ ] 기본 공유 폴더 쓰기 성공
- [ ] 새 설치 시 기본 저장 폴더가 비어 있고 폴더 선택 전 다운로드가 차단됨
- [ ] 관리자 계정 설정 및 웹 포털·Android 로그인 성공
- [ ] GigaFile, GoFile, Pixeldrain, Buzzheavier 각각 검사·다운로드 확인
- [ ] Buzzheavier 일반 공유 페이지는 `Copy download link` 안내를 표시하고, 서명된 직접 링크는 파일명·크기를 HEAD로 확인한다.
- [ ] Buzzheavier `v` 토큰이 작업 목록, `jobs.json`, 서비스 로그에 나타나지 않으며 재시작 후 비밀 저장소에서만 복구된다.
- [ ] 만료된 Buzzheavier 링크는 새 직접 링크가 필요하다는 전용 오류를 표시한다.
- [ ] GoFile 429 발생 시 추가 네트워크 요청 없이 대기 상태 표시
- [ ] 패키지 중지·업데이트·제거 동작 확인
- [ ] 영어 기본값과 한국어·일본어·중국어 자동/수동 전환 확인
- [ ] SPK의 INFO·생명주기 스크립트가 LF 줄바꿈인지 확인
- [ ] 모든 생명주기 스크립트와 번들 Node.js·7-Zip에 실행 권한이 있는지 확인

## 보안·안정성 회귀 방지

- [ ] DSM 런처 handoff는 한 번 교환한 뒤 즉시 거부되고, 계정 재설정 권한은 launcher 세션 발급 후 5분까지만 유효하다.
- [ ] 음수·16 KiB 초과 Content-Length 요청은 다운로드 큐에 도달하지 않고 400으로 거부된다.
- [ ] API 경로에 query string이 붙어도 JSON API로 라우팅된다.
- [ ] `X-Forwarded-For`는 기본적으로 무시되며, 명시적으로 신뢰한 로컬 프록시에서만 rightmost 주소를 사용한다.
- [ ] 로그인 실패 기록과 `jobs.json` 권한, 압축 해제 제한시간을 검사한다.
- [ ] 공급자 요청 User-Agent의 NASDrop 버전은 `PACKAGE_VERSION`과 일치한다.
- [ ] 세션 저장소는 256개를 넘지 않고 가장 오래된 세션부터 제거한다.
- [ ] 다운로드 리디렉션은 HTTPS만 허용하며 압축 암호가 7-Zip 프로세스 명령행에 나타나지 않는다.
- [ ] API와 작업 오류 코드가 영어·한국어·일본어·중국어 UI에 모두 매핑된다.
- [ ] ID·비밀번호 형식 오류와 로그인 제한 남은 시간이 4개 언어에서 구체적으로 표시된다.
- [ ] Pixeldrain User-Agent를 포함한 제품 버전 식별자는 `PACKAGE_VERSION`을 사용하며 과거 버전 문자열이 남아 있지 않다.
- [ ] DSM 역방향 프록시 모드는 기본적으로 꺼져 있고, loopback peer의 rightmost `X-Forwarded-For`만 신뢰한다.
- [ ] 프록시 모드가 꺼진 상태에서 loopback 전달 헤더를 받으면 설정 화면과 로그에 공동 로그인 차단 경고가 한 번 표시된다.
- [ ] 프록시 모드 변경은 `config.json`에 저장되고 서비스 재시작 없이 즉시 로그인 차단 버킷에 적용된다.
- [ ] 서로 다른 주소에서 60초 안에 로그인 실패 30회가 누적되면 전체 로그인은 5초만 지연되고, 15분 전역 잠금은 발생하지 않는다.

## 배포 기록

산출물 이름, SHA-256, 빌드 일시와 실기기 테스트 결과를 GitHub 릴리스 노트에 기록합니다. 빌드 성공과 실기기 동작 확인은 별도로 표시합니다.
