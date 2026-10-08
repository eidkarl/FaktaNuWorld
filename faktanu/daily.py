"""Config-driven daily execution; private upload requires explicit --upload."""
from contextlib import contextmanager
from datetime import datetime, time
import hashlib
import json
from pathlib import Path
import sqlite3
import tomllib
from zoneinfo import ZoneInfo

from .narration import narrate
from .pipeline import load_plan, render, upload, youtube_client


def load_config(path):
    path = Path(path).resolve(strict=True)
    config = tomllib.loads(path.read_text())
    if config['content']['language'] != 'sv' or config['tts']['voice'] != 'sv':
        raise ValueError('Content and voice must be Swedish (sv)')
    if config['tts']['provider'] != 'espeak-ng':
        raise ValueError('Supported TTS provider: espeak-ng')
    if config['youtube']['privacy'] != 'private':
        raise ValueError('Daily workflow requires private uploads for review')
    ZoneInfo(config['schedule']['timezone'])
    import re
    after = config['schedule']['after']
    if not isinstance(after, str) or not re.fullmatch(r'[0-2][0-9]:[0-5][0-9]', after):
        raise ValueError('Schedule after must be local HH:MM')
    time.fromisoformat(after)
    speed = config['tts']['speed']
    if type(speed) is not int or not 100 <= speed <= 220:
        raise ValueError('TTS speed must be 100–220')
    config['queue'] = [path.parent / p for p in config['content']['queue']]
    config['output_dir'] = path.parent / config['storage']['output_dir']
    config['state_dir'] = path.parent / config['storage']['state_dir']
    ids = [load_plan(p)['id'] for p in config['queue']]
    if len(ids) != len(set(ids)):
        raise ValueError('Queue content ids must be unique')
    return config


@contextmanager
def database(state):
    state.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(state / 'daily.sqlite3', timeout=30)
    try:
        connection.execute('''CREATE TABLE IF NOT EXISTS runs (
            day TEXT PRIMARY KEY, content_id TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL, video_id TEXT, created_at TEXT NOT NULL)''')
        connection.commit()
        yield connection
    finally:
        connection.close()


def claim_day(connection, day, content_id, timestamp):
    try:
        with connection:
            connection.execute('INSERT INTO runs VALUES (?, ?, ?, NULL, ?)',
                               (day, content_id, 'pending', timestamp))
        return True
    except sqlite3.IntegrityError:
        return False


def verify_video(path, seconds):
    import subprocess
    probe = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], text=True))
    streams = probe['streams']
    videos = [s for s in streams if s['codec_type'] == 'video']
    audios = [s for s in streams if s['codec_type'] == 'audio']
    if not videos or (videos[0]['width'], videos[0]['height'], videos[0]['codec_name']) != (1080, 1920, 'h264'):
        raise ValueError('Rendered video must be 1080x1920 H.264')
    if not audios or audios[0]['codec_name'] != 'aac':
        raise ValueError('Rendered video must have AAC audio')
    if abs(float(probe['format']['duration']) - seconds) > 0.2:
        raise ValueError('Rendered duration does not match the script')
    return probe


def run_daily(config_path, send=False, now=None):
    config = load_config(config_path)
    timezone = ZoneInfo(config['schedule']['timezone'])
    now = now or datetime.now(timezone)
    if now.tzinfo is None:
        raise ValueError('Use a timezone-aware clock')
    now = now.astimezone(timezone)
    day = now.date().isoformat()
    if send and now.time() < time.fromisoformat(config['schedule']['after']):
        return {'status': 'not_due', 'day': day}
    with database(config['state_dir']) as connection:
        if send and connection.execute('SELECT 1 FROM runs WHERE day = ?', (day,)).fetchone():
            return {'status': 'already_claimed', 'day': day}
        candidates = []
        for path in config['queue']:
            plan = load_plan(path)
            if send and plan.get('approved') is not True:
                continue
            if connection.execute('SELECT 1 FROM runs WHERE content_id = ?', (plan['id'],)).fetchone():
                continue
            legacy = config['state_dir'] / (hashlib.sha256(plan['id'].encode()).hexdigest() + '.json')
            if legacy.exists():
                continue
            candidates.append((path, plan))
        if not candidates:
            return {'status': 'queue_empty', 'day': day, 'upload': send}
        path, plan = candidates[0]
        client = youtube_client(config['youtube'].get('channel_id')) if send else None
        snapshot = json.dumps(plan, ensure_ascii=False, indent=2)
        fingerprint = hashlib.sha256(snapshot.encode()).hexdigest()[:12]
        # Unique run workspace prevents concurrent renders overwriting files being uploaded.
        import tempfile
        config['output_dir'].mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix=f'{day}-{fingerprint}-', dir=config['output_dir']))
        snapshot_path = output / 'plan.json'
        snapshot_path.write_text(snapshot)
        narration = narrate(snapshot_path, output / 'narration.wav',
                            config['tts']['voice'], config['tts']['speed'])
        video = render(snapshot_path, output / 'video.mp4', narration)
        verify_video(video, sum(s['seconds'] for s in plan['scenes']))
        if not send:
            return {'status': 'preview', 'day': day, 'content_id': plan['id'], 'video': str(video)}
        if not claim_day(connection, day, plan['id'], now.isoformat()):
            return {'status': 'already_claimed', 'day': day}
        # A failure retains pending state: it may have occurred after YouTube accepted the upload.
        video_id = upload(video, privacy='private', state_dir=config['state_dir'], client=client)
        with connection:
            connection.execute('UPDATE runs SET status = ?, video_id = ? WHERE day = ?',
                               ('uploaded', video_id, day))
        return {'status': 'uploaded', 'day': day, 'video_id': video_id, 'privacy': 'private'}


def status(config_path):
    config = load_config(config_path)
    with database(config['state_dir']) as connection:
        rows = connection.execute('SELECT day, content_id, status, video_id FROM runs ORDER BY day DESC').fetchall()
    return [{'day': day, 'content_id': content_id, 'status': outcome, 'video_id': video_id}
            for day, content_id, outcome, video_id in rows]


def worker(config_path, send=False, interval=300):
    """Foreground worker for an external process supervisor. No automatic publication."""
    import signal
    import threading
    if not send:
        raise ValueError('Worker requires --upload; use daily for a one-off preview')
    if not 30 <= interval <= 3600:
        raise ValueError('Worker interval must be between 30 and 3600 seconds')
    load_config(config_path)
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    while not stopped.is_set():
        try:
            print(json.dumps(run_daily(config_path, send=True)), flush=True)
        except Exception as error:
            # Avoid emitting upstream errors that could include authentication material.
            print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                              'action': 'Check runtime prerequisites and pending state before retry'}), flush=True)
        stopped.wait(interval)


def doctor(config_path, check_youtube=False):
    import os
    import shutil
    from .narration import espeak_command
    config = load_config(config_path)
    try:
        espeak_command()
        speech_ready = True
    except RuntimeError:
        speech_ready = False
    plans = [load_plan(path) for path in config['queue']]
    result = {
        'ffmpeg': bool(shutil.which('ffmpeg')),
        'ffprobe': bool(shutil.which('ffprobe')),
        'font': Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').exists(),
        'tts_available': speech_ready,
        'queue_items': len(plans),
        'approved_items': sum(plan['approved'] is True for plan in plans),
        'schedule': config['schedule'],
        'privacy': config['youtube']['privacy'],
        'channel_id_present': bool(os.environ.get('YOUTUBE_CHANNEL_ID') or config['youtube'].get('channel_id')),
        'oauth_environment_complete': all(os.environ.get(name) for name in [
            'YOUTUBE_OAUTH_CLIENT_ID', 'YOUTUBE_OAUTH_CLIENT_SECRET', 'YOUTUBE_OAUTH_REFRESH_TOKEN']),
        'oauth_token_file_present': Path(os.environ.get('YOUTUBE_TOKEN_FILE', 'secrets/token.json')).is_file(),
        'youtube_verified': False,
    }
    if check_youtube:
        youtube_client(config['youtube'].get('channel_id'))
        result['youtube_verified'] = True
    return result
