# DSM 런처 이름 지침

## 반복된 문제

DSM 데스크톱 아이콘 아래에 앱 이름 대신 `nasdrop:title`이 그대로 표시된 적이 있다. DSM 7은 데스크톱 앱을 열기 전에는 패키지의 다국어 문자열을 아직 불러오지 않을 수 있으므로, 브랜드명을 i18n 키로 지정하면 이 문제가 다시 발생할 수 있다.

## 고정 규칙

- `synology/package-inner/ui/config`의 `title`은 항상 문자열 `NASDrop`이어야 한다.
- `title`에 `nasdrop:title` 또는 다른 번역 키를 사용하지 않는다. NASDrop은 언어에 따라 바뀌지 않는 브랜드명이다.
- 다국어 설명을 사용할 때는 `"texts": "texts"`를 유지하고 `nasdrop:desc`를 `preloadTexts`에 넣는다.
- 소스 파일 검사만으로 끝내지 않는다. SPK 안의 `package.tgz`에 포함된 `ui/config`도 같은 규칙을 만족해야 빌드가 성공하도록 한다.
- 버전 변경 시 DSM과 브라우저 캐시를 고려해 정적 자산 버전도 함께 올린다.

## 필수 회귀 확인

- 새 설치 직후 앱을 열기 전에도 아이콘 이름이 `NASDrop`이다.
- 앱을 한 번 연 뒤에도 이름이 바뀌거나 번역 키로 노출되지 않는다.
- DSM 새로고침, 로그아웃·로그인 후에도 `NASDrop`으로 표시된다.
- Package Center의 표시 이름과 DSM 데스크톱 아이콘 이름이 모두 `NASDrop`이다.
- 빌드 검증이 `nasdrop:title`을 런처 제목으로 사용한 SPK를 거부한다.

GigaFile 파일명 회귀 규칙은 별도 문서인 `docs/PROVIDER_FILENAME_GUIDE.md`를 따른다. 두 규칙 모두 저장소 루트 `AGENTS.md`의 필수 구현 불변 조건이다.
