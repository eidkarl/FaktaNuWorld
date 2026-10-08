from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from faktanu.connect import connect


class ConnectTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.client = self.root / 'client.json'
        self.client.write_text(json.dumps({'installed': {
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token'}}))
        self.config = self.root / 'pipeline.toml'
        self.config.write_text('[youtube]\nchannel_id="UC-expected"\n')
        self.credentials = Mock(refresh_token='synthetic-refresh')
        self.credentials.to_json.return_value = json.dumps({
            'client_id': 'synthetic-client-id', 'client_secret': 'synthetic-client-secret',
            'refresh_token': 'synthetic-refresh', 'token': 'synthetic-access'})
        self.flow = Mock()
        self.flow.run_local_server.return_value = self.credentials
        self.youtube = Mock()
        self.youtube.channels.return_value.list.return_value.execute.return_value = {
            'items': [{'id': 'UC-expected', 'snippet': {'title': 'FaktaNuWorld'}}]}

    def run_wizard(self):
        with patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file', return_value=self.flow), \
             patch('googleapiclient.discovery.build', return_value=self.youtube), \
             redirect_stdout(io.StringIO()) as output:
            result = connect(self.client, self.config)
        return result, output.getvalue()

    def test_correct_channel_saves_private_files_without_logging_secrets(self):
        result, output = self.run_wizard()
        token = Path(result['token_file'])
        settings = Path(result['cloud_settings_file'])
        self.assertEqual(json.loads(token.read_text())['refresh_token'], 'synthetic-refresh')
        self.assertEqual(json.loads(settings.read_text())['environment_variables']['YOUTUBE_CHANNEL_ID'], 'UC-expected')
        if os.name != 'nt':
            self.assertEqual(token.stat().st_mode & 0o777, 0o600)
            self.assertEqual(settings.stat().st_mode & 0o777, 0o600)
        for secret in ['synthetic-client-secret', 'synthetic-refresh', 'synthetic-access']:
            self.assertNotIn(secret, output)
        arguments = self.flow.run_local_server.call_args.kwargs
        self.assertTrue(arguments['open_browser'])
        self.assertEqual(arguments['login_hint'], 'sweklaus@gmail.com')
        self.assertEqual(arguments['timeout_seconds'], 300)
        self.youtube.videos.assert_not_called()

    def test_wrong_channel_preserves_existing_token(self):
        secrets = self.root / 'secrets'
        secrets.mkdir()
        token = secrets / 'token.json'
        token.write_text('existing-token')
        self.youtube.channels.return_value.list.return_value.execute.return_value = {'items': []}
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.run_wizard()
        self.assertEqual(token.read_text(), 'existing-token')
        self.assertFalse((secrets / 'cloud-settings.json').exists())

    def test_no_refresh_token_saves_nothing(self):
        self.credentials.refresh_token = None
        with self.assertRaisesRegex(ValueError, 'Offline authorization'):
            self.run_wizard()
        self.assertFalse((self.root / 'secrets').exists())

    def test_non_google_endpoints_are_rejected_before_login(self):
        value = json.loads(self.client.read_text())
        value['installed']['token_uri'] = 'https://example.org/token'
        self.client.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'original Desktop app'):
            self.run_wizard()
        self.flow.run_local_server.assert_not_called()

    def test_web_client_is_rejected_before_login(self):
        self.client.write_text('{"web": {}}')
        with self.assertRaisesRegex(ValueError, 'Desktop app'):
            self.run_wizard()
        self.flow.run_local_server.assert_not_called()
