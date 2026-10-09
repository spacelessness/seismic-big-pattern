#!/usr/bin/env python3
"""Restore SHA256-locked upstream files using GitHub CLI (Python stdlib only)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'data/metadata/sources.lock.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verified(path, item):
    return path.is_file() and path.stat().st_size == item['bytes'] and digest(path) == item['sha256']


def fetch(item, force=False):
    path = ROOT / item['path']
    if verified(path, item):
        print('OK', item['path'])
        return
    if path.exists() and not force:
        raise RuntimeError(f'{path}: existing file differs; inspect it before using --force')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Contents API avoids dependence on raw.githubusercontent.com. Never embed credentials.
    endpoint = item['api_url'].removeprefix('https://api.github.com/')
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            subprocess.run(['gh', 'api', endpoint, '-H', 'Accept: application/vnd.github.raw+json'],
                           stdout=stream, check=True, timeout=180)
            stream.close()
            if not verified(tmp, item):
                raise RuntimeError(f'Checksum/size mismatch: {item["id"]}; original not replaced')
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
    print('FETCHED', item['path'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-cache', action='store_true', help='Fetch city source for deterministic rebuilding')
    parser.add_argument('--include-local', action='store_true', help='Fetch GMT China to ignored data/local/')
    parser.add_argument('--acknowledge-terms', action='store_true', help='Acknowledge upstream-specific terms; not a redistribution grant')
    parser.add_argument('--force', action='store_true', help='Replace changed files only after hash-verified download')
    args = parser.parse_args()
    if args.include_local and not args.acknowledge_terms:
        parser.error('--include-local requires --acknowledge-terms; read data/local/README.md')
    for item in json.loads(LOCK.read_text())['sources']:
        if item['storage'] == 'local_only' and not args.include_local:
            continue
        if item['storage'] == 'cache_only' and not args.include_cache:
            continue
        fetch(item, args.force)


if __name__ == '__main__':
    main()
