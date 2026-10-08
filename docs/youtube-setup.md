# Google OAuth와 FaktaNuWorld 채널 연결

## 사용자가 한 번 수행할 설정

1. Google Cloud Console에서 프로젝트를 만들거나 선택하고 YouTube Data API v3를 활성화합니다.
2. OAuth 동의 화면을 설정합니다. 테스트 모드라면 `sweklaus@gmail.com`을 테스트 사용자로 등록합니다.
3. OAuth 클라이언트 유형은 **Desktop app**으로 만듭니다. 다운로드한 JSON을 사용자 PC의 프로젝트 내 `secrets/client_secret.json`에 저장합니다.
4. 사용자 PC에서 이 저장소를 받아 Python 가상환경과 `requirements.lock` 의존성을 설치합니다.
5. 아래 인증 명령으로 브라우저에 로그인합니다. `sweklaus@gmail.com`에 연결된 실제 **FaktaNuWorld 채널**을 선택합니다. 브랜드 채널이 있으면 선택 결과를 확인합니다.

```sh
python -m faktanu.pipeline authorize --client-secrets secrets/client_secret.json --token-file secrets/token.json
```

이 명령은 사용자 PC에서만 브라우저와 로컬 콜백을 사용합니다. 클라우드 localhost 주소를 공개 링크로 사용하지 않습니다.
권한은 YouTube 업로드와 채널 조회입니다. OAuth 인증을 자동으로 대신할 수 없으며 비밀번호는 필요하지 않습니다.

## 채널 ID 확인

```sh
export YOUTUBE_TOKEN_FILE='secrets/token.json'
python -m faktanu.pipeline channels
```

출력의 채널 제목이 FaktaNuWorld인지 확인하고 해당 `id`를 `YOUTUBE_CHANNEL_ID`로 설정합니다.
다른 채널이 나오면 올바른 채널로 다시 인증하세요. 채널 이름과 이메일은 채널 ID가 아닙니다.

```sh
export YOUTUBE_CHANNEL_ID='확인한_채널_ID'
python -m faktanu.pipeline doctor --youtube
```

검증은 읽기 전용입니다. 인증된 채널이 설정한 ID와 일치해야 업로드가 가능합니다.

## 클라우드 환경의 비밀값으로 연결하는 방식

현재 채널 설정은 사용자가 제공한 `UCHZZmCjoEngwykhGSxDr5iQ`입니다.
OAuth로 해당 채널 접근을 검증하기 전에는 실제 채널 연결이 완료된 것이 아닙니다.

위의 사용자 PC 인증으로 생성된 token.json을 본인 PC에서 확인하고, 다음 항목을 환경 설정에 입력합니다.
파일이나 값을 채팅으로 보내지 마세요.

| 환경 항목 | 사용자 PC의 token.json 항목 | 입력 위치 |
| --- | --- | --- |
| YOUTUBE_CHANNEL_ID | 확인한 채널 ID | 환경 변수 |
| YOUTUBE_OAUTH_CLIENT_ID | client_id | 환경 변수 |
| YOUTUBE_OAUTH_CLIENT_SECRET | client_secret | 비밀값 |
| YOUTUBE_OAUTH_REFRESH_TOKEN | refresh_token | 비밀값 |

비밀값 선언의 허용 목적지는 `oauth2.googleapis.com`입니다. 이 두 값은 Google 토큰 발급 요청에만 사용합니다.
세 항목이 모두 있으면 파일 없이 메모리에서 인증합니다. 일부만 있으면 다른 파일 인증으로
조용히 전환하지 않고 설정 누락 오류를 반환합니다. 환경 값은 파일이나 로그에 저장하지 않습니다.
현재 클라우드의 프록시 치환 및 실제 Google 토큰 발급은 인증값 입력 후 검증해야 합니다.
저장된 요구사항만으로 값이 제공되거나 로그인이 완료되는 것은 아닙니다.

환경 설정을 저장해 적용한 뒤 `doctor --youtube`로 읽기 전용 검증을 하고 실제 비공개 업로드를 검증합니다.
YouTube 기본 연결 파일을 직접 전달하는 방식도 계속 지원합니다.

## 인증 파일로 연결하는 대안

운영 머신에 안전한 파일 전달·마운트 방식으로 실제 `token.json`을 제공합니다.
`YOUTUBE_TOKEN_FILE`은 그 파일의 경로이며, `YOUTUBE_CHANNEL_ID`는 비밀이 아닌 채널 식별자입니다.
계정 토큰과 클라이언트 파일을 채팅, Git, GitHub Actions 로그에 붙여 넣지 마세요.
프로젝트에서 `secrets/`, `.env`는 Git에서 제외됩니다. 토큰 파일은 인증 명령에서 권한 0600으로 생성됩니다.

현재 Google 인증 라이브러리는 실제 OAuth JSON 파일을 로컬에서 읽습니다.
HTTPS 프록시가 치환하는 placeholder secret은 이 파일 대신 사용할 수 없습니다.
환경 설정의 경로 변수만 추가하는 것으로 OAuth 인증이 완료되지는 않습니다.
클라우드에 안전한 파일 전달 수단이 없다면 먼저 인증한 사용자 PC나 개인 서버에서 실행하세요.

네트워크에는 `accounts.google.com`, `oauth2.googleapis.com`, `www.googleapis.com`이 필요합니다.
현재 클라우드 설정 초안에 추가된 도메인은 설정 저장·적용 전까지 런타임 접근을 보장하지 않습니다.

## 첫 업로드와 검토

대본 원문과 출처, 음성·영상·제목·설명을 확인한 뒤 `approved: true`로 설정하고
`daily --upload` 또는 개별 `upload` 명령으로 비공개 업로드합니다.
YouTube Studio에서 처리 완료와 재생을 확인하고, 최종 검토 후 기존 영상의 공개 범위를 공개로 바꿉니다.
같은 영상을 공개하기 위해 다시 업로드하지 않습니다.

OAuth 동의 화면의 테스트 모드는 refresh token 수명이 제한될 수 있습니다.
API 프로젝트의 검증·감사 상태에 따라 API 업로드가 비공개로 제한될 수 있습니다.
지속 운영 전에 Google의 동의 화면, API 감사, quota 정책을 계정에서 확인해야 합니다.
