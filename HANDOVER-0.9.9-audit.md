# NASDrop 0.9.9 후속 감사 핸드오버

작성일: 2026-09-04
대상 커밋: `ad21587` (Harden NASDrop 0.9.9 security and localization), 태그 `v0.9.9-1`
이전 문서: `HANDOVER-0.9.6-audit.md` — **여기 있던 8개 항목은 전부 수정 확인됨. 해당 문서는 삭제해도 된다.**

---

## 0. 0.9.9에서 확인된 것

### 0-1. 검증 통과

```
python -m py_compile backend.py                              # OK
python -m unittest discover -s tests -p "test_*.py"           # 90 tests, OK
node --test tests/rendered-html.test.mjs tests/gofile-wt-sandbox.test.mjs   # 11 tests, pass
```

버전 문자열은 `backend.py:77` / `compose.yaml:7` / `synology/package/INFO:2` / `synology/build-spk.ps1:23` / `README.md` / `docs/RELEASE_CHECKLIST.md` 전부 `0.9.9`로 일치.

### 0-2. 이전 지적 8건 전부 해결 — 재현 테스트로 확인

| 항목 | 0.9.9 동작 |
|---|---|
| 한글 ID 로그인 | 401 + `invalid_credentials`, traceback 0건 |
| XFF 로그인 차단 우회 | 12회 IP 회전 중 8회 차단 (5회째부터 정상 작동) |
| `LOGIN_FAILURES` 누수 | `_prune_login_failures` + `MAX_LOGIN_FAILURE_ENTRIES=4096` |
| `Content-Length: -1` | `-1` / `abc` / 초과값 모두 즉시 400, 블로킹 없음 |
| 런처 토큰 영구 재사용 | 재사용 시 `launcher_expired`, 1회 교환 후 회전 |
| 쿼리스트링 라우팅 | `?x=1` 붙여도 전부 JSON 응답 |
| 오류 메시지 현지화 | 19개 코드 × 4개 국어 + 폴백 체인 |
| 소규모 5건 | 4건 완료, 1건 잔여(§3) |

### 0-3. 잘 되어 있는 부분 — 건드리지 말 것

- **curl config 파일 방식** (`backend.py:1598` 부근): 다운로드 URL·쿠키·토큰이 `--config` 파일로 이동해 `ps` 노출이 사라졌다. `umask 077`, 인용 heredoc(`<<'NASDROP_CURL_CONFIG'`), `_curl_config_value`의 제어문자 차단 + 백슬래시/따옴표 이스케이프, `trap cleanup`까지 갖췄다. 제어문자가 막혀 있어 heredoc 조기 종료도 불가능하다.
- **7-Zip 암호 처리** (`backend.py:766`): 암호를 stdin으로 전달하고, 출력에서 `replace(password, "***")`로 마스킹한다.
- **HTTPS 강제**: `CURL_HTTPS_ONLY`(`backend.py:107`)와 config 파일의 `proto`/`proto-redir`가 모든 curl 호출 경로에 적용되어 있다.
- 0.9.6 문서 §0-3에 적었던 SSRF 방어, `shlex.quote`, 압축 해제 2단 검증, 파일명 정제, 저장 경로 격리, PBKDF2, job-secrets 권한은 그대로 유지되고 있다.

---

## 1. [P1] 역방향 프록시 뒤 기본 설정에서 전체 사용자가 함께 잠긴다

**성격**: 0.9.6 §2(XFF 우회) 수정의 부작용. 새로 생긴 문제다.

**위치**: `backend.py:184`(`TRUST_FORWARDED_FOR` 기본값 `False`), `backend.py:411`(`login_block_remaining`), `README.md:175`, `README.md:353`

**동작**: `TRUST_FORWARDED_FOR=false`(기본값)에서는 `trusted_client_ip`가 항상 peer IP를 반환한다. DSM 역방향 프록시는 같은 호스트에서 돌기 때문에 **모든 클라이언트의 peer가 `127.0.0.1`이 되어 차단 버킷 하나를 공유한다.**

**재현**:

```
# 공격자가 5회 실패
for i in 1 2 3 4 5; do
  curl -s -o /dev/null -X POST http://127.0.0.1:PORT/api/login \
    -H 'content-type: application/json' -H 'x-forwarded-for: 203.0.113.66' \
    -d '{"username":"owner","password":"wrong"}'
done

# 다른 사용자가 올바른 비밀번호로 로그인
curl -s -X POST http://127.0.0.1:PORT/api/login \
  -H 'content-type: application/json' -H 'x-forwarded-for: 198.51.100.5' \
  -d '{"username":"owner","password":"correcthorse1"}'
```

관측 결과: `{"error": "로그인 시도가 너무 많습니다. 약 15분 후 다시 시도하세요.", "code": "generic_error"}`
→ **비밀번호가 맞는 정상 사용자도 15분간 로그인 불가.** 인증 없이 누구나 유발할 수 있다.

**완화책은 이미 존재하고 문서화되어 있다** (`NAS_PORTAL_TRUST_FORWARDED_FOR=true`, `README.md:353`). 문제는 기본값이 함정이라는 점과, 안내가 역방향 프록시 절 **맨 끝에 참고사항처럼** 붙어 있어 설정 절차를 따라가는 사용자가 놓치기 쉽다는 점이다.

**수정 방향** (택1 또는 병행):

1. **문서 우선(저비용)**: `README.md`의 "Configuring HTTPS with DSM Reverse Proxy" 절차 **안에** 이 변수 설정을 번호 붙은 필수 단계로 넣는다. 그리고 `README.md:175`의 "from the same client IP"에 "프록시 뒤에서 이 변수를 켜지 않으면 차단 버킷이 전체 공유된다"는 단서를 단다.
2. **동작 개선(권장)**: peer가 loopback인데 `TRUST_FORWARDED_FOR`가 꺼져 있고 `X-Forwarded-For`가 실제로 들어오는 상황을 감지하면, 기동 로그에 1회 경고를 남긴다. 사용자가 잘못된 구성을 스스로 발견할 수 있게 된다.
3. **추가 방어**: IP 버킷과 별개로 계정 단위 지수 백오프를 두고, 전역 잠금은 더 긴 실패 누적에서만 발동하도록 완화한다.

**추가할 테스트**: `TRUST_FORWARDED_FOR=false`에서 서로 다른 XFF가 같은 버킷을 쓰는지(현 동작 고정), `true`에서 분리되는지.

---

## 2. [P2] 오류 코드 미분류 24건 — 최초 계정 생성 경로가 여기 포함된다

**위치**: `backend.py:187`(`public_error_code`), `synology/web/i18n.js:141`(`error()`), `backend.py:251`(`normalize_username`), `backend.py:258`(`validate_password`)

**현황**: `raise ValueError` 94건 중 **24건(26%)** 이 어느 규칙에도 걸리지 않아 `generic_error`로 떨어진다. 한국어 UI에서는 `i18n.js:142`의 `if (language === "ko" && fallback) return String(fallback);` 덕분에 원문이 그대로 보이지만, **나머지 3개 언어는 "The request could not be completed." 한 줄로 뭉개진다.**

**가장 문제되는 것 — 제품 첫 화면**:

```
POST /api/account {"username":"owner","password":"short"}
→ {"error": "비밀번호는 10~128자로 입력하세요.", "code": "generic_error"}

POST /api/account {"username":"a","password":"correcthorse1"}
→ {"error": "ID는 영문, 숫자, 마침표, 밑줄, 하이픈을 사용해 3~32자로 입력하세요.", "code": "generic_error"}
```

영어/일본어/중국어 사용자가 README 절차대로 **최초 계정을 만드는 순간** 실패 사유를 알 수 없다.

**같은 버킷에 있는 나머지 주요 항목**:

| 메시지 | 발생 위치 | 왜 중요한가 |
|---|---|---|
| `로그인 시도가 너무 많습니다. 약 N분 후…` | `backend.py:2535` | 잠금 여부와 남은 시간이 전달되지 않는다 |
| `허용된 저장소 마운트 안의 폴더만 선택할 수 있습니다.` | `backend.py:2228` 부근 | README가 "업데이트 후 매번 기본 폴더 재선택"을 강조하는 경로 |
| `선택한 저장 폴더가 없습니다.` / `탐색할 수 없는 폴더입니다.` | 동상 | 동상 |
| `허용할 수 없는 파일 정보입니다.` | `backend.py:1910` 외 3곳 | `MAX_FILE_BYTES`(300 GiB) 초과 시 나오는 메시지 |
| `아이콘 외부 포트는 1~65535 사이의 숫자여야 합니다.` | `backend.py` 설정부 | 설정 화면 검증 실패 |

전체 24건 목록은 아래 스크립트로 재생성할 수 있다:

```python
import re, importlib.util, os, sys, tempfile
os.environ['NAS_PORTAL_STATE_DIR'] = tempfile.mkdtemp()
spec = importlib.util.spec_from_file_location('b', 'backend.py')
m = importlib.util.module_from_spec(spec); sys.modules['b'] = m; spec.loader.exec_module(m)
src = open('backend.py', encoding='utf-8').read()
msgs = sorted(set(re.findall(r'raise (?:ValueError|PasswordRequiredError)\(\s*[fr]?"([^"]{4,})"', src)))
for s in msgs:
    if m.public_error_code(s) == 'generic_error':
        print(s)
```

**수정 방향**: 코드 4~5개만 추가하면 위 표가 전부 커버된다.

| 새 코드 | 대상 | 비고 |
|---|---|---|
| `invalid_account_format` | ID/비밀번호 형식 검증 | 4개 국어 문구에 실제 규칙(3~32자 / 10~128자)을 포함시킬 것 |
| `too_many_attempts` | 로그인 차단 | 남은 분 수를 파라미터로 넘겨야 하므로, `i18n.js`의 `error()`에 치환 인자를 받는 경로가 필요하다 |
| `invalid_target_folder` | 저장 폴더 선택/탐색 실패 | 기존 `permission_denied`와 구분할 것 |
| `file_too_large` | `MAX_FILE_BYTES` 초과 | 문구에 300 GiB 상한을 명시 |
| `invalid_setting_value` | 포트·다운로드 방식 등 설정값 | `invalid_request`로 흡수해도 무방 |

각 코드는 `synology/web/i18n.js`의 4개 언어 블록(19행 en / 48행 ko / 77행 ja / 106행 zh) 모두에 추가해야 한다.

**구조적 주의사항**: `public_error_code`는 **한국어 원문 부분문자열 매칭**으로 분류한다(`backend.py:187`). 즉 메시지 문구를 조금만 손봐도 코드가 조용히 `generic_error`로 바뀐다. 회귀 방지를 위해 다음 테스트를 추가할 것을 권한다.

- `backend.py`의 모든 `raise ValueError` 문자열을 수집해 `generic_error` 비율이 기준치를 넘으면 실패시키는 Python 테스트
- `public_error_code`가 반환할 수 있는 모든 코드가 `i18n.js` 4개 언어에 존재하는지 검사하는 Node 테스트 (`tests/rendered-html.test.mjs`에 추가)

장기적으로는 문자열 매칭 대신 `raise` 지점에서 코드를 직접 지정하는 방식(예외 클래스에 `code` 속성)이 맞다. 다만 이번 릴리스 범위에서는 위 테스트로 고정하는 것으로 충분하다.

---

## 3. [P3] Pixeldrain User-Agent에 옛 버전이 남아 있다

**위치**: `backend.py:2138`

```python
headers={"User-Agent": "NAS Download Portal/0.4.2"},
```

0.9.6 감사 §8-4에서 지적한 버전 드리프트 항목이다. Buzzheavier 쪽(`backend.py:1853`)은 `f"NASDrop/{PACKAGE_VERSION}"`으로 수정됐으나 Pixeldrain 요청은 누락됐다. `0.4.2`는 현행 버전과 무관한 값이다.

**수정**: `f"NASDrop/{PACKAGE_VERSION}"`으로 통일한다. `backend.py:1928`, `backend.py:1935`의 `"Mozilla/5.0 NAS Download Portal"`은 GigaFile 호환을 위한 의도적 위장일 수 있으므로 **변경 전 확인할 것.** `GOFILE_USER_AGENT`도 마찬가지로 의도적이다.

`docs/RELEASE_CHECKLIST.md`에 "버전 문자열이 하드코딩된 곳이 없는지 확인" 항목을 추가하면 재발을 막을 수 있다.

---

## 4. 우선순위와 커밋 분할

| 우선순위 | 항목 | 규모 |
|---|---|---|
| P1 | §1 프록시 뒤 전체 잠금 | 문서 수정만으로 1차 완화 가능 |
| P2 | §2 오류 코드 24건 | 코드 4~5개 + 4개 국어 문구 + 회귀 테스트 |
| P3 | §3 Pixeldrain UA | 한 줄 |

커밋 제안 (기존 저장소의 영문 명령형 한 줄 요약 스타일 유지):

1. `Use the package version in the Pixeldrain user agent` — §3
2. `Document the shared login throttle behind a reverse proxy` — §1 문서 수정
3. `Warn when forwarded headers arrive from an untrusted proxy` — §1 동작 개선 (선택)
4. `Classify account, folder, and size validation errors` — §2 + 4개 국어 문구
5. `Test that every error code is translated in all languages` — §2 회귀 테스트

---

## 5. 미검증 항목

**릴리스 SPK의 SHA-256을 대조하지 않았다.** 파일 다운로드가 필요해 임의로 진행하지 않았다.

확인한 릴리스 메타데이터:

- 태그: `v0.9.9-1`
- 애셋: `nasdrop-0.9.9-1-x86_64.spk`
- 크기: 43,970,560 바이트

대조할 기준값: `A7CA2D649983A693C2BDEF161BECA66928DAEDCB42576A530A5788600FAD5F0D`

---

## 6. 참고

- 이 문서와 `HANDOVER-0.9.6-audit.md`는 저장소에 커밋되지 않은 untracked 파일이다. 0.9.6 문서는 모든 항목이 해결되었으므로 삭제해도 된다.
- 감사 시점 로컬 작업 트리는 `origin/main`(`ad21587`)과 동일했다.
