#!/usr/bin/env python3
"""Collect a bounded ComCat snapshot with no magnitude cutoff; stdlib only.

Use on a machine allowed to reach earthquake.usgs.gov. No credentials required.
Raw CSV responses are losslessly gzip-compressed. Publish only a verified snapshot.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = 'https://earthquake.usgs.gov/fdsnws/event/1/'
UTC = timezone.utc
MS = timedelta(milliseconds=1)
REQUIRED = {'time', 'latitude', 'longitude', 'depth', 'mag', 'magType', 'id', 'net',
            'updated', 'type', 'status', 'locationSource', 'magSource'}
MAPPING = {
    'id': 'event_id', 'time': 'origin_time_utc', 'longitude': 'longitude',
    'latitude': 'latitude', 'depth': 'depth_km', 'mag': 'magnitude',
    'magType': 'magnitude_type', 'type': 'event_type', 'status': 'review_status',
    'updated': 'updated_utc', 'net': 'network', 'locationSource': 'origin_source',
    'magSource': 'magnitude_source', 'horizontalError': 'horizontal_error_km',
    'depthError': 'depth_error_km', 'magError': 'magnitude_error', 'nst': 'nst',
    'gap': 'gap_deg', 'dmin': 'dmin_deg', 'rms': 'rms_s', 'magNst': 'mag_nst', 'place': 'place',
}


def iso(value):
    return value.astimezone(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def timestamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Explicit timezone required: ' + value)
    return dt.astimezone(UTC)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compressed(data):
    return gzip.compress(data, compresslevel=9, mtime=0)


def csv_bytes(rows, fields):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def parse_csv(body):
    if not body:
        return []
    reader = csv.DictReader(io.StringIO(body.decode('utf-8-sig'), newline=''), strict=True)
    if not REQUIRED.issubset(reader.fieldnames or []):
        raise ValueError('Response is not the expected ComCat CSV (possibly an error/login page)')
    try:
        rows = list(reader)
    except csv.Error as error:
        raise ValueError('Malformed or truncated CSV') from error
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError('Malformed or truncated CSV row')
    return rows


def number(value):
    if value == '':
        return None
    n = float(value)
    if not math.isfinite(n):
        raise ValueError('Non-finite numeric field')
    return n


def validate_row(row, start, end, bbox):
    if not row['id']:
        raise ValueError('Missing event id')
    t = timestamp(row['time'])
    if not start <= t <= end:
        raise ValueError('Event time outside requested inclusive interval: ' + row['id'])
    timestamp(row['updated'])
    lon, lat = number(row['longitude']), number(row['latitude'])
    w, e, s, n = bbox
    if lon is None or lat is None or not (w <= lon <= e and s <= lat <= n):
        raise ValueError('Event coordinates outside request: ' + row['id'])
    depth = number(row['depth'])
    if depth is not None and not -100 <= depth <= 1000:
        raise ValueError('Unexpected depth: ' + row['id'])
    number(row['mag'])  # missing/negative/zero magnitude are NOT discarded
    for field in ('horizontalError', 'depthError', 'magError', 'nst', 'gap', 'dmin', 'rms', 'magNst'):
        if field in row:
            number(row[field])


def is_small_medium(row):
    m = number(row['magnitude'])
    return row['event_type'] == 'earthquake' and m is not None and m < 5


def bin_magnitude(value):
    m = number(value)
    if m is None:
        return 'missing'
    for edge, label in [(2, 'lt2'), (3, '2to3'), (4, '3to4'), (5, '4to5')]:
        if m < edge:
            return label
    return 'ge5'


class Client:
    def __init__(self, delay=0.5):
        self.delay = delay

    def get(self, url):
        for attempt in range(4):
            try:
                time.sleep(self.delay)
                req = Request(url, headers={'User-Agent': 'seismic-big-pattern-public-catalog/1.0 (research snapshot)'})
                with urlopen(req, timeout=120) as response:
                    return response.read()
            except HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise
            except (URLError, TimeoutError):
                if attempt == 3:
                    raise
            time.sleep(2 ** (attempt + 1))
        raise RuntimeError('Unreachable')


class Collector:
    def __init__(self, directory, bbox, client=None, max_events=12000):
        self.directory = directory
        self.bbox = bbox
        self.client = client or Client()
        self.max_events = max_events
        self.intervals = []
        self.events = {}
        self.duplicates = []

    def url(self, method, start, end):
        w, e, s, n = self.bbox
        params = dict(starttime=iso(start), endtime=iso(end), minlongitude=w,
                      maxlongitude=e, minlatitude=s, maxlatitude=n)
        if method == 'query':
            params.update(format='csv', orderby='time-asc')
        # Deliberately no minmagnitude, maxmagnitude, eventtype, catalog, or reviewstatus.
        return API + method + '?' + urlencode(params)

    def count(self, start, end):
        body = self.client.get(self.url('count', start, end))
        result = int(body.strip())
        if result < 0:
            raise ValueError('Negative count')
        return result

    def collect(self, start, end):
        count = self.count(start, end)
        if count > self.max_events:
            if end - start < MS:
                raise RuntimeError('Too many events within one millisecond; cannot split safely')
            half_ms = (end - start) // MS // 2
            midpoint = start + half_ms * MS
            self.collect(start, midpoint)
            self.collect(midpoint + MS, end)
            return
        entry = dict(start_inclusive=iso(start), end_inclusive=iso(end), count_before=count,
                     count_url=self.url('count', start, end), query_url=self.url('query', start, end))
        if not count:
            entry.update(rows=0, count_after=0, path=None)
            self.intervals.append(entry)
            return
        for attempt in range(3):
            raw = self.client.get(entry['query_url'])
            rows = parse_csv(raw)
            after = self.count(start, end)
            if len(rows) == count == after:
                break
            if attempt == 2:
                raise RuntimeError('Catalog changed/count mismatch; refusing partial publication')
            count = self.count(start, end)
            if count > self.max_events:
                raise RuntimeError('Catalog grew beyond chunk limit; restart collection')
        ids = [r['id'] for r in rows]
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate id inside one response')
        index = len(self.intervals)
        name = f'raw/part-{index:04d}.csv.gz'
        for row in rows:
            validate_row(row, start, end, self.bbox)
            if row['id'] in self.events:
                # Disjoint intervals: duplicate ids indicate a moving catalog, not normal overlap.
                self.duplicates.append(row['id'])
                raise ValueError('Event id occurs in disjoint time windows; retry snapshot')
            normalized = {new: row.get(old, '') for old, new in MAPPING.items()}
            normalized.update(source_catalog='USGS-ComCat', source_chunk=name)
            self.events[row['id']] = normalized
        payload = compressed(raw)
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        entry.update(count_before=count, rows=len(rows), count_after=after,
                     path=name, bytes=len(payload), sha256=sha(payload),
                     response_bytes=len(raw), response_sha256=sha(raw),
                     retrieved_at_utc=iso(datetime.now(UTC)))
        self.intervals.append(entry)
        print(f"Collected {entry['start_inclusive']} .. {entry['end_inclusive']}: {len(rows)}", flush=True)


def summarize(events):
    years = defaultdict(Counter)
    mags, types, sources = Counter(), Counter(), Counter()
    for row in events:
        t = timestamp(row['origin_time_utc'])
        key = (t.year, row['event_type'], row['magnitude_type'])
        years[key]['total'] += 1
        years[key][bin_magnitude(row['magnitude'])] += 1
        mags[row['magnitude_type'] or '(missing)'] += 1
        types[row['event_type']] += 1
        sources[row['network']] += 1
    annual = []
    for (year, kind, magtype), c in sorted(years.items()):
        annual.append(dict(year=year, event_type=kind, magnitude_type=magtype,
                           **{k: c[k] for k in ['total', 'lt2', '2to3', '3to4', '4to5', 'ge5', 'missing']}))
    magnitude_values = [number(r['magnitude']) for r in events if r['magnitude'] != '']
    summary = dict(events=len(events), earthquakes=sum(r['event_type'] == 'earthquake' for r in events),
        small_medium_m_lt5=sum(is_small_medium(r) for r in events),
        missing_magnitude=sum(r['magnitude'] == '' for r in events),
        first_event_utc=min((r['origin_time_utc'] for r in events), default=None),
        last_event_utc=max((r['origin_time_utc'] for r in events), default=None),
        magnitude_min=min(magnitude_values, default=None), magnitude_max=max(magnitude_values, default=None),
        magnitude_types=dict(sorted(mags.items())), event_types=dict(sorted(types.items())),
        source_networks=dict(sorted(sources.items())))
    return summary, annual


def write_snapshot(directory, collector, start, end_exclusive, before, after):
    events = sorted(collector.events.values(), key=lambda r: (r['origin_time_utc'], r['event_id']))
    if not events or before != after or after != len(events):
        raise ValueError(f'Root count mismatch or empty snapshot: before={before}, after={after}, unique={len(events)}')
    summary, annual = summarize(events)
    fields = list(MAPPING.values()) + ['source_catalog', 'source_chunk']
    files = []
    for name, rows, columns in [
        ('events.csv.gz', events, fields),
        ('earthquakes_m_lt5.csv.gz', [r for r in events if is_small_medium(r)], fields),
        ('annual_counts.csv', annual, list(annual[0]))]:
        raw = csv_bytes(rows, columns)
        payload = compressed(raw) if name.endswith('.gz') else raw
        (directory / name).write_bytes(payload)
        files.append(dict(path=name, rows=len(rows), bytes=len(payload), sha256=sha(payload)))
    metadata = dict(schema_version=1, source='USGS ComCat FDSN Event Web Service',
        source_url=API, credit='U.S. Geological Survey; contributing networks retained in each event',
        rights_url='https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits',
        rights_note='USGS-produced information is U.S. public domain; retain third-party contributor credit and applicable rights. No blanket relicensing.',
        collected_at_utc=iso(datetime.now(UTC)), bbox_wesn=list(collector.bbox),
        start_inclusive=iso(start), end_exclusive=iso(end_exclusive),
        magnitude_filter=None, event_type_filter=None, preferred_origin_and_magnitude_only=True,
        crs='WGS84 geographic longitude/latitude (degrees)', timezone='UTC', depth_unit='km',
        root_count_before=before, root_count_after=after, duplicate_ids=collector.duplicates,
        completeness='All returned preferred events within these API filters at retrieval, NOT physical/detection completeness; not an atomic database transaction.',
        limitations=['Regional box is not a national boundary.',
                    'ComCat is not the complete China small-earthquake catalog.',
                    'Historical start bound does not imply small-event coverage since that date.',
                    'Magnitudes of different types are not homogenized; missing magnitudes remain missing.',
                    'Non-earthquake events retained in events.csv.gz; M<5 file contains earthquake type only.'],
        summary=summary, intervals=collector.intervals, derived_files=files)
    (directory / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory; existing snapshots will not be overwritten')
    parser.add_argument('--start', default='1000-01-01T00:00:00Z')
    parser.add_argument('--end-exclusive', required=True)
    parser.add_argument('--bbox', nargs=4, type=float, default=(70, 140, 0, 60), metavar=('W', 'E', 'S', 'N'))
    args = parser.parse_args()
    start, end_exclusive = timestamp(args.start), timestamp(args.end_exclusive)
    w, e, s, n = args.bbox
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        parser.error('Invalid non-dateline bounding box')
    if not start < end_exclusive or start.microsecond % 1000 or end_exclusive.microsecond % 1000:
        parser.error('Ordered timestamps at millisecond resolution are required')
    if args.output.exists():
        parser.error('Output exists: use a new snapshot directory')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # A failed run cannot leave a directory looking like a successful snapshot.
    with tempfile.TemporaryDirectory(prefix='.collect-', dir=args.output.parent) as temp:
        directory = Path(temp)
        collector = Collector(directory, args.bbox)
        end = end_exclusive - MS
        before = collector.count(start, end)
        collector.collect(start, end)
        after = collector.count(start, end)
        metadata = write_snapshot(directory, collector, start, end_exclusive, before, after)
        shutil.move(str(directory), str(args.output))
    print(json.dumps(metadata['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
