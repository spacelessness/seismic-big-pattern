#!/usr/bin/env python3
"""Offline verification of acquired earthquake catalogs and their provenance."""
import argparse
import csv
import gzip
import io
import json
from pathlib import Path

from collect_usgs_catalog import (MAPPING, MS, is_small_medium, parse_csv, sha,
                                  summarize, timestamp, validate_row)
from collect_zenodo_catalogs import verify as verify_zenodo

ROOT = Path(__file__).resolve().parents[1]


def read_derived(path):
    body = path.read_bytes()
    if path.suffix == '.gz':
        body = gzip.decompress(body)
    return list(csv.DictReader(io.StringIO(body.decode('utf-8'), newline='')))


def verify_usgs(directory):
    m = json.loads((directory / 'manifest.json').read_text())
    start = timestamp(m['start_inclusive'])
    end = timestamp(m['end_exclusive']) - MS
    previous_end = start - MS
    events = {}
    for item in m['intervals']:
        a, b = timestamp(item['start_inclusive']), timestamp(item['end_inclusive'])
        if a != previous_end + MS or b < a:
            raise ValueError('Missing/overlapping query interval')
        previous_end = b
        if item['rows'] != item['count_before'] or item['rows'] != item['count_after']:
            raise ValueError('Chunk counts disagree')
        if item['path'] is None:
            if item['rows'] != 0:
                raise ValueError('Missing nonempty chunk')
            continue
        payload = (directory / item['path']).read_bytes()
        raw = gzip.decompress(payload)
        if sha(payload) != item['sha256'] or len(payload) != item['bytes']:
            raise ValueError('Compressed chunk checksum/size mismatch')
        if sha(raw) != item['response_sha256'] or len(raw) != item['response_bytes']:
            raise ValueError('Original response checksum/size mismatch')
        rows = parse_csv(raw)
        if len(rows) != item['rows']:
            raise ValueError('CSV row count mismatch')
        for row in rows:
            validate_row(row, a, b, m['bbox_wesn'])
            if row['id'] in events:
                raise ValueError('Duplicate event ID')
            event = {new: row.get(old, '') for old, new in MAPPING.items()}
            event.update(source_catalog='USGS-ComCat', source_chunk=item['path'])
            events[row['id']] = event
    if previous_end != end:
        raise ValueError('Query intervals do not cover the requested endpoint')
    if len(events) != m['root_count_before'] or len(events) != m['root_count_after']:
        raise ValueError('Total API/unique counts disagree')
    ordered = sorted(events.values(), key=lambda r: (r['origin_time_utc'], r['event_id']))
    summary, annual = summarize(ordered)
    if summary != m['summary']:
        raise ValueError('Summary does not reproduce')
    expected = {'events.csv.gz': ordered,
                'earthquakes_m_lt5.csv.gz': [r for r in ordered if is_small_medium(r)],
                'annual_counts.csv': [{k: str(v) for k, v in r.items()} for r in annual]}
    if set(expected) != {i['path'] for i in m['derived_files']}:
        raise ValueError('Unexpected derivative inventory')
    for item in m['derived_files']:
        path = directory / item['path']
        if sha(path.read_bytes()) != item['sha256'] or path.stat().st_size != item['bytes']:
            raise ValueError('Derived checksum/size mismatch')
        rows = read_derived(path)
        if len(rows) != item['rows'] or rows != expected[item['path']]:
            raise ValueError('Derived content does not reproduce from raw chunks')
    if m['magnitude_filter'] is not None or m['event_type_filter'] is not None:
        raise ValueError('Unexpected collection filter')
    print(f"Verified USGS: {len(events)} unique events; {summary['small_medium_m_lt5']} earthquakes M<5")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--usgs', type=Path)
    parser.add_argument('--all', action='store_true', help='Require all collected catalog families')
    args = parser.parse_args()
    if args.all:
        verify_zenodo(ROOT / 'data/catalogs/zenodo')
        paths = sorted((ROOT / 'data/catalogs/usgs').glob('*/manifest.json'))
        if not paths:
            raise ValueError('No USGS snapshot')
        for path in paths:
            verify_usgs(path.parent)
    elif args.usgs:
        verify_usgs(args.usgs)
    else:
        parser.error('Specify --all or --usgs PATH')


if __name__ == '__main__':
    main()
