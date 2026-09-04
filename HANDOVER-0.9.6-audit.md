# NASDrop 0.9.6 감사 결과 핸드오버

작성일: 2026-09-03
대상 커밋: `ef1777a` (Restore legacy ZIP filenames), 태그 `v0.9.6-1`
저장소: https://github.com/littleweirdlab0514-web/NASDROP

이 문서는 코드 감사에서 확인된 결함 목록과 수정 지침이다. 이 문서만 읽고 작업할 수 있도록 파일 경로, 줄 번호, 재현 절차, 수정 방향을 모두 포함했다.

---

## 0. 시작 전 확인

### 0-1. 기존 검증 절차는 전부 통과한다

아래 세 명령은 감사 시점에 모두 통과했다. **수정 후에도 반드시 통과해야 한다.**

```
python -m py_compile backend.py
python -m unittest discover -s tests -p "test_*.py"     # 80 tests, OK
node --test tests/rendered-html.test.mjs tests/gofile-wt-sandbox.test.mjs   # 9 tests, pass
```

즉 아래 결함들은 **기존 테스트가 잡아내지 못하는 것들**이다. 각 항목을 고칠 때 회귀 테스트를 함께 추가할 것.

### 0-2. 로컬 재현 환경

```
NAS_PORTAL_STATE_DIR=<임시디렉터리> \
NAS_PORTAL_LISTEN_HOST=127.0.0.1 \
NAS_PORTAL_LISTEN_PORT=8899 \
python backend.py
```

계정 생성(런처 토큰 사용):

```
TOK=$(cat <임시디렉터리>/access_token)
curl -X POST http://127.0.0.1:8899/api/account \
  -H "authorization: Bearer $TOK" -H 'content-type: application/json' \
  -d '{"username":"owner","password":"correcthorse1"}'
```

### 0-3. 이미 잘 되어 있는 부분 — 건드리지 말 것

다음은 감사에서 문제없음을 확인했다. "개선"하려다 회귀를 만들지 말 것.

- **SSRF 방어**: `_validate_buzzheavier_download_url`, `BuzzheavierRedirectHandler`, `inspect_gigafile`의 `GIGAFILE_HOST` 검사 — 호스트 화이트리스트 + HTTPS 강제 + 리다이렉트 목적지 재검증까지 되어 있다.
- **셸 주입 방어**: `_download_script*` 계열이 `shlex.quote`를 일관되게 적용한다.
- **압축 해제 안전성**: `_archive_relative_path`(절대경로/`..`/NUL 차단), `_validate_seven_zip_listing`(해제 **전** 검증), `_validate_extracted_tree`(해제 **후** 심볼릭 링크·이탈 재검증). 2단 방어가 제대로 되어 있다.
- **파일명 정제**: `_clean_download_name`이 `\ / \x00-\x1f :`를 치환하고 180자로 자른다. 경로 이탈 불가.
- **저장 경로 격리**: `storage_root_for` + `Path.resolve()` 조합으로 `STORAGE_ROOTS` 밖으로 나갈 수 없다.
- **비밀번호 해싱**: PBKDF2-SHA256 600,000회, 솔트 16바이트.
- **작업 시크릿 파일**: `SECRET_DIR` 0700, 개별 파일 0600. Buzzheavier 서명 토큰이 `jobs.json`과 작업 목록에서 분리되어 있다는 README 서술은 정확하다.
- **프런트엔드 런처 토큰 처리**: `app.js`가 해시에서 읽은 뒤 `history.replaceState`로 즉시 제거하고 `localStorage`에 저장하지 않는다.

---

## 1. [P0] 한글/일본어/중국어 ID로 로그인 시 서버가 응답 없이 연결을 끊음

**위치**: `backend.py:262` (`verify_credentials`)

```python
username_matches = secrets.compare_digest(username.strip().casefold(), stored_username.casefold())
```

**원인**: `secrets.compare_digest`는 str 인자에 non-ASCII 문자가 있으면 `TypeError: comparing strings with non-ASCII characters is not supported`를 던진다. 이 줄은 바로 아래 `try` 블록(솔트 파싱/해싱) **바깥**이라 잡히지 않는다. `do_POST`의 `/api/login` 핸들러는 `except (ValueError, json.JSONDecodeError)`만 잡으므로 `TypeError`가 그대로 전파되어 `socketserver`가 커넥션을 끊는다.

**재현**:

```
python -c "import json; open('p.json','wb').write(json.dumps({'username':'테스트','password':'correcthorse1'}, ensure_ascii=False).encode('utf-8'))"
curl -s -w "\n[http=%{http_code} exit=%{exitcode}]\n" -X POST http://127.0.0.1:8899/api/login \
  -H 'content-type: application/json' --data-binary @p.json
```

관측 결과: `[http=000 exit=52]` (empty reply from server). `service.log`에 전체 traceback 기록.

> 주의: 셸에서 한글을 인라인으로 넘기면 인코딩이 깨져 이 버그를 재현하지 못하고 별개의 UTF-8 디코드 오류(400)가 난다. 반드시 위처럼 파일로 만들어 `--data-binary`로 보낼 것.

**영향**:
1. 이 제품은 한/일/중 UI를 기본 제공한다. 해당 언어권 사용자가 자국어 ID를 시도하면 "ID 또는 비밀번호가 올바르지 않습니다" 대신 **먹통**을 본다.
2. `record_login_result`가 실행되지 않으므로 **이 시도는 로그인 차단 카운트에 잡히지 않는다**.
3. 매 요청마다 multi-line traceback이 `service.log`에 쌓인다. 로그는 1 MiB × (본체 + 백업 2개) 제한이므로, 인증 없이 반복하면 **진단 로그 전체를 밀어낼 수 있다**.

**수정 방향** (둘 중 하나, 또는 둘 다):

- (권장) 로그인 경로에서 `normalize_username`과 동일한 정규식 `[A-Za-z0-9._-]{3,32}`을 먼저 적용해 형식에 맞지 않는 ID는 인증 실패로 처리한다. 이때 **타이밍 차이가 생기지 않도록**, 그리고 `record_login_result(client_ip, False)`가 반드시 호출되도록 할 것.
- `secrets.compare_digest`에 넘기기 전에 양쪽을 `.encode("utf-8")`로 바이트화한다.

계정 생성은 이미 `normalize_username`으로 ASCII만 허용하므로, 저장된 ID가 non-ASCII일 가능성은 없다. 따라서 non-ASCII 입력은 무조건 인증 실패로 처리해도 기능 손실이 없다.

**추가할 테스트**: `tests/test_account_auth.py`에 non-ASCII ID 로그인이 401(또는 400)을 반환하고 예외가 전파되지 않으며 실패 카운트가 증가하는지 확인하는 케이스.

---

## 2. [P0] `X-Forwarded-For` 헤더로 로그인 차단을 완전 우회

**위치**: `backend.py:350` (`trusted_client_ip`)

```python
if not peer.is_loopback or not forwarded_for:
    return peer_ip
candidate = forwarded_for.split(",", 1)[0].strip()   # ← 첫 번째 값을 신뢰
```

**원인**: peer가 loopback이면 `X-Forwarded-For`의 **첫 번째** 항목을 클라이언트 IP로 채택한다. 그런데 README가 권장하는 배포 형태가 정확히 이 조건이다 — DSM 역방향 프록시는 같은 NAS에서 돌기 때문에 peer는 항상 `127.0.0.1`이다. DSM의 nginx는 `$proxy_add_x_forwarded_for`를 사용하므로 **클라이언트가 보낸 값 뒤에** 실제 IP를 덧붙인다. 결과적으로 `split(",")[0]`은 공격자가 완전히 제어한다.

**재현**:

```
# 고정 IP: 정상 동작 (5회째부터 차단)
for i in 1 2 3 4 5 6; do
  curl -s -X POST http://127.0.0.1:8899/api/login -H 'content-type: application/json' \
    -H 'x-forwarded-for: 203.0.113.9' -d '{"username":"owner","password":"wrong"}'; echo
done

# IP 회전: 차단 안 됨
for i in $(seq 1 25); do
  curl -s -X POST http://127.0.0.1:8899/api/login -H 'content-type: application/json' \
    -H "x-forwarded-for: 198.51.100.$i" -d '{"username":"owner","password":"wrong"}'; echo
done
```

관측 결과: 고정 IP는 6회째에 차단. IP 회전은 **25회 연속 오답에도 차단 0회**.

**부수 영향**: `log_request`는 `self.client_address[0]`(= `127.0.0.1`)를 기록한다. 즉 역방향 프록시 뒤에서는 **로그로도 공격자를 특정할 수 없다**. README의 보안 가이드라인은 "client IP addresses"를 기록한다고 하지만 실제로는 프록시 IP만 남는다.

**수정 방향**:

1. XFF 신뢰를 명시적 옵트인으로 전환한다. 예: `NAS_PORTAL_TRUST_FORWARDED_FOR` (기본 off). 기본값 off여야 하는 이유는, 프록시를 쓰지 않는 사용자가 로컬 프로세스로부터 스푸핑당하는 것을 막기 위함이다.
2. 신뢰하는 경우에도 **마지막** 항목을 사용한다. 신뢰 프록시가 덧붙인 값이 항상 마지막이기 때문이다.
3. IP 기반 카운터와 **별도로** 계정 단위 전역 실패 카운터를 둔다. IP 스푸핑이 가능하더라도 계정 단위 잠금은 우회할 수 없다. (단, 이것만으로는 정상 사용자를 잠글 수 있으므로 지수 백오프 등 완화책을 함께 고려)
4. 로깅에는 실제 peer IP와 채택된 클라이언트 IP를 **모두** 남긴다.

**README 동반 수정**: 아래 §11-B 참고.

**추가할 테스트**: `trusted_client_ip`가 옵트인 off일 때 XFF를 무시하는지, on일 때 마지막 항목을 취하는지.

---

## 3. [P1] `LOGIN_FAILURES` 딕셔너리가 무한 증가

**위치**: `backend.py:324` (`login_block_remaining`)

```python
failures, blocked_until = LOGIN_FAILURES.get(client_ip, (0, 0))
if not failures or not blocked_until:
    return 0                      # ← 항목을 제거하지 않음
if blocked_until <= time.time():
    LOGIN_FAILURES.pop(client_ip, None)
    return 0
```

**원인**: 실패 횟수가 `LOGIN_FAILURE_LIMIT`(5) 미만이면 `blocked_until`이 `0`이므로 첫 번째 분기로 빠지고, 항목이 **프로세스 수명 내내 제거되지 않는다**. 차단이 걸린 항목만 만료 시 정리된다.

**영향**: 결함 2와 결합하면 인증 없는 공격자가 요청 하나당 항목 하나씩 무한히 적재할 수 있다. 딕셔너리 크기 상한도 없다.

**수정 방향**: `record_login_result`에 진입할 때마다 오래된 항목을 정리한다. 마지막 실패 시각을 튜플에 추가하고, `LOGIN_BLOCK_SECONDS`가 지난 항목은 만료 처리한다. 추가로 전체 항목 수 상한(예: 4096)을 두고 초과 시 가장 오래된 것부터 제거한다. `create_session`이 `SESSIONS`를 정리하는 방식(`backend.py:273`)과 동일한 패턴을 쓰면 된다.

---

## 4. [P1] `Content-Length: -1` 요청 하나로 워커 스레드를 영구 점유

**위치**: `backend.py:2294` (`Handler.body`)

```python
length = min(int(self.headers.get("content-length", "0")), 16_384)
return json.loads(self.rfile.read(length) or b"{}")
```

**원인**: 상한만 있고 하한이 없다. `min(-1, 16384)`는 `-1`이고, `rfile.read(-1)`은 EOF까지 블로킹한다. keep-alive 커넥션에서는 클라이언트가 닫을 때까지 스레드가 묶인다.

**재현**:

```python
import socket, time
s = socket.create_connection(('127.0.0.1', 8899), 3)
s.sendall(b'POST /api/login HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n'
          b'Content-Type: application/json\r\n\r\n{}')
s.settimeout(5)
try:
    print('response:', s.recv(200))
except Exception as e:
    print('NO RESPONSE -> thread blocked:', type(e).__name__)
```

관측 결과: 5초 대기 후에도 응답 없음.

**영향**: `/api/login`은 인증 이전 경로이므로 **인증 없이 트리거 가능**하다. `ThreadingHTTPServer`는 동시 커넥션 상한이 없어 스레드/메모리 고갈로 이어진다.

**수정 방향**:

```python
length = max(0, min(int(self.headers.get("content-length", "0") or "0"), 16_384))
```

추가로 `int()` 실패 시(`ValueError`)의 처리 경로를 확인할 것. 현재는 `do_POST`의 `try`에 잡혀 400이 나가므로 동작은 하지만, 명시적으로 0으로 처리하는 편이 낫다. 소켓 타임아웃(`Handler.timeout`) 설정도 함께 검토할 것.

---

## 5. [P1] DSM 런처 토큰이 회전하지 않는 영구 마스터 자격증명

**위치**: `backend.py:197` (`load_launcher_token`), `backend.py:207`, `backend.py:391`, `backend.py:2385`

**문제 구조**:

1. `runtime/access_token`은 최초 1회 생성 후 **절대 재생성되지 않는다**. `replace_credentials`(`backend.py:301`)는 `SESSIONS`만 비우고 이 토큰은 건드리지 않는다. → **사용자가 비밀번호를 바꿔도 유출된 런처 토큰은 계속 유효하다.**
2. `backend.py:2385`에서 `auth_kind() == "launcher"`이면 현재 비밀번호 확인을 건너뛰고 ID/비밀번호를 통째로 교체할 수 있다. 즉 이 토큰은 **계정 탈취 권한을 가진 마스터 키**다.
3. 이 토큰이 `launcher.html`에 평문으로 기록되며, 파일 권한은 `backend.py:391`에서 `chmod(0o644)` — **월드 리더블**이다.
4. 보호 수단은 `synology/package-inner/ui/config`의 `"allUsers": false` 하나뿐이다. 이는 DSM 관리자가 일반 사용자에게 부여할 수 있는 앱 권한이며, `/webman/3rdparty/nasdownloadportal/launcher.html`에 대한 정적 파일 요청에 DSM이 이 권한을 강제하는지는 별도 검증이 필요하다.

**수정 방향** (우선순위 순):

1. **런처 토큰을 1회용으로 전환한다.** `launcher.html` 요청 시마다 짧은 TTL(예: 60초)의 일회성 핸드오프 토큰을 발급하고, 사용 즉시 폐기한다. 현재처럼 영구 토큰을 정적 파일에 박아두지 않는다.
2. `replace_credentials` 실행 시 런처 토큰도 함께 재생성한다.
3. 그때까지의 완화책으로 `launcher.html`의 권한을 `0600`으로 낮출 수 있는지 검토한다. 단 DSM 웹서버가 읽을 수 있어야 하므로 실제 실행 계정을 먼저 확인할 것.
4. `write_launcher_file`이 토큰을 담지 않는 형태로 바꾸는 것이 가장 근본적이다. 예를 들어 `/api/launcher/handoff` 엔드포인트를 두고 런처 페이지가 그것을 호출하게 한다.

**README 동반 수정**: 아래 §11-C 참고.

---

## 6. [P2] API 라우팅이 쿼리스트링을 포함한 전체 경로로 매칭

**위치**: `backend.py:2306`, `backend.py:2318` 등 `do_GET` 전반

`/api/folders`만 `parsed_path.path`로 비교하고, 나머지는 `self.path`(쿼리스트링 포함)로 비교한다. 따라서 쿼리 파라미터가 붙으면 API 분기를 타지 못하고 `serve_static()`으로 떨어진다.

**재현**:

```
curl -o /dev/null -w "%{http_code} %{content_type}\n" "http://127.0.0.1:8899/api/status?x=1" -H "authorization: Bearer $SESSION"
# 200 text/html; charset=utf-8   ← JSON이 아니라 index.html
curl -o /dev/null -w "%{http_code} %{content_type}\n" "http://127.0.0.1:8899/api/jobs?x=1" -H "authorization: Bearer $SESSION"
# 200 text/html; charset=utf-8
```

**영향**: 캐시 무효화용 쿼리(`?t=...`)를 붙이는 클라이언트 — 특히 안드로이드 클라이언트 — 가 JSON 대신 HTML을 받고 파싱에 실패한다. 200을 반환하므로 오류 처리도 타지 않는다.

**수정 방향**: `do_GET`/`do_POST` 진입부에서 `path = urlparse(self.path).path`를 한 번 계산하고, 모든 라우팅 비교를 이 값으로 통일한다. `do_POST`의 `re.fullmatch` 3종(cancel/pause/resume/password)도 동일하게 적용할 것. `/api/` 접두사 검사도 마찬가지다.

---

## 7. [P2] 백엔드 오류 메시지 91개가 한국어 하드코딩 — 4개 국어 지원과 모순

**위치**: `backend.py` 전역 (`raise ValueError` 95개 중 91개가 한국어), `synology/web/app.js`, `synology/web/i18n.js`

**현상**: `app.js`는 서버 오류를 `error.message` 그대로 `textContent`에 넣는다(최소 12곳). `i18n.js`에는 서버 오류 문자열 매핑이 없다.

**재현**:

```
curl -X POST http://127.0.0.1:8899/api/inspect -H "authorization: Bearer $SESSION" \
  -H 'accept-language: en-US,en' -H 'content-type: application/json' \
  -d '{"url":"https://example.com/nope"}'
# {"error": "정식 GigaFile HTTPS 링크가 아닙니다."}

curl http://127.0.0.1:8899/api/status -H 'accept-language: en-US,en'
# {"error": "로그인이 필요합니다."}
```

**영향**: 영어/일본어/중국어 UI 사용자가 모든 실패 상황에서 한국어를 본다. 로그인 실패 메시지(`#login-error`)가 비한국어 사용자가 가장 먼저 마주치는 지점이다. README §Languages는 제품 전체가 현지화된 것처럼 서술한다.

**수정 방향** (권장안):

1. `ValueError` 메시지를 **오류 코드**로 전환한다. 예: `raise PortalError("invalid_gigafile_link")`. 응답은 `{"error": "...", "code": "invalid_gigafile_link"}` 형태로 하위 호환을 유지한다.
2. `i18n.js`에 코드 → 4개 국어 문자열 매핑을 추가하고, `app.js`가 `code`가 있으면 번역문을, 없으면 `error`를 표시하도록 한다.
3. 작업 목록의 실패 사유(`job.error` / `detail`)도 동일하게 처리한다.

**작업량이 크므로 단계적 접근 권장**: 사용자가 가장 자주 보는 경로(로그인, 링크 검사, 폴더 선택, 작업 실패 사유)부터 코드화한다.

**추가할 테스트**: `tests/rendered-html.test.mjs`에 "모든 오류 코드가 4개 국어 모두에 매핑되어 있는지" 검사를 추가하면 이후 회귀를 막을 수 있다.

---

## 8. [P3] 그 외 소규모 결함

| # | 위치 | 내용 | 수정 |
|---|---|---|---|
| 8-1 | 다운로드 스크립트 전반 | GoFile `accountToken`과 Buzzheavier 서명 URL이 curl argv로 전달되어 로컬 사용자의 `ps` 출력에 노출된다. (`shlex.quote`는 적용되어 있어 **주입은 불가**) | 토큰을 환경변수나 `--config` 파일(0600)로 전달 |
| 8-2 | `backend.py:946` | `jobs.json`만 명시적 `chmod(0o600)`이 없다. `credentials.json`·`config.json`·job-secrets는 모두 0600. DSM의 `umask 077`과 Docker의 `/config` 0700이 덮어주므로 현재 악용 불가하나 일관성이 없다 | `temp.chmod(0o600)` 추가 |
| 8-3 | `backend.py:787` | 압축 해제 실행(`_run_seven_zip(["x", ...])`)에 `timeout` 미지정. 목록 조회는 `timeout=120`이 있다 | 충분히 큰 타임아웃 지정 |
| 8-4 | `backend.py:1699` | Buzzheavier User-Agent에 `"NASDrop/0.9.6"`이 리터럴로 박혀 있다. `PACKAGE_VERSION`을 쓰지 않아 다음 릴리스에서 조용히 어긋난다 | f-string으로 `PACKAGE_VERSION` 사용. `docs/RELEASE_CHECKLIST.md`에도 항목 추가 |
| 8-5 | `set_*` 설정 함수들 | `CONFIG` 전역의 read-modify-write에 락이 없다. 동시 `/api/settings` 요청 시 갱신 유실 가능 | 설정 쓰기 전용 락 추가 |

---

## 9. 우선순위 요약

| 우선순위 | 항목 | 근거 |
|---|---|---|
| **P0** | §1 한글 ID 크래시 | 정상 사용자가 즉시 부딪힘. 한 줄 수정 |
| **P0** | §2 XFF 로그인 차단 우회 | README 권장 구성에서 인증 보호가 무력화됨 |
| **P1** | §4 `Content-Length: -1` | 한 줄 수정. 인증 불필요 DoS |
| **P1** | §3 `LOGIN_FAILURES` 누수 | §2와 결합 시 증폭 |
| **P1** | §5 런처 토큰 영구성 | 설계 재검토 필요. 단독 작업으로 분리 권장 |
| **P2** | §6 쿼리스트링 라우팅 | 안드로이드 클라이언트 연동 전에 반드시 해결 |
| **P2** | §7 오류 메시지 현지화 | 작업량 큼. 단계적 진행 |
| **P3** | §8 소규모 항목 | 묶어서 한 번에 |

§1과 §4는 각각 한 줄 수정이므로 즉시 처리 가능하다.

---

## 10. 커밋 분할 제안

기존 저장소의 커밋 스타일(영문 명령형 한 줄 요약)을 따를 것.

1. `Reject non-ASCII account IDs during login` — §1 + 테스트
2. `Clamp request body length to a non-negative size` — §4
3. `Trust forwarded client IPs only when configured` — §2 + §3 + 테스트
4. `Match API routes without the query string` — §6 + 테스트
5. `Correct reverse proxy and login throttle documentation` — §11-A/B/C
6. `Document NASDrop size and archive limits` — §11-D
7. (별도 작업) §5 런처 토큰 재설계
8. (별도 작업) §7 오류 메시지 코드화

---

## 11. README 수정 사항

### 11-A. [오류] `X-Forwarded-Proto` / `X-Forwarded-Host` 안내가 무의미하다

**위치**: `README.md:329` 부근

```
DSM should forward the original host and HTTPS scheme. If the generated public address is incorrect, add or correct these reverse-proxy request headers:
- `X-Forwarded-Proto: https`
- `X-Forwarded-Host: nas.example.com:8791` when the public URL uses port `8791`
```

**사실 확인**: `backend.py`가 읽는 요청 헤더는 다음 **세 개뿐**이다.

- `authorization` (`backend.py:2272`)
- `x-forwarded-for` (`backend.py:2279`)
- `content-length` (`backend.py:2294`)

`X-Forwarded-Proto`와 `X-Forwarded-Host`는 `backend.py`, `synology/web/`, `docs/` 어디에서도 참조되지 않는다(grep으로 확인). 공개 주소는 `render_launcher_html`이 생성한 스크립트가 **브라우저에서** `location.hostname` / `location.protocol`로 계산한다.

**조치**: 해당 두 줄과 앞 문장을 삭제한다. 실제 해법인 "DSM icon external port" 설정은 이미 같은 절에 문서화되어 있으므로 그쪽을 가리키게 한다.

### 11-B. [과장] 로그인 차단 설명

**위치**: `README.md:155`

```
- Five consecutive failed login attempts from the same client IP trigger a 15-minute login block.
```

결함 §2 때문에, **README가 권장하는 DSM 역방향 프록시 구성에서는 성립하지 않는다.** §2를 수정하기 전까지는 이 문장을 그대로 두면 안 된다.

**조치**: §2 수정과 동시에 진행한다. 수정 후에는 "신뢰할 수 있는 프록시가 전달한 클라이언트 IP 기준"임을 명시하고, 설정 항목 이름을 함께 안내한다. 같은 절의 보안 가이드라인에 있는 "records ... client IP addresses"도 프록시 뒤에서는 프록시 IP가 기록된다는 점을 반영해야 한다.

### 11-C. [근거 부족] "administrator-only launch"

**위치**: `README.md:150`

```
- Sign in to DSM with an administrator account, then open NASDrop from its DSM desktop or Package Center icon. This administrator-only launch signs in automatically.
```

**사실 확인**: 패키지 어디에도 관리자 여부를 검사하는 코드가 없다. `synology/package/conf/privilege`는 `{"defaults": {"run-as": "package"}}`뿐이고, 접근 제어는 `synology/package-inner/ui/config`의 `"allUsers": false` 하나에 의존한다. 이 값은 "기본적으로 관리자만"을 의미할 뿐이며, DSM 관리자가 제어판 → 응용 프로그램 권한에서 일반 사용자에게 부여할 수 있다.

**조치**: "administrator-only"를 "DSM에서 NASDrop 앱 권한이 부여된 계정"으로 정정한다. §5를 해결하기 전이라면, 이 권한을 일반 사용자에게 부여하면 NASDrop 계정을 재설정할 수 있게 된다는 점을 경고로 덧붙인다.

### 11-D. [누락] 하드 리밋이 문서화되어 있지 않다

`backend.py:79-82`에 정의된 다음 상한이 README 어디에도 없다.

| 상수 | 값 | 사용자에게 보이는 증상 |
|---|---|---|
| `MAX_FILE_BYTES` | 300 GiB | 초과 시 "허용할 수 없는 파일 정보입니다" — 원인을 알 수 없는 메시지 |
| `MAX_EXTRACTED_BYTES` | 1 TiB | 압축 해제 거부 |
| `MAX_ARCHIVE_ENTRIES` | 100,000 | 압축 해제 거부 |
| `MAX_PARALLEL_DOWNLOADS` | 3 | 대기열이 도는 속도 |

**조치**: Features 절이나 별도의 "Limits" 절에 명시한다. 특히 300 GiB는 사용자가 실제로 부딪힐 수 있는 값인데 오류 메시지가 원인을 알려주지 않는다 — 메시지에 실제 상한을 포함시키는 것도 함께 검토할 것.

### 11-E. [누락] Repository layout

**위치**: `README.md:62`

현재 목록에 `tests/`, `docs/`, `assets/`, `.github/`가 빠져 있다. 항목을 추가한다.

### 11-F. [불일치] Docker 빠른 시작 1단계

**위치**: `README.md:93`

```
1. Download `compose.yaml` and copy `docker/compose.env.example` to `.env`.
```

`compose.yaml`만 내려받은 사용자에게는 `docker/` 디렉터리가 없다. 또한 `compose.yaml`은 모든 변수에 기본값을 갖고 있어(`${PUID:-1000}`, `${NASDROP_CONFIG_DIR:-./nasdrop-config}` 등) `.env` 없이도 기동된다.

**조치**: `.env`가 선택 사항임을 명시하거나, `compose.env.example`의 내용을 README에 직접 인용해 복사할 수 있게 한다.

### 11-G. [불일치] Languages 절

**위치**: `README.md:215-217`

셸 UI가 4개 국어라는 서술은 맞지만, 결함 §7 때문에 모든 오류 메시지는 한국어로 표시된다. §7 수정 전이라면 이 절에 알려진 제약으로 명시하고, 수정 후 제거한다.

### 11-H. 정확한 것으로 확인된 서술 — 수정 불필요

- DSM 7.1 이상 지원 → `synology/package/INFO`의 `os_min_ver="7.1-42661"`과 일치
- SPK 출력 파일명 `nasdrop-0.9.6-1-x86_64.spk` → `synology/build-spk.ps1:85`와 일치
- 로그 1 MiB 제한, 백업 2개, 총 약 3 MiB → `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT`와 일치
- 쿼리스트링을 제외한 경로만 로깅 → `log_request`가 `urlparse(self.path).path` 사용, 일치
- Docker 이미지 amd64/arm64 멀티플랫폼 → `.github/workflows/docker.yml:81` `linux/amd64,linux/arm64`와 일치
- Buzzheavier 토큰이 작업 목록과 `jobs.json`에서 분리 저장 → `SECRET_DIR` 0700/0600, 작업 source는 canonical URL. 일치
- 8분할 다운로드 → 다운로드 스크립트의 `COUNT=8`과 일치
- 버전 0.9.6이 `backend.py` / `compose.yaml` / `INFO` / `build-spk.ps1` / `README` 전부에서 일치

---

## 12. 참고

- 이 문서는 저장소에 커밋되지 않은 untracked 파일이다. 작업 완료 후 삭제하거나 `docs/`로 옮길지 결정할 것.
- 감사 시점에 로컬 작업 트리는 `origin/main`과 동일했고, 수정 사항은 없었다.
