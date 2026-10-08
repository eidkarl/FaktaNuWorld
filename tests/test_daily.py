from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from faktanu.daily import claim_day, database, load_config, run_daily, status


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        (self.root / 'content').mkdir()
        for path in Path('content').glob('*.json'):
            shutil.copy(path, self.root / 'content' / path.name)
        shutil.copy('pipeline.toml', self.root / 'pipeline.toml')
        self.config = self.root / 'pipeline.toml'
        self.now = datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc)

    def approve(self):
        path = self.root / 'content/example.json'
        plan = json.loads(path.read_text())
        plan['approved'] = True
        path.write_text(json.dumps(plan))

    def test_paths_are_relative_to_config(self):
        config = load_config(self.config)
        self.assertEqual(config['state_dir'], self.root / 'state')
        self.assertEqual(config['queue'][0], self.root / 'content/example.json')

    def test_private_policy_cannot_be_overridden(self):
        self.config.write_text(self.config.read_text().replace('privacy = "private"', 'privacy = "public"'))
        with self.assertRaisesRegex(ValueError, 'private uploads'):
            load_config(self.config)

    def test_unapproved_queue_does_not_connect_or_upload(self):
        with patch('faktanu.daily.youtube_client') as client:
            outcome = run_daily(self.config, True, self.now)
            self.assertEqual(outcome['status'], 'queue_empty')
            client.assert_not_called()

    def test_stockholm_9am_in_summer_and_winter(self):
        for before, due in [('2026-07-01T06:59:00+00:00', '2026-07-01T07:00:00+00:00'),
                            ('2026-12-01T07:59:00+00:00', '2026-12-01T08:00:00+00:00')]:
            self.assertEqual(run_daily(self.config, True, datetime.fromisoformat(before))['status'], 'not_due')
            self.assertEqual(run_daily(self.config, True, datetime.fromisoformat(due))['status'], 'queue_empty')

    def test_preflight_failure_does_not_claim_day(self):
        self.approve()
        with patch('faktanu.daily.youtube_client', side_effect=ValueError('missing token')):
            with self.assertRaisesRegex(ValueError, 'missing token'):
                run_daily(self.config, True, self.now)
        self.assertEqual(status(self.config), [])

    def test_claim_enforces_day_and_content_uniqueness_across_connections(self):
        with database(self.root / 'state') as a, database(self.root / 'state') as b:
            self.assertTrue(claim_day(a, '2026-10-08', 'item1', self.now.isoformat()))
            self.assertFalse(claim_day(b, '2026-10-08', 'item2', self.now.isoformat()))
            self.assertFalse(claim_day(b, '2026-10-09', 'item1', self.now.isoformat()))
            self.assertTrue(claim_day(b, '2026-10-09', 'item2', self.now.isoformat()))

    def test_uploaded_and_pending_days_never_repeat(self):
        for should_fail in [False, True]:
            with self.subTest(failure=should_fail), tempfile.TemporaryDirectory() as state:
                self.approve()
                self.config.write_text(self.config.read_text().replace('state_dir = "state"', f'state_dir = "{state}"'))
                with patch('faktanu.daily.youtube_client'), \
                     patch('faktanu.daily.narrate', return_value='audio.wav'), \
                     patch('faktanu.daily.render', return_value='video.mp4'), \
                     patch('faktanu.daily.verify_video'), \
                     patch('faktanu.daily.upload', return_value='youtube-id') as upload:
                    if should_fail:
                        upload.side_effect = RuntimeError('connection lost')
                        with self.assertRaises(RuntimeError):
                            run_daily(self.config, True, self.now)
                    else:
                        self.assertEqual(run_daily(self.config, True, self.now)['status'], 'uploaded')
                    self.assertEqual(run_daily(self.config, True, self.now)['status'], 'already_claimed')
                    self.assertEqual(upload.call_count, 1)
                    self.assertEqual(upload.call_args.kwargs['privacy'], 'private')
                    self.assertEqual(status(self.config)[0]['status'], 'pending' if should_fail else 'uploaded')
                # Restore state location for the next subtest.
                self.config.write_text(self.config.read_text().replace(f'state_dir = "{state}"', 'state_dir = "state"'))

    def test_preview_never_claims_or_uploads(self):
        with patch('faktanu.daily.narrate', return_value='audio.wav'), \
             patch('faktanu.daily.render', return_value='video.mp4'), \
             patch('faktanu.daily.verify_video'), \
             patch('faktanu.daily.upload') as upload:
            self.assertEqual(run_daily(self.config, False, self.now)['status'], 'preview')
            self.assertEqual(status(self.config), [])
            upload.assert_not_called()
