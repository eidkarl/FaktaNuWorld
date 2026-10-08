#!/usr/bin/env python3
"""Run on the user's PC: install pinned OAuth dependencies and open the login wizard."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description='Connect FaktaNuWorld to Google on your own PC')
    parser.add_argument('--client-secrets', help='Downloaded Google Desktop app client JSON path')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error('Install Python 3.12 or newer first')
    root = Path(__file__).resolve().parent.parent
    default = root / 'secrets/client_secret.json'
    client_path = args.client_secrets or (str(default) if default.exists() else None)
    if not client_path:
        print('Create a Desktop app OAuth client in Google Cloud and download its JSON first.')
        client_path = input('Path to downloaded JSON on this PC: ').strip().strip('"')
    client_path = Path(client_path).expanduser().resolve()
    if not client_path.is_file():
        parser.error('Client JSON not found; download it from Google Cloud first')
    virtualenv = root / '.venv'
    executable = virtualenv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not executable.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(virtualenv)], check=True)
    subprocess.run([str(executable), '-m', 'pip', 'install', '--no-cache-dir',
                    '-r', str(root / 'requirements.lock')], cwd=root, check=True)
    command = [str(executable), '-m', 'faktanu.pipeline', 'connect',
               '--client-secrets', str(client_path), '--config', str(root / 'pipeline.toml')]
    subprocess.run(command, cwd=root, check=True)


if __name__ == '__main__':
    main()
