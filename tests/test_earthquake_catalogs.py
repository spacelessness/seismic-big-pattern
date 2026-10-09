import csv
from datetime import timedelta
import gzip
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collect_usgs_catalog import (Collector, MAPPING, MS, REQUIRED, csv_bytes, compressed,
    iso, parse_csv, timestamp, validate_row, write_snapshot, is_small_medium)
from build_regional_catalogs import (analyze, empty_row, excel_datetime, local_iso,
    local_time, regional_number)
from collect_zenodo_catalogs import safe_file_url
from validate_earthquake_catalogs import verify_usgs


def event(identifier, when, mag='2.0', kind='earthquake'):
    r = {k: '' for k in MAPPING}
    r.update(id=identifier, time=when, longitude='103', latitude='30', depth='5',
             mag=mag, magType='ml', net='test', type=kind, status='reviewed',
             updated='2026-10-08T00:00:00Z', locationSource='test', magSource='test',
             place='Synthetic test fixture, not an observation')
    return r


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        q = parse_qs(urlparse(url).query)
        a, b = timestamp(q['starttime'][0]), timestamp(q['endtime'][0])
        rows = [r for r in self.rows if a <= timestamp(r['time']) <= b]
        if '/count?' in url:
            return str(len(rows)).encode()
        return csv_bytes(rows, list(MAPPING))


class CatalogTests(unittest.TestCase):
    def test_timezone_is_explicit(self):
        self.assertEqual(timestamp('2020-01-01T08:00:00+08:00'), timestamp('2020-01-01T00:00:00Z'))
        with self.assertRaises(ValueError):
            timestamp('2020-01-01T00:00:00')

    def test_csv_quotes_and_bad_responses(self):
        row = event('x', '2020-01-01T00:00:00Z')
        body = csv_bytes([row], list(MAPPING))
        self.assertEqual(parse_csv(body), [row])
        for body in (b'<html>login</html>', b'id,time\nx,2020\n', body.rsplit(b',', 1)[0]):
            with self.assertRaises(ValueError):
                parse_csv(body)

    def test_negative_and_missing_magnitudes_not_zero_filled(self):
        for mag in ('-0.5', '0', ''):
            r = event('x', '2020-01-01T00:00:00Z', mag)
            validate_row(r, timestamp(r['time']), timestamp(r['time']), (70, 140, 0, 60))
        self.assertTrue(is_small_medium({'magnitude': '-0.5', 'event_type': 'earthquake'}))
        self.assertFalse(is_small_medium({'magnitude': '', 'event_type': 'earthquake'}))
        self.assertFalse(is_small_medium({'magnitude': '2', 'event_type': 'explosion'}))
        self.assertFalse(is_small_medium({'magnitude': '5', 'event_type': 'earthquake'}))

    def test_coordinate_and_nonfinite_rejection(self):
        r = event('x', '2020-01-01T00:00:00Z')
        for key, val in [('longitude', '10'), ('latitude', 'nan'), ('depth', 'inf'), ('mag', 'nan')]:
            with self.assertRaises(ValueError):
                validate_row(dict(r, **{key: val}), timestamp(r['time']), timestamp(r['time']), (70, 140, 0, 60))

    def test_lossless_gzip(self):
        raw = b'original\r\nbytes\n'
        self.assertEqual(gzip.decompress(compressed(raw)), raw)
        self.assertEqual(compressed(raw), compressed(raw))

    def test_split_count_coverage_and_reproducible_derivatives(self):
        a = timestamp('2020-01-01T00:00:00Z')
        times = [a, a + MS, a + 2 * MS, a + 4 * MS]
        rows = [event(str(i), iso(t), '-0.2' if i == 0 else '') for i, t in enumerate(times)]
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient(rows)
            c = Collector(Path(d), (70, 140, 0, 60), client, max_events=2)
            c.collect(a, a + 5 * MS)
            self.assertEqual(len(c.events), 4)
            self.assertTrue(all('minmagnitude' not in u and 'limit=' not in u for u in client.urls))
            m = write_snapshot(Path(d), c, a, a + 6 * MS, 4, 4)
            self.assertEqual(m['summary']['missing_magnitude'], 3)
            self.assertEqual(verify_usgs(Path(d))['events'], 4)
            p = Path(d) / m['intervals'][0]['path']
            p.write_bytes(b'corrupted')
            with self.assertRaises((ValueError, OSError)):
                verify_usgs(Path(d))

    def test_changed_root_count_refuses_publish(self):
        with tempfile.TemporaryDirectory() as d:
            a = timestamp('2020-01-01T00:00:00Z')
            c = Collector(Path(d), (70, 140, 0, 60), FakeClient([event('x', iso(a))]))
            c.collect(a, a + MS)
            with self.assertRaises(ValueError):
                write_snapshot(Path(d), c, a, a + 2 * MS, 1, 2)

    def test_no_untrusted_zenodo_download_host(self):
        self.assertEqual(safe_file_url('https://zenodo.org/api/records/1'), 'https://zenodo.org/api/records/1')
        for url in ['https://example.org/file', 'http://zenodo.org/file', 'file:///etc/passwd']:
            with self.assertRaises(ValueError):
                safe_file_url(url)

    def test_regional_dash_is_missing_never_zero(self):
        self.assertIsNone(regional_number(''))
        self.assertIsNone(regional_number('-'))
        self.assertEqual(regional_number('2.5'), 2.5)
        self.assertEqual(regional_number('-0.5'), -0.5)
        with self.assertRaises(ValueError):
            regional_number('nan')

    def test_local_time_validates_calendar(self):
        dt = local_time('2019', '06', '17', '22', '55', '43.25')
        self.assertEqual(local_iso(dt), '2019-06-17T22:55:43.250')
        for bad in [('2019', '13', '01', '00', '00', '01'),
                    ('2019', '01', '01', '00', '00', '60'),
                    ('2019', '01', '01', '00', '00', '-1')]:
            with self.assertRaises(ValueError):
                local_time(*bad)

    def test_excel_datetime_rounds_to_millisecond(self):
        # Pinned workbook row 2: serial -> 2022-12-31 17:34:34 local.
        self.assertEqual(excel_datetime('44926.73233796296').isoformat(),
                         '2022-12-31T17:34:34')
        with self.assertRaises(ValueError):
            excel_datetime('25568.0')

    def test_regional_rows_keep_timezone_unknown_by_default(self):
        r = empty_row(5602183, 7)
        self.assertEqual(r['origin_time_utc'], '')
        self.assertEqual(r['timezone_status'], 'unspecified_in_source_do_not_assume_UTC')
        self.assertEqual(r['source_record_id'], 'zenodo.5602183:row7')

    def test_regional_analyze_bins_and_rejects_bad_coordinates(self):
        def row(mag, depth, lon='100.0', lat='30.0'):
            r = empty_row(1, 1)
            r.update(origin_time_source='2020-01-01T00:00:00.000', longitude=lon,
                     latitude=lat, depth_value=depth, magnitude=mag)
            return r
        summary = analyze([row('-0.5', '5'), row('0', '-'), row('', '10')])
        self.assertEqual(summary['records'], 3)
        self.assertEqual(summary['magnitude_value_counts']['negative'], 1)
        self.assertEqual(summary['magnitude_value_counts']['zero'], 1)
        self.assertEqual(summary['magnitude_value_counts']['missing'], 1)
        self.assertEqual(summary['depth_value_missing'], 1)
        self.assertEqual(summary['magnitude_min'], -0.5)
        with self.assertRaises(ValueError):
            analyze([row('1.0', '5', lon='-')])
        with self.assertRaises(ValueError):
            analyze([row('1.0', '5', lat='91')])
        with self.assertRaises(ValueError):
            analyze([])


if __name__ == '__main__':
    unittest.main()
