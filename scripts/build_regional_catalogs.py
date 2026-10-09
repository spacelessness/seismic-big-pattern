#!/usr/bin/env python3
"""Build per-source CSVs without inventing timezone, datum, or magnitude conversions.

This is a schema-specific reader for the three locked source versions, not a generic
Excel/earthquake importer. Unknown timezones produce an EMPTY UTC column.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import gzip
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from collect_usgs_catalog import compressed, csv_bytes, iso, number, sha
from collect_zenodo_catalogs import SOURCES, verify

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/catalogs/zenodo'
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
FIELDS = ['source_record_id', 'source_row_number', 'origin_time_source', 'origin_time_utc',
          'timezone_status', 'source_time_serial', 'longitude', 'latitude', 'depth_value',
          'depth_unit', 'magnitude', 'magnitude_type', 'rms_source', 'err_ns_source',
          'err_ew_source', 'err_depth_source', 'nrec_source', 'location', 'source_id']


def local_time(year, month, day, hour, minute, seconds):
    # Validate the calendar; do not silently carry invalid second/minute values.
    sec = Decimal(seconds)
    if not sec.is_finite() or not 0 <= sec < 60:
        raise ValueError('Unexpected second value; retain source and review leap/invalid times')
    dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
    return dt + timedelta(microseconds=int(sec * 1000000))


def local_iso(dt):
    return dt.isoformat(timespec='milliseconds')


def excel_datetime(serial):
    # The pinned workbook uses the Excel 1900 system; dates are all post-1970.
    # Round numerical spreadsheet time noise to a millisecond; serial is retained.
    value = Decimal(serial)
    if not value.is_finite() or value < 25569:
        raise ValueError('Unexpected Excel date range')
    ms = int((value * Decimal(86400000)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return datetime(1899, 12, 30) + timedelta(milliseconds=ms)


def workbook_rows(path):
    with ZipFile(path) as z:
        workbook = ET.fromstring(z.read('xl/workbook.xml'))
        props = workbook.find('m:workbookPr', NS)
        if props is not None and props.get('date1904') in ('1', 'true'):
            raise ValueError('Unexpected Excel 1904 epoch')
        if len(workbook.findall('m:sheets/m:sheet', NS)) != 1:
            raise ValueError('Expected one sheet in the pinned workbook')
        strings = [''.join(t.text or '' for t in item.findall('.//m:t', NS))
                   for item in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS)]
        root = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        for row in root.findall('m:sheetData/m:row', NS):
            cells = {}
            for cell in row:
                if cell.find('m:f', NS) is not None:
                    raise ValueError('Unexpected formula in source workbook')
                column = ''.join(c for c in cell.get('r', '') if c.isalpha())
                value = cell.find('m:v', NS)
                if value is None:
                    value = ''.join(t.text or '' for t in cell.findall('.//m:t', NS))
                else:
                    value = strings[int(value.text)] if cell.get('t') == 's' else value.text
                cells[column] = value or ''
            if not any(cells.values()):
                continue
            if set(cells) - set('ABCDEFGH'):
                raise ValueError('Unexpected columns in source workbook')
            yield int(row.get('r')), [cells.get(c, '') for c in 'ABCDEFGH']


def regional_number(value):
    # Observed missing-value token in the locked workbook: a bare '-' (depth).
    # Preserved verbatim in catalog.csv.gz; treated as missing (never zero) here.
    if value in ('', '-'):
        return None
    return number(value)


def empty_row(record_id, row_number):
    row = dict.fromkeys(FIELDS, '')
    row.update(source_record_id=f'zenodo.{record_id}:row{row_number}',
               source_row_number=str(row_number), source_id=f'zenodo.{record_id}',
               timezone_status='unspecified_in_source_do_not_assume_UTC', depth_unit='unspecified')
    return row


def source_rows(directory, manifest):
    source = directory / manifest['path']
    record_id = manifest['record_id']
    if record_id == 14525785:
        iterator = iter(workbook_rows(source))
        _, header = next(iterator)
        expected = ['No.', 'Time (UTC+8)', 'Longitude (°)', 'Latitude (°)', 'Depth (km)',
                    'Magnitude', 'Magnitude Type', 'Location']
        if header != expected:
            raise ValueError('Unexpected workbook header')
        for index, cells in iterator:
            r = empty_row(record_id, index)
            dt = excel_datetime(cells[1])
            r.update(origin_time_source=local_iso(dt),
                     origin_time_utc=iso(dt.replace(tzinfo=timezone(timedelta(hours=8)))),
                     timezone_status='UTC+08:00_per_workbook_header', source_time_serial=cells[1],
                     longitude=cells[2], latitude=cells[3], depth_value=cells[4], depth_unit='km',
                     magnitude=cells[5], magnitude_type=cells[6], location=cells[7])
            yield r
    else:
        lines = gzip.decompress(source.read_bytes()).decode('utf-8-sig').splitlines()
        for index, line in enumerate(lines, 1):
            if not line.strip():
                continue
            values = line.split()
            r = empty_row(record_id, index)
            if record_id == 21787957:
                if index == 1:
                    if values != ['Date', 'Time', 'LAT', 'LON', 'DEP', 'MAG', 'RMS', 'ERR_NS', 'ERR_EW', 'ERR_dep', 'NREC']:
                        raise ValueError('Unexpected AI catalog header')
                    continue
                if len(values) != 11:
                    raise ValueError(f'Unexpected AI source row {index}')
                dt = local_time(*values[0].split('/'), *values[1].split(':'))
                r.update(origin_time_source=local_iso(dt), latitude=values[2], longitude=values[3],
                         depth_value=values[4], magnitude=values[5], magnitude_type='ML',
                         rms_source=values[6], err_ns_source=values[7], err_ew_source=values[8],
                         err_depth_source=values[9], nrec_source=values[10])
            elif record_id == 5602183:
                if len(values) != 10:
                    raise ValueError(f'Unexpected regional source row {index}')
                dt = local_time(*values[:6])
                r.update(origin_time_source=local_iso(dt), latitude=values[6], longitude=values[7],
                         depth_value=values[8], magnitude=values[9])
            else:
                raise ValueError('Unknown source schema')
            yield r


def analyze(rows):
    annual = Counter()
    magtypes = Counter()
    bins = Counter()
    magnitudes, depths, lons, lats, times = [], [], [], [], []
    exact = set()
    duplicate_records = 0
    missing_depth = 0
    for row in rows:
        lon, lat = number(row['longitude']), number(row['latitude'])
        if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError('Invalid coordinates: ' + row['source_record_id'])
        lons.append(lon)
        lats.append(lat)
        magnitude, depth = regional_number(row['magnitude']), regional_number(row['depth_value'])
        if magnitude is not None:
            magnitudes.append(magnitude)
        if depth is not None:
            depths.append(depth)
        else:
            missing_depth += 1
        bins['missing' if magnitude is None else 'negative' if magnitude < 0 else 'zero' if magnitude == 0 else '0to2' if magnitude < 2 else '2to3' if magnitude < 3 else '3to4' if magnitude < 4 else '4to5' if magnitude < 5 else 'ge5'] += 1
        magtypes[row['magnitude_type'] or '(unspecified)'] += 1
        dt = datetime.fromisoformat(row['origin_time_source'])
        times.append(row['origin_time_source'])
        annual[dt.year] += 1
        for field in ['rms_source', 'err_ns_source', 'err_ew_source', 'err_depth_source', 'nrec_source']:
            regional_number(row[field])
        key = tuple(row[k] for k in FIELDS if k not in ('source_record_id', 'source_row_number'))
        if key in exact:
            duplicate_records += 1
        exact.add(key)
    if not rows:
        raise ValueError('Empty regional catalog')
    return dict(records=len(rows), first_source_time=min(times), last_source_time=max(times),
        bbox_wsen=[min(lons), min(lats), max(lons), max(lats)],
        magnitude_min=min(magnitudes, default=None), magnitude_max=max(magnitudes, default=None),
        magnitude_types=dict(magtypes), magnitude_value_counts=dict(bins),
        depth_value_min=min(depths, default=None), depth_value_max=max(depths, default=None),
        depth_value_missing=missing_depth,
        exact_duplicate_rows_preserved=duplicate_records,
        annual_counts_source_time={str(y): annual[y] for y in sorted(annual)})


def build_or_verify(directory, check=False):
    manifest = json.loads((directory / 'manifest.json').read_text())
    rows = list(source_rows(directory, manifest))
    summary = analyze(rows)
    csv_data = compressed(csv_bytes(rows, FIELDS))
    data_path = directory / 'catalog.csv.gz'
    quality = dict(schema_version=1, generator='scripts/build_regional_catalogs.py',
        source_sha256=manifest['source_sha256'], source_record=manifest['record_id'],
        license='CC-BY-4.0', path='catalog.csv.gz', bytes=len(csv_data), sha256=sha(csv_data),
        transformations=['Parsed per-source columns; all source records kept in original order.',
                         'IDs are local source-row references, NOT authoritative global event IDs.',
                         'Spreadsheet dates: Excel 1900 epoch, rounded to ms; original serial retained.',
                         'UTC conversion ONLY for the workbook with explicit UTC+8 header.',
                         "A bare '-' in numeric fields is preserved verbatim and counted as missing, never zero.",
                         'AI magnitude type ML is from the dataset description; other undocumented types left blank.',
                         'Text-file depth/quality units and coordinate datum not assumed.',
                         'No spatial/magnitude cutoff, deduplication, declustering, or homogenization.'],
        summary=summary)
    report = directory / 'derived.json'
    if check:
        existing = json.loads(report.read_text())
        stored = data_path.read_bytes()
        # Compare semantic CSV bytes across Python/zlib versions; also check stored SHA.
        if sha(stored) != existing['sha256'] or len(stored) != existing['bytes']:
            raise ValueError('Derived archive checksum mismatch')
        if gzip.decompress(stored) != gzip.decompress(csv_data):
            raise ValueError('CSV does not reproduce from locked original')
        if {k: v for k, v in existing.items() if k not in ('sha256', 'bytes')} != {k: v for k, v in quality.items() if k not in ('sha256', 'bytes')}:
            raise ValueError('Regional derivation report does not reproduce')
    else:
        data_path.write_bytes(csv_data)
        report.write_text(json.dumps(quality, ensure_ascii=False, indent=2) + '\n')
    print(directory.name, json.dumps(summary, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    verify(BASE)
    for source in SOURCES:
        build_or_verify(BASE / source['directory'], args.verify)


if __name__ == '__main__':
    main()
