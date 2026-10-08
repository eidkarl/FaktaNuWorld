# FaktaNuWorld

매일 YouTube Shorts를 제작하고 FaktaNuWorld 채널에 업로드하기 위한 초기 파이프라인입니다.
현재 구현은 검수 가능한 JSON 대본, 세로 영상 렌더링, 녹음 파일 결합, OAuth 인증,
채널 확인, 비공개 기본 업로드 및 중복 업로드 방지를 지원합니다.
자동 주제 수집, 생성형 AI 대본/TTS, 매일 예약 실행은 다음 구현 단계입니다.

## 설치와 로컬 실행

Python 3.12+, FFmpeg/ffprobe, DejaVu Sans가 필요합니다.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m faktanu.pipeline validate content/example.json
.venv/bin/python -m faktanu.pipeline render content/example.json --output output/preview.mp4
```

콘텐츠 방향은 스웨덴어 세계 상식입니다. 예제는 아직 검수되지 않았습니다. 오디오가 없으면 무음 검토용 영상만 생성합니다.
`scenes`의 합계는 15–60초, 각 장면은 1–20초입니다. 실제 제작에는 장면 길이에 맞춘 음성이 필요합니다.
예제의 경우 23–24초 녹음 파일을 `--audio narration.wav`로 전달합니다.
출처 확인, 대본·발음·영상 검수를 완료한 후 JSON의 `approved`를 `true`로 설정하고 다시 렌더링하세요.

## YouTube 연결

Google Cloud에서 YouTube Data API v3를 활성화하고 Desktop app OAuth 클라이언트를 만듭니다.
다운로드한 클라이언트 파일은 `secrets/client_secret.json`에만 보관합니다.
로컬 PC에서 의존성을 설치한 뒤 `python -m faktanu.pipeline authorize`를 실행하고
`sweklaus@gmail.com`으로 로그인하여 실제 FaktaNuWorld 채널을 선택하세요.
브랜드 채널이 있다면 올바른 채널을 선택해야 합니다. 이메일은 채널 ID가 아닙니다.
생성된 토큰은 안전한 런타임 저장소로 전달하고 Git에 올리지 마세요.
클라우드 환경에서 localhost 인증 링크를 공개하지 마세요.

```sh
export YOUTUBE_CHANNEL_ID='실제_UC로_시작하는_채널_ID'
export YOUTUBE_TOKEN_FILE='/안전한/경로/token.json'
.venv/bin/python -m faktanu.pipeline upload output/preview.mp4
```

사용자가 선택한 기본값은 비공개(`private`)입니다. 업로드 후 YouTube Studio에서 영상·음성·제목·설명을 검토한 다음 공개로 전환하세요.
공개 전환을 위해 같은 영상을 다시 업로드하지 마세요. `--privacy public`은 검토를 이미 완료한 경우에만 명시적으로 사용합니다.
검수 승인과 음성이 없으면 업로드가 거절됩니다. 실제 영상의 채널과 검수는 운영자의 책임입니다.
API 프로젝트의 검증 상태에 따라 업로드가 비공개로 제한될 수 있습니다.
OAuth 동의 화면이 테스트 모드이면 refresh token 수명이 제한될 수 있어 운영 전 확인해야 합니다.

`state/`는 콘텐츠 ID별 업로드 상태를 보존합니다. 여러 실행 환경을 사용하면 공유 영속 저장소가 필요합니다.
실패한 업로드는 `pending` 상태를 유지합니다. YouTube Studio에서 업로드 여부를 확인한 뒤에만
해당 상태 파일을 수동 처리하세요. 자동 재시도는 중복 업로드를 유발할 수 있습니다.

[설계와 운영 계획](docs/design.md)
