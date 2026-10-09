#!/usr/bin/env python3
"""Archive explicitly CC-BY-4.0 regional earthquake catalogs, pinned by record/file/MD5.

No waveform or GNSS bundles are fetched. Source numeric records remain unmodified.
Timezones and magnitude definitions not documented by a source are NOT guessed.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlparse

from collect_usgs_catalog import Client, compressed, iso, datetime, UTC, sha

SOURCES = [
    dict(record=21787957, directory='sichuan_ai_2019_2020_v2',
         filename='seismic_catalog_for_Sichuan_Province_20260804.tsv',
         md5='98a976235f67af3e183908cbc3853b0f', size=26949766,
         kind='AI-derived research catalog, NOT the official routine CENC bulletin'),
    dict(record=5602183, directory='sichuan_2013_2018', filename='catalog2013_2018_update.txt',
         md5='05d4c43c493c71250eb73e2cd811df7b', size=None,
         kind='Researcher-published regional catalog; source description sparse'),
    dict(record=14525785, directory='qinghai_tibet_1970_2022',
         filename='The Qinghai-Tibet Plateau earthquake catalog (1970–2022).xlsx',
         md5='c55d9b130514a46579d25b2cc0836e17', size=None,
         kind='Researcher-published CENC-derived regional subset, NOT a direct official nationwide download'),
]


def safe_file_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'zenodo.org':
        raise ValueError('Unexpected download host/scheme in metadata')
    return url


def collect_one(source, base, client):
    target = base / source['directory']
    if target.exists():
        raise ValueError(f'Existing snapshot will not be overwritten: {target}')
    api = f"https://zenodo.org/api/records/{source['record']}"
    record = json.loads(client.get(api))
    meta = record['metadata']
    if str(record['id']) != str(source['record']):
        raise ValueError('Record ID mismatch')
    if meta.get('access_right') != 'open' or meta.get('license', {}).get('id') != 'cc-by-4.0':
        raise ValueError('Explicit CC-BY-4.0/open access no longer confirmed; refusing redistribution')
    file = next(f for f in record['files'] if f['key'] == source['filename'])
    if file['checksum'] != 'md5:' + source['md5'] or file['size'] > 35_000_000:
        raise ValueError('Checksum changed or unexpected oversized file')
    if source['size'] is not None and file['size'] != source['size']:
        raise ValueError('Pinned size mismatch')
    url = safe_file_url(file['links']['self'])
    body = client.get(url)
    if len(body) != file['size'] or hashlib.md5(body).hexdigest() != source['md5']:
        raise ValueError('Downloaded file size/MD5 mismatch')
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.zenodo-', dir=base) as temp:
        directory = Path(temp)
        is_excel = source['filename'].endswith('.xlsx')
        name = source['filename'] + ('' if is_excel else '.gz')
        payload = body if is_excel else compressed(body)
        (directory / name).write_bytes(payload)
        result = dict(schema_version=1, record_id=source['record'], doi=record['doi'],
            source_url=f"https://zenodo.org/records/{source['record']}", api_url=api,
            title=meta['title'], creators=meta['creators'], publication_date=meta['publication_date'],
            description=meta.get('description', ''), source_kind=source['kind'],
            license='CC-BY-4.0', license_url='https://creativecommons.org/licenses/by/4.0/',
            retrieved_at_utc=iso(datetime.now(UTC)), source_filename=source['filename'],
            download_url=url, source_bytes=len(body), source_md5=source['md5'], source_sha256=sha(body),
            path=name, bytes=len(payload), sha256=sha(payload),
            transformation='none' if is_excel else 'lossless gzip only; decompressed bytes equal the original',
            original_timezone='not assumed; inspect source documentation',
            original_coordinate_datum='not assumed; inspect source documentation',
            original_magnitude_type='see source; no conversion or inferred uniform scale',
            header_preview=None if is_excel else body.decode('utf-8-sig').splitlines()[0],
            nonblank_line_count=None if is_excel else sum(bool(x.strip()) for x in body.splitlines()))
        (directory / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        shutil.move(str(directory), str(target))
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


def verify(base):
    total = 0
    for manifest in sorted(base.glob('*/manifest.json')):
        m = json.loads(manifest.read_text())
        payload = (manifest.parent / m['path']).read_bytes()
        if len(payload) != m['bytes'] or sha(payload) != m['sha256']:
            raise ValueError('Stored checksum mismatch: ' + str(manifest))
        body = gzip.decompress(payload) if m['path'].endswith('.gz') else payload
        if sha(body) != m['source_sha256'] or hashlib.md5(body).hexdigest() != m['source_md5']:
            raise ValueError('Decompressed checksum mismatch: ' + str(manifest))
        if len(body) != m['source_bytes'] or m['license'] != 'CC-BY-4.0':
            raise ValueError('Size/license mismatch')
        total += 1
    if total != len(SOURCES):
        raise ValueError(f'Expected {len(SOURCES)} regional sources; found {total}')
    print(f'Verified {total} pinned regional catalogs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/catalogs/zenodo'))
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if not args.verify:
        client = Client()
        for source in SOURCES:
            # Resumption only accepts existing files when the final verifier succeeds.
            if not (args.output / source['directory']).exists():
                collect_one(source, args.output, client)
    verify(args.output)


if __name__ == '__main__':
    main()
