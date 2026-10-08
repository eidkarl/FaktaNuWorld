import copy
import json
from pathlib import Path
import tempfile
import unittest
import os
from unittest.mock import Mock, patch
from faktanu.pipeline import load_plan, render, upload, file_hash


class PlanTests(unittest.TestCase):
    def test_valid_example(self):
        plan = load_plan('content/example.json')
        self.assertEqual(sum(s['seconds'] for s in plan['scenes']), 24)
        self.assertFalse(plan['approved'])

    def test_rejects_invalid_plans(self):
        base = load_plan('content/example.json')
        for change in [{'title': 'x' * 101}, {'sources': []}, {'scenes': []},
                       {'scenes': [{'text': 'hello', 'seconds': 61}]}]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as work:
                plan = copy.deepcopy(base)
                plan.update(change)
                path = Path(work) / 'plan.json'
                path.write_text(json.dumps(plan))
                with self.assertRaises(ValueError):
                    load_plan(path)


class UploadTests(unittest.TestCase):
    def fixture(self, root, approved=True, narrated=True):
        video = Path(root) / 'video.mp4'
        video.write_bytes(b'test-video')
        plan = load_plan('content/example.json')
        plan['approved'] = approved
        video.with_suffix('.json').write_text(json.dumps({
            'plan': plan, 'narrated': narrated, 'video_sha256': file_hash(video)}))
        return video

    def test_rejects_unreviewed_or_silent_video(self):
        for approved, narrated in [(False, True), (True, False)]:
            with tempfile.TemporaryDirectory() as root:
                video = self.fixture(root, approved, narrated)
                with self.assertRaisesRegex(ValueError, 'editorial approval'):
                    upload(video)

    def test_rejects_changed_video(self):
        with tempfile.TemporaryDirectory() as root:
            video = self.fixture(root)
            video.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                upload(video)

    def test_wrong_channel_is_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            video = self.fixture(root)
            youtube = Mock()
            youtube.channels.return_value.list.return_value.execute.return_value = {
                'items': [{'id': 'UC-other'}]}
            with patch.dict(os.environ, {'YOUTUBE_CHANNEL_ID': 'UC-expected'}), \
                 patch('google.oauth2.credentials.Credentials.from_authorized_user_file',
                       return_value=Mock(valid=True)), \
                 patch('googleapiclient.discovery.build', return_value=youtube):
                with self.assertRaisesRegex(ValueError, 'configured channel'):
                    upload(video)
                youtube.videos.assert_not_called()

    def test_upload_records_result_and_blocks_duplicates(self):
        with tempfile.TemporaryDirectory() as root:
            video = self.fixture(root)
            youtube = Mock()
            youtube.channels.return_value.list.return_value.execute.return_value = {
                'items': [{'id': 'UC-expected'}]}
            youtube.videos.return_value.insert.return_value.next_chunk.return_value = (
                None, {'id': 'test-id'})
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {'YOUTUBE_CHANNEL_ID': 'UC-expected'}), \
                     patch('google.oauth2.credentials.Credentials.from_authorized_user_file',
                           return_value=Mock(valid=True)), \
                     patch('googleapiclient.discovery.build', return_value=youtube), \
                     patch('googleapiclient.http.MediaFileUpload'):
                    upload(video)
                    with self.assertRaises(FileExistsError):
                        upload(video)
                    calls = youtube.videos.return_value.insert.call_args
                    self.assertEqual(calls.kwargs['body']['status']['privacyStatus'], 'private')
                    records = list(Path('state').glob('*.json'))
                    self.assertEqual(json.loads(records[0].read_text())['video_id'], 'test-id')
                    self.assertEqual(youtube.videos.return_value.insert.call_count, 1)
            finally:
                os.chdir(old_cwd)


if __name__ == '__main__':
    unittest.main()
