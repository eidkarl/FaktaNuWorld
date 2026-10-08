"""Offline Swedish speech synthesis, padded per scene without cutting narration."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

from .pipeline import load_plan


def espeak_command():
    binary = shutil.which('espeak-ng')
    environment = os.environ.copy()
    if binary:
        return [binary], environment
    root = Path(os.environ.get('FAKTANU_TOOLS_DIR', '/workspace/.faktanu-tools')) / 'runtime'
    binary = root / 'usr/bin/espeak-ng'
    if not binary.exists():
        raise RuntimeError('Install espeak-ng or run bash scripts/bootstrap_tts.sh')
    libraries = root / 'usr/lib/x86_64-linux-gnu'
    environment['LD_LIBRARY_PATH'] = str(libraries) + (
        ':' + environment['LD_LIBRARY_PATH'] if environment.get('LD_LIBRARY_PATH') else '')
    return [str(binary), f'--path={libraries}'], environment


def narrate(plan_path, destination, voice='sv', speed=155):
    plan = load_plan(plan_path)
    if voice != 'sv' or plan.get('language') != 'sv':
        raise ValueError('The initial voice provider supports Swedish (sv) only')
    if isinstance(speed, bool) or not isinstance(speed, int) or not 100 <= speed <= 220:
        raise ValueError('Speech speed must be an integer between 100 and 220')
    command, environment = espeak_command()
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='faktanu-speech-') as work:
        segments = []
        for index, scene in enumerate(plan['scenes']):
            raw = Path(work) / f'{index}-raw.wav'
            subprocess.run(command + ['-v', voice, '-s', str(speed), '-w', str(raw), '--stdin'],
                           input=scene.get('narration', scene['text']), text=True,
                           env=environment, check=True)
            with wave.open(str(raw)) as speech:
                length = speech.getnframes() / speech.getframerate()
            # Keep a small gap at each boundary; ask for editorial timing changes rather than cut words.
            if length > scene['seconds'] - 0.15:
                raise ValueError(f'Scene {index + 1} speech needs {length:.2f}s; '
                                 f'increase seconds or shorten narration (budget {scene["seconds"]}s)')
            segment = Path(work) / f'{index}.wav'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(raw),
                            '-af', 'apad', '-t', str(scene['seconds']), '-ar', '48000', '-ac', '1',
                            '-c:a', 'pcm_s16le', str(segment)], check=True)
            segments.append(segment)
        temporary = Path(work) / 'narration.wav'
        with wave.open(str(temporary), 'wb') as joined:
            joined.setnchannels(1)
            joined.setsampwidth(2)
            joined.setframerate(48000)
            for segment in segments:
                with wave.open(str(segment)) as stream:
                    joined.writeframes(stream.readframes(stream.getnframes()))
        shutil.copyfile(temporary, destination)
    return destination
