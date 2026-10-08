import argparse
import hashlib
import json
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
    if not plan.get('sources'):
        raise ValueError('Source links are required for editorial review')
    scenes = plan.get('scenes')
    if not isinstance(scenes, list) or not scenes:
        raise ValueError('At least one scene is required')
    for scene in scenes:
        if not isinstance(scene.get('text'), str) or not scene['text'].strip():
            raise ValueError('Each scene needs text')
        if not isinstance(scene.get('seconds'), (int, float)) or not 1 <= scene['seconds'] <= 20:
            raise ValueError('Each scene must last 1–20 seconds')
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


def upload(video, privacy='private'):
    # Imports stay lazy so rendering and validation need no Google credentials.
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    video = Path(video).resolve(strict=True)
    manifest = json.loads(video.with_suffix('.json').read_text())
    plan = manifest['plan']
    if plan.get('approved') is not True or not manifest.get('narrated'):
        raise ValueError('Upload requires editorial approval and recorded narration')
    if file_hash(video) != manifest['video_sha256']:
        raise ValueError('Video has changed since rendering')
    expected_channel = os.environ.get('YOUTUBE_CHANNEL_ID')
    if not expected_channel:
        raise ValueError('Set YOUTUBE_CHANNEL_ID to the verified FaktaNuWorld channel ID')
    credentials = Credentials.from_authorized_user_file(os.environ.get('YOUTUBE_TOKEN_FILE', 'secrets/token.json'))
    if not credentials.valid:
        if not credentials.refresh_token:
            raise ValueError('Repeat OAuth authorization to obtain a refresh token')
        credentials.refresh(Request())
    youtube = build('youtube', 'v3', credentials=credentials)
    channels = youtube.channels().list(part='id', mine=True).execute().get('items', [])
    if expected_channel not in [c['id'] for c in channels]:
        raise ValueError('OAuth credentials do not belong to the configured channel')
    state = Path('state')
    state.mkdir(exist_ok=True)
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


def authorize():
    from google_auth_oauthlib.flow import InstalledAppFlow
    scopes = ['https://www.googleapis.com/auth/youtube.upload',
              'https://www.googleapis.com/auth/youtube.readonly']
    flow = InstalledAppFlow.from_client_secrets_file('secrets/client_secret.json', scopes)
    credentials = flow.run_local_server(port=0, access_type='offline', prompt='consent')
    token = Path('secrets/token.json')
    token.parent.mkdir(exist_ok=True)
    token.write_text(credentials.to_json())
    token.chmod(0o600)
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
    commands.add_parser('authorize')
    args = parser.parse_args()
    if args.command == 'validate':
        print(json.dumps(load_plan(args.plan), ensure_ascii=False, indent=2))
    elif args.command == 'render':
        print(render(args.plan, args.output, args.audio))
    elif args.command == 'upload':
        upload(args.video, args.privacy)
    else:
        authorize()


if __name__ == '__main__':
    main()
