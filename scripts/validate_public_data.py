#!/usr/bin/env python3
"""Offline integrity + basic geometry/coordinate checks, not a scientific or topology audit."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path

from fetch_public_data import ROOT, LOCK, verified
from build_public_data import positions


def check_position(point):
    if len(point) < 2:
        raise ValueError('Coordinate requires longitude and latitude')
    lon, lat = point[:2]
    if not all(isinstance(x, (float, int)) and math.isfinite(x) for x in (lon, lat)):
        raise ValueError(f'Non-finite/nonnumeric coordinate: {point}')
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError(f'Out-of-range longitude/latitude: {point}')


def geometry_stats(path, allowed_empty=()):
    d = json.loads(path.read_text(encoding='utf-8'))
    if d.get('type') != 'FeatureCollection' or not d.get('features'):
        raise ValueError('Expected nonempty FeatureCollection')
    types = Counter()
    west = south = math.inf
    east = north = -math.inf
    vertices = 0
    empty_indices = []
    for index, f in enumerate(d['features']):
        g = f.get('geometry')
        if not g:
            raise ValueError('Null geometry')
        types[g['type']] += 1
        coords = g['coordinates']
        if g['type'] == 'Point':
            parts = []
        elif g['type'] == 'LineString':
            parts = [coords]
        elif g['type'] in ('MultiLineString', 'Polygon'):
            parts = coords
        elif g['type'] == 'MultiPolygon':
            parts = [ring for polygon in coords for ring in polygon]
        else:
            raise ValueError(f'Unsupported geometry {g["type"]}')
        polygon = g['type'] in ('Polygon', 'MultiPolygon')
        for part in parts:
            if len(part) < (4 if polygon else 2):
                raise ValueError('Short line/ring')
            if polygon and part[0] != part[-1]:
                raise ValueError('Unclosed ring')
        points = list(positions(coords))
        if not points:
            if index not in allowed_empty:
                raise ValueError(f'Empty coordinates at feature {index}')
            empty_indices.append(index)
            continue
        for p in points:
            check_position(p)
            west, east = min(west, p[0]), max(east, p[0])
            south, north = min(south, p[1]), max(north, p[1])
            vertices += 1
    if set(empty_indices) != set(allowed_empty):
        raise ValueError('Known empty-geometry exceptions do not match this file')
    return dict(features=len(d['features']), geometry_types=dict(types), vertices=vertices,
                known_empty_feature_indices=empty_indices, bbox_wsen=[west, south, east, north])


def gmt_stats(path):
    segments = points = current = 0
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('>'):
            segments += 1
            current = 0
            continue
        values = line.split()
        check_position([float(values[0]), float(values[1])])
        points += 1
        current += 1
    if not points:
        raise ValueError('No GMT coordinates')
    return dict(segments=segments, vertices_or_points=points)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-local', action='store_true', help='Require all optional GMT China files')
    parser.add_argument('--report', type=Path, help='Write JSON report (optional)')
    args = parser.parse_args()
    sources = json.loads(LOCK.read_text())['sources']
    derived = json.loads((ROOT / 'data/metadata/derivatives.json').read_text())['files']
    issues = json.loads((ROOT / 'data/metadata/known-issues.json').read_text())
    report = dict(scope='SHA256, sizes, finite/range coordinates, nonempty geometries, ring closure; NOT topology/accuracy/official approval',
                  checked=[], skipped=[], errors=[])
    for item in sources + derived:
        p = ROOT / item['path']
        required = item.get('storage', 'vendored') == 'vendored' or (args.include_local and item.get('storage') == 'local_only')
        if not p.exists() and not required:
            report['skipped'].append(item['path'])
            continue
        try:
            if not verified(p, item):
                raise ValueError('Missing file, SHA256 mismatch or size mismatch')
            stats = {}
            if p.suffix in ('.json', '.geojson'):
                stats = geometry_stats(p, issues.get(item['path'], {}).get('allowed_empty_feature_indices', ()))
            elif p.suffix == '.csv':
                with p.open(encoding='utf-8', newline='') as stream:
                    rows = list(csv.DictReader(stream))
                for row in rows:
                    check_position([float(row['longitude']), float(row['latitude'])])
                if len({r['ne_id'] for r in rows}) != len(rows):
                    raise ValueError('Duplicate city ne_id')
                stats = dict(rows=len(rows))
            elif p.suffix == '.gmt':
                stats = gmt_stats(p)
            if 'count' in item:
                actual = stats.get('rows', stats.get('features', stats.get('segments') or stats.get('vertices_or_points')))
                if actual != item['count']:
                    raise ValueError(f'Count mismatch {actual} != {item["count"]}')
            report['checked'].append(dict(path=item['path'], **stats))
        except (ValueError, KeyError, TypeError, OSError) as error:
            report['errors'].append(dict(path=item['path'], error=str(error)))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return bool(report['errors'])


if __name__ == '__main__':
    raise SystemExit(main())
