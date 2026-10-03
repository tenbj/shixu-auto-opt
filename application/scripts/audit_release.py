"""Scan Git publication candidates and optional ZIP without printing sensitive values."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
from app.config import load_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true')
    parser.add_argument('--zip', type=Path)
    args = parser.parse_args()
    load_environment()
    needles = {key: os.getenv(key, '').encode() for key in ['DB_PASSWORD', 'DB_HOST'] if os.getenv(key)}
    needles['workspace_absolute_path'] = str(REPO).encode()
    if os.getenv('SHIXU_ENV_FILE'):
        needles['private_config_path'] = os.environ['SHIXU_ENV_FILE'].encode()
    patterns = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', rb'ghp_[A-Za-z0-9]{30,}',
                rb'sx_[A-Za-z0-9_-]{43}', rb'github_pat_[A-Za-z0-9_]{50,}', rb'(?<![A-Za-z])sk-[A-Za-z0-9_-]{25,}']
    command = ['git', 'ls-files', '-z'] if args.staged else ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z']
    paths = subprocess.check_output(command, cwd=REPO).decode('utf-8').split('\0')
    findings = []

    def scan(name, data):
        parts = Path(name).parts
        if any(p in {'private', 'runtime', '.venv', '__pycache__', '.pytest_cache', '.git'} for p in parts):
            findings.append(name + ': excluded directory')
        if Path(name).name.startswith('frp-public.') or (Path(name).name.startswith('.env') and Path(name).name != '.env.example'):
            findings.append(name + ': private artifact')
        if Path(name).suffix.lower() in {'.sqlite3', '.db', '.log', '.pyc', '.pem', '.key'}:
            findings.append(name + ': private/runtime file type')
        for label, needle in needles.items():
            if needle and needle in data:
                findings.append(name + ': ' + label)
        if any(re.search(pattern, data) for pattern in patterns):
            findings.append(name + ': credential signature')

    for path in filter(None, paths):
        data = subprocess.check_output(['git', 'show', ':' + path], cwd=REPO) if args.staged else (REPO / path).read_bytes()
        scan(path, data)
    zip_count = 0
    if args.zip:
        with zipfile.ZipFile(args.zip) as bundle:
            for name in bundle.namelist():
                if not name.endswith('/'):
                    scan(name, bundle.read(name))
                    zip_count += 1
    report = {'passed': not findings, 'git_scope': 'index' if args.staged else 'tracked-and-nonignored-candidates',
              'git_files': len(list(filter(None, paths))), 'zip_files': zip_count, 'findings': findings,
              'known_secret_values_printed': False}
    print(json.dumps(report, ensure_ascii=False))
    if findings:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
