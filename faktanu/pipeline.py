import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import textwrap
import tempfile


def load_plan(path):
    plan = json.loads(Path(path).read_text())
    if not isinstance(plan.get('id'), str) or not plan['id']:
        raise ValueError('A nonempty content id is required')
    if not isinstance(plan.get('title'), str) or not 1 <= len(plan['title']) <= 100:
        raise ValueError('YouTube title must contain 1–100 characters')
    if not isinstance(plan.get('description'), str) or len(plan['description']) > 5000:
        raise ValueError('Description is required and must fit YouTube limits')
    from urllib.parse import urlsplit
    sources = plan.get('sources')
    if not isinstance(sources, list) or not sources or any(
            not isinstance(source, str) or urlsplit(source).scheme != 'https'
            or not urlsplit(source).hostname for source in sources):
        raise ValueError('HTTPS source links are required for editorial review')
    if plan.get('language') != 'sv':
        raise ValueError('Content language must be Swedish (sv)')
    if type(plan.get('approved')) is not bool:
        raise ValueError('approved must be a boolean')
    scenes = plan.get('scenes')
    if not isinstance(scenes, list) or not scenes:
        raise ValueError('At least one scene is required')
    for scene in scenes:
        if not isinstance(scene, dict):
            raise ValueError('Each scene must be an object')
        if not isinstance(scene.get('text'), str) or not scene['text'].strip():
            raise ValueError('Each scene needs text')
        if (type(scene.get('seconds')) not in (int, float) or not math.isfinite(scene['seconds'])
                or not 1 <= scene['seconds'] <= 20):
            raise ValueError('Each scene must last 1–20 seconds')
        if 'narration' in scene and (not isinstance(scene['narration'], str) or not scene['narration'].strip()):
            raise ValueError('Optional narration must contain text')
        if len(textwrap.wrap(scene['text'], width=26)) > 9:
            raise ValueError('Scene text is too long for the portrait layout')
    if not 15 <= sum(s['seconds'] for s in scenes) <= 60:
        raise ValueError('The initial format supports 15–60 seconds')
    return plan


def render(plan_path, destination, audio=None):
    plan = load_plan(plan_path)
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise RuntimeError('Install ffmpeg and ffprobe')
    font = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    if not font.exists():
        raise RuntimeError('Install fonts-dejavu-core')
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    duration = sum(s['seconds'] for s in plan['scenes'])
    if audio:
        audio = str(Path(audio).resolve(strict=True))
        probe = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                                         'format=duration', '-of', 'json', audio], text=True)
        audio_duration = float(json.loads(probe)['format']['duration'])
        if not duration - 1 <= audio_duration <= duration:
            raise ValueError(f'Narration must last {duration - 1}–{duration} seconds')
    with tempfile.TemporaryDirectory(prefix='faktanu-') as work:
        filters = []
        start = 0
        for i, scene in enumerate(plan['scenes']):
            path = Path(work) / f'scene{i}.txt'
            path.write_text('\n'.join(textwrap.wrap(scene['text'], width=26)))
            end = start + scene['seconds']
            filters.append(f"drawtext=fontfile={font}:textfile={path}:expansion=none:"
                           f"fontcolor=white:fontsize=64:line_spacing=22:x=(w-text_w)/2:"
                           f"y=(h-text_h)/2:enable='gte(t,{start})*lt(t,{end})'")
            start = end
        filters.append(f"drawtext=fontfile={font}:text=FaktaNuWorld:fontcolor=0x78dcff:"
                       "fontsize=40:x=(w-text_w)/2:y=240")
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                   '-i', f'color=c=0x102030:s=1080x1920:r=30:d={duration}']
        command += ['-i', audio] if audio else ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
        command += ['-vf', ','.join(filters), '-t', str(duration), '-c:v', 'libx264',
                    '-threads', '2', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-movflags', '+faststart', str(destination)]
        subprocess.run(command, check=True)
    manifest = {'plan': plan, 'narrated': bool(audio), 'video_sha256': file_hash(destination)}
    destination.with_suffix('.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return destination


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def authenticated_youtube():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    bindings = ['YOUTUBE_OAUTH_CLIENT_ID', 'YOUTUBE_OAUTH_CLIENT_SECRET', 'YOUTUBE_OAUTH_REFRESH_TOKEN']
    if all(os.environ.get(name) for name in bindings):
        # Proxy-bound secrets stay in memory and are sent only to Google's token endpoint.
        credentials = Credentials(
            token=None,
            client_id=os.environ['YOUTUBE_OAUTH_CLIENT_ID'],
            client_secret=os.environ['YOUTUBE_OAUTH_CLIENT_SECRET'],
            refresh_token=os.environ['YOUTUBE_OAUTH_REFRESH_TOKEN'],
            token_uri='https://oauth2.googleapis.com/token',
            scopes=['https://www.googleapis.com/auth/youtube.upload',
                    'https://www.googleapis.com/auth/youtube.readonly'])
    elif any(os.environ.get(name) for name in bindings):
        raise ValueError('OAuth environment bindings are incomplete; configure all three values')
    else:
        credentials = Credentials.from_authorized_user_file(
            os.environ.get('YOUTUBE_TOKEN_FILE', 'secrets/token.json'))
    if not credentials.valid:
        if not credentials.refresh_token:
            raise ValueError('Repeat OAuth authorization to obtain a refresh token')
        credentials.refresh(Request())
    return build('youtube', 'v3', credentials=credentials)


def youtube_client(channel_id=None):
    expected_channel = os.environ.get('YOUTUBE_CHANNEL_ID') or channel_id
    if not expected_channel:
        raise ValueError('Set YOUTUBE_CHANNEL_ID to the verified FaktaNuWorld channel ID')
    youtube = authenticated_youtube()
    channels = youtube.channels().list(part='id', mine=True).execute().get('items', [])
    if expected_channel not in [c['id'] for c in channels]:
        raise ValueError('OAuth credentials do not belong to the configured channel')
    return youtube


def channels():
    youtube = authenticated_youtube()
    entries = youtube.channels().list(part='id,snippet', mine=True).execute().get('items', [])
    return [{'id': entry['id'], 'title': entry['snippet']['title']} for entry in entries]


def upload(video, privacy='private', state_dir='state', client=None):
    # Imports stay lazy so rendering and validation need no Google credentials.
    from googleapiclient.http import MediaFileUpload
    video = Path(video).resolve(strict=True)
    manifest = json.loads(video.with_suffix('.json').read_text())
    plan = manifest['plan']
    if plan.get('approved') is not True or not manifest.get('narrated'):
        raise ValueError('Upload requires editorial approval and recorded narration')
    if file_hash(video) != manifest['video_sha256']:
        raise ValueError('Video has changed since rendering')
    youtube = client or youtube_client()
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    if privacy not in {'private', 'unlisted', 'public'}:
        raise ValueError('Invalid YouTube privacy status')
    key = hashlib.sha256(plan['id'].encode()).hexdigest()
    record = state / f'{key}.json'
    # Exclusive claim persists even on failure: ambiguous uploads require manual reconciliation.
    with record.open('x') as stream:
        json.dump({'status': 'pending', 'content_id': plan['id']}, stream)
    request = youtube.videos().insert(
        part='snippet,status',
        body={'snippet': {'title': plan['title'], 'description': plan['description'],
                          'defaultLanguage': plan.get('language', 'sv'), 'categoryId': '27'},
              'status': {'privacyStatus': privacy, 'selfDeclaredMadeForKids': False}},
        media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True))
    response = None
    while response is None:
        _, response = request.next_chunk()
    record.write_text(json.dumps({'status': 'uploaded', 'content_id': plan['id'],
                                 'video_id': response['id'], 'privacy': privacy}, indent=2))
    print(json.dumps({'video_id': response['id'], 'privacy': privacy}))
    return response['id']


def authorize(client_secrets='secrets/client_secret.json', token_file='secrets/token.json'):
    from google_auth_oauthlib.flow import InstalledAppFlow
    scopes = ['https://www.googleapis.com/auth/youtube.upload',
              'https://www.googleapis.com/auth/youtube.readonly']
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, scopes)
    credentials = flow.run_local_server(port=0, access_type='offline', prompt='consent')
    token = Path(token_file)
    token.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(credentials.to_json())
    print('Saved OAuth token; never commit secrets/')


def main():
    parser = argparse.ArgumentParser(description='FaktaNuWorld Shorts pipeline')
    commands = parser.add_subparsers(dest='command', required=True)
    validate = commands.add_parser('validate')
    validate.add_argument('plan')
    renderer = commands.add_parser('render')
    renderer.add_argument('plan')
    renderer.add_argument('--output', default='output/preview.mp4')
    renderer.add_argument('--audio')
    uploader = commands.add_parser('upload')
    uploader.add_argument('video')
    uploader.add_argument('--privacy', choices=['private', 'unlisted', 'public'], default='private')
    auth = commands.add_parser('authorize')
    auth.add_argument('--client-secrets', default='secrets/client_secret.json')
    auth.add_argument('--token-file', default='secrets/token.json')
    connector = commands.add_parser('connect')
    connector.add_argument('--client-secrets', default='secrets/client_secret.json')
    connector.add_argument('--config', default='pipeline.toml')
    speech = commands.add_parser('narrate')
    speech.add_argument('plan')
    speech.add_argument('--output', default='output/narration.wav')
    daily = commands.add_parser('daily')
    daily.add_argument('--config', default='pipeline.toml')
    daily.add_argument('--upload', action='store_true', help='Upload one approved item privately if due')
    worker = commands.add_parser('worker')
    worker.add_argument('--config', default='pipeline.toml')
    worker.add_argument('--upload', action='store_true')
    worker.add_argument('--interval', type=int, default=300)
    commands.add_parser('channels')
    diagnostic = commands.add_parser('doctor')
    diagnostic.add_argument('--config', default='pipeline.toml')
    diagnostic.add_argument('--youtube', action='store_true', help='Verify configured channel using OAuth')
    report = commands.add_parser('status')
    report.add_argument('--config', default='pipeline.toml')
    args = parser.parse_args()
    if args.command == 'validate':
        print(json.dumps(load_plan(args.plan), ensure_ascii=False, indent=2))
    elif args.command == 'render':
        print(render(args.plan, args.output, args.audio))
    elif args.command == 'upload':
        upload(args.video, args.privacy)
    elif args.command == 'connect':
        from .connect import connect
        connect(args.client_secrets, args.config)
    elif args.command == 'narrate':
        from .narration import narrate
        print(narrate(args.plan, args.output))
    elif args.command == 'daily':
        from .daily import run_daily
        print(json.dumps(run_daily(args.config, args.upload), ensure_ascii=False, indent=2))
    elif args.command == 'worker':
        from .daily import worker
        worker(args.config, args.upload, args.interval)
    elif args.command == 'channels':
        print(json.dumps(channels(), ensure_ascii=False, indent=2))
    elif args.command == 'doctor':
        from .daily import doctor
        print(json.dumps(doctor(args.config, args.youtube), ensure_ascii=False, indent=2))
    elif args.command == 'status':
        from .daily import status
        print(json.dumps(status(args.config), ensure_ascii=False, indent=2))
    else:
        authorize(args.client_secrets, args.token_file)


if __name__ == '__main__':
    main()
