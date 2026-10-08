# FaktaNuWorld

스웨덴어 세계 상식 쇼츠를 **매일 스웨덴 시간 오전 9시 이후 비공개 업로드하고,
검토 후 공개**하는 파이프라인입니다. 현재 음성·영상 제작과 일일 실행기는 구현되어 있습니다.
실제 YouTube 연결은 운영자의 Google OAuth 인증 및 채널 ID 설정이 필요합니다.
이메일 주소만으로 채널 접근 권한이 생기지는 않습니다.

## 빠른 시작

Python 3.12+, FFmpeg/ffprobe, DejaVu Sans, eSpeak NG가 필요합니다.
Debian 클라우드에서는 권한 상승 없이 `scripts/bootstrap_tts.sh`로 eSpeak NG를 설치할 수 있습니다.
이 스크립트는 Debian 서명과 패키지 무결성 검증을 유지합니다.
Ubuntu에서는 `sudo apt-get install ffmpeg fonts-dejavu-core espeak-ng`로 설치할 수 있습니다.

```sh
cd /workspace/FaktaNuWorld
python -m venv .venv
.venv/bin/pip install --no-cache-dir -r requirements.lock
bash scripts/bootstrap_tts.sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m faktanu.pipeline doctor
.venv/bin/python -m faktanu.pipeline daily
```

`daily`는 네트워크 업로드 없이 대본 → 장면별 스웨덴어 음성 → 세로 영상 → 규격 검사를 수행합니다.
출력 JSON의 `video` 경로에서 영상을 확인할 수 있습니다. 이 미리보기 실행은 업로드 상태를 소비하지 않습니다.
기본 음성은 무료 오프라인 eSpeak NG로, 자연스러운 음성 공급자로 교체할 수 있도록 모듈을 분리했습니다.
현재 음성은 기계음에 가까워 공개 전 청취 검수가 필요합니다.

## 콘텐츠와 설정

[pipeline.toml](pipeline.toml)에 큐, 음성 속도, 시간대, 실행 시각, 저장 위치가 있습니다.
상대 경로는 설정 파일 기준입니다. 오전 9시 Europe/Stockholm은 여름·겨울 시간 변경을 자동 반영합니다.
일일 실행기는 비공개만 허용합니다.

초기 큐의 금성·달·지구 대본 3개는 **검수 전 초안**입니다. 출처 URL은 포함되어 있으나,
실시간 원문 확인과 스웨덴어 표현·발음 검수는 완료되지 않았습니다.
대본 사실 확인 후 해당 JSON의 `approved`를 `true`로 설정하면 비공개 업로드 대상이 됩니다.
이 승인은 사전 사실 검수이며, 공개 승인은 YouTube Studio에서 별도로 진행합니다.
큐는 자동으로 보충되지 않습니다. 새 대본을 추가하고 큐 목록에 등록해야 합니다.

각 대본은 15–60초, 장면별 1–20초입니다. `narration`을 별도로 지정하면 자막과 음성 문장을 다르게 만들 수 있습니다.
음성이 장면 길이를 넘으면 잘라내지 않고 오류로 알려 줍니다. 문장을 줄이거나 장면 시간을 늘리세요.

```sh
.venv/bin/python -m faktanu.pipeline validate content/example.json
.venv/bin/python -m faktanu.pipeline narrate content/example.json --output output/narration.wav
.venv/bin/python -m faktanu.pipeline render content/example.json --audio output/narration.wav --output output/preview.mp4
```

별도 녹음 파일을 `--audio`로 전달할 수도 있습니다. 음성이 없는 `render`는 무음 미리보기만 만듭니다.

## YouTube 연결과 매일 실행

[Google OAuth 설정 안내](docs/youtube-setup.md)를 따라 사용자 PC에서 인증하고 실제 FaktaNuWorld 채널 ID를 확인하세요.
채널 ID는 `UCHZZmCjoEngwykhGSxDr5iQ`로 설정했습니다. 실제 계정 연결은 OAuth 이후 검증해야 합니다.
클라우드 환경에서는 OAuth의 client ID, client secret, refresh token을 안전한 환경 설정으로 제공할 수 있습니다.
파일 방식은 `secrets/` 또는 안전한 런타임 파일 저장소를 사용합니다.

```sh
export YOUTUBE_CHANNEL_ID='실제_UC로_시작하는_채널_ID'
export YOUTUBE_TOKEN_FILE='/안전한/경로/token.json'
.venv/bin/python -m faktanu.pipeline doctor --youtube
.venv/bin/python -m faktanu.pipeline daily --upload
.venv/bin/python -m faktanu.pipeline status
```

`daily --upload`는 오전 9시 이후 아직 처리하지 않은 승인 콘텐츠 한 편만 비공개로 업로드합니다.
지속 실행 명령은 다음과 같습니다. 실제 인증과 사전 검수 없이 업로드를 활성화하지 마세요.

```sh
.venv/bin/python -m faktanu.pipeline worker --upload --interval 300
```

워커는 5분 간격으로 확인하므로 실제 시작은 오전 9시부터 약 5분 이내입니다.
오전 9시 이후 재시작하면 당일 남은 작업을 수행합니다. 누락된 과거 날짜를 한꺼번에 업로드하지 않습니다.
업로드 완료 시각은 렌더링·전송 시간에 따라 달라집니다. 정확한 9시 공개 예약 기능은 아닙니다.

[운영과 실패 복구](docs/operations.md) · [구조와 후속 구현](docs/design.md)
