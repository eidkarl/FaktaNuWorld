# Google OAuth와 FaktaNuWorld 채널 연결

## 첫 연결: 사용자 PC에서 실행

Google 계정 로그인·동의와 Google Cloud OAuth 클라이언트의 최초 생성은 사용자가 직접 합니다.
그 뒤의 의존성 설치, 로그인 창 열기, 채널 확인, 인증 파일 저장은 도우미가 처리합니다.
PC에는 Python 3.12 이상이 필요하며 인증 연결만 할 때는 FFmpeg나 TTS를 설치할 필요가 없습니다.

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 선택하거나 만듭니다.
2. [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com)를 활성화합니다.
3. [Google Auth Platform](https://console.cloud.google.com/auth/overview)에서 앱 정보와 동의 화면을 설정합니다.
   외부 앱 테스트 모드라면 Audience의 테스트 사용자에 `sweklaus@gmail.com`을 추가합니다.
4. [Clients](https://console.cloud.google.com/auth/clients)에서 OAuth 클라이언트를 생성합니다.
   유형은 **Desktop app / 데스크톱 앱**입니다. JSON 파일을 사용자 PC에 다운로드합니다.
5. GitHub의 최신 `main`을 사용자 PC에 내려받고 프로젝트 폴더에서 아래 명령을 실행합니다.

```sh
python scripts/connect_youtube.py
```

Windows에서 `python`이 없다면 `py -3 scripts/connect_youtube.py`를 사용할 수 있습니다.
도우미가 다운로드한 JSON 파일 경로를 물어봅니다. 또는 다음처럼 지정합니다.

```sh
python scripts/connect_youtube.py --client-secrets "/다운로드/폴더/client_secret.json"
```

도우미는 `.venv`를 준비하고 고정된 의존성을 설치한 뒤 브라우저를 엽니다.
`sweklaus@gmail.com`으로 로그인하여 YouTube 업로드와 채널 조회 권한에 동의하세요.
브랜드 채널이 있으면 **FaktaNuWorld** 채널을 선택합니다. 이메일 힌트만으로 계정 소유를 검증하지 않으며,
실제 인증 결과의 채널 ID가 `UCHZZmCjoEngwykhGSxDr5iQ`인지 API로 확인합니다.
로그인 제한 시간은 5분이며, 중단하거나 다른 채널을 선택하면 다시 실행할 수 있습니다.
이 과정은 업로드를 수행하거나 일일 워커를 시작하지 않습니다.

성공하면 다음 파일을 자동 저장합니다.

- `secrets/token.json`: 사용자 PC/운영 호스트의 파일 인증용 OAuth 토큰
- `secrets/cloud-settings.json`: 클라우드 환경에 입력할 변수·비밀값 항목

파일의 내용은 화면에 출력하지 않습니다. POSIX 시스템에서는 0600 권한으로 원자적으로 저장합니다.
잘못된 채널 선택이나 불완전한 인증 결과는 기존 파일을 덮어쓰지 않습니다.
자기 PC에서 `cloud-settings.json`을 열어 아래 표에 따라 환경 설정에 값을 입력하세요.
파일이나 값을 채팅에 붙여 넣지 마세요. Google 비밀번호 입력은 Google 로그인 화면에서만 합니다.

가상환경이 이미 준비돼 있다면 `python -m faktanu.pipeline connect`를 직접 사용할 수도 있습니다.
기존 저수준 `authorize` 명령은 유지하지만 채널 검증이 포함된 `connect`를 권장합니다.
클라우드 localhost 주소를 공개 링크로 쓰지 않고, 도우미는 브라우저가 있는 사용자 PC에서 실행합니다.

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

도우미가 만든 `secrets/cloud-settings.json`을 본인 PC에서 열고, 다음 항목을 환경 설정에 입력합니다.
`environment_variables`의 값은 환경 변수, `secrets`의 값은 비밀값 항목입니다.
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
