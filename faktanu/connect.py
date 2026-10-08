"""Desktop-only OAuth connection wizard. Never logs credential contents."""
import json
import os
from pathlib import Path
import tempfile
import tomllib
from urllib.parse import urlsplit

SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly']


def private_json(path, contents):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix='.oauth-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(contents, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def connect(client_secrets, config_path='pipeline.toml', token_file=None, settings_file=None):
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    config_path = Path(config_path).resolve(strict=True)
    config = tomllib.loads(config_path.read_text())
    channel_id = config['youtube'].get('channel_id')
    if not channel_id:
        raise ValueError('Set youtube.channel_id in the configuration first')
    client_secrets = Path(client_secrets).resolve(strict=True)
    client = json.loads(client_secrets.read_text()).get('installed')
    if not client:
        raise ValueError('Download a Desktop app OAuth client JSON, not a Web application client')
    for field, hostname in [('auth_uri', 'accounts.google.com'), ('token_uri', 'oauth2.googleapis.com')]:
        endpoint = urlsplit(client.get(field, ''))
        if endpoint.scheme != 'https' or endpoint.hostname != hostname or endpoint.username:
            raise ValueError('Use the original Desktop app client downloaded from Google Cloud')
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
    print('Opening Google login on this PC. Select sweklaus@gmail.com and the FaktaNuWorld channel.')
    credentials = flow.run_local_server(
        host='localhost', port=0, open_browser=True, timeout_seconds=300,
        access_type='offline', prompt='consent select_account',
        login_hint='sweklaus@gmail.com', authorization_prompt_message='',
        success_message='Login received. Return to the terminal for channel verification.')
    if credentials is None or not credentials.refresh_token:
        raise ValueError('Offline authorization was not completed; repeat login and consent')
    youtube = build('youtube', 'v3', credentials=credentials)
    entries = youtube.channels().list(part='id,snippet', mine=True).execute().get('items', [])
    matching = next((entry for entry in entries if entry['id'] == channel_id), None)
    if matching is None:
        raise ValueError('Selected account/channel does not match FaktaNuWorld. Existing files were preserved.')
    token = json.loads(credentials.to_json())
    fields = {name: token.get(name) for name in ['client_id', 'client_secret', 'refresh_token']}
    if not all(fields.values()):
        raise ValueError('OAuth result is incomplete; existing files were preserved')
    token_path = Path(token_file) if token_file else config_path.parent / 'secrets/token.json'
    settings_path = Path(settings_file) if settings_file else config_path.parent / 'secrets/cloud-settings.json'
    if token_path.resolve() == settings_path.resolve():
        raise ValueError('Token and cloud settings files must have different paths')
    private_json(token_path, token)
    private_json(settings_path, {
        'environment_variables': {'YOUTUBE_CHANNEL_ID': channel_id,
                                  'YOUTUBE_OAUTH_CLIENT_ID': fields['client_id']},
        'secrets': {'YOUTUBE_OAUTH_CLIENT_SECRET': fields['client_secret'],
                    'YOUTUBE_OAUTH_REFRESH_TOKEN': fields['refresh_token']}})
    result = {'channel_id': channel_id, 'channel_title': matching['snippet']['title'],
              'token_file': str(token_path), 'cloud_settings_file': str(settings_path)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('Open cloud-settings.json only on your own PC and enter its values in secure environment settings.')
    print('Do not send either file in chat or commit it. No video was uploaded.')
    return result
