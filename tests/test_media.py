from array import array
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import wave

from faktanu.daily import verify_video
from faktanu.narration import espeak_command, narrate
from faktanu.pipeline import render


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise unittest.SkipTest('FFmpeg integration prerequisites missing')
        try:
            espeak_command()
        except RuntimeError:
            raise unittest.SkipTest('Install espeak-ng to run media integration tests')

    def test_swedish_narration_and_portrait_video(self):
        with tempfile.TemporaryDirectory() as root:
            audio = narrate('content/example.json', Path(root) / 'narration.wav')
            with wave.open(str(audio)) as stream:
                self.assertAlmostEqual(stream.getnframes() / stream.getframerate(), 24)
                samples = array('h', stream.readframes(stream.getnframes()))
                self.assertGreater(max(abs(sample) for sample in samples), 100)
            video = render('content/example.json', Path(root) / 'video.mp4', audio)
            verify_video(video, 24)
            self.assertTrue(json.loads(video.with_suffix('.json').read_text())['narrated'])

    def test_overlong_narration_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as root:
            plan = json.loads(Path('content/example.json').read_text())
            plan['scenes'][0]['narration'] = 'Det här är en mycket lång mening. ' * 30
            path = Path(root) / 'plan.json'
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, 'shorten narration'):
                narrate(path, Path(root) / 'narration.wav')
            self.assertFalse((Path(root) / 'narration.wav').exists())
