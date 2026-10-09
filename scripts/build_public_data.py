#!/usr/bin/env python3
"""Deterministic lightweight derivatives. No reprojection, simplification or invented coordinates."""
import csv
import hashlib
import json
from pathlib import Path

from fetch_public_data import ROOT, LOCK, verified

# Editorial label list, not inferred from Natural Earth's sometimes incorrect admin fields.
CAPITALS = dict(pair.split(':') for pair in (
    '北京:北京市 天津:天津市 石家庄:河北省 太原:山西省 呼和浩特:内蒙古自治区 '
    '沈阳:辽宁省 长春:吉林省 哈尔滨:黑龙江省 上海:上海市 南京:江苏省 '
    '杭州:浙江省 合肥:安徽省 福州:福建省 南昌:江西省 济南:山东省 '
    '郑州:河南省 武汉:湖北省 长沙:湖南省 广州:广东省 南宁:广西壮族自治区 '
    '海口:海南省 重庆:重庆市 成都:四川省 贵阳:贵州省 昆明:云南省 '
    '拉萨:西藏自治区 西安:陕西省 兰州:甘肃省 西宁:青海省 银川:宁夏回族自治区 '
    '乌鲁木齐:新疆维吾尔自治区 台北:台湾省 香港:香港特别行政区 澳门:澳门特别行政区'
).split())
BBOX = (70, 140, 0, 60)  # Analysis window, NOT an administrative boundary.


def positions(coords):
    if not coords:
        return
    if isinstance(coords[0], (float, int)):
        yield coords
    else:
        for part in coords:
            yield from positions(part)


def bbox_intersects(geometry, bbox=BBOX):
    points = list(positions(geometry['coordinates']))
    xs, ys = zip(*[(p[0], p[1]) for p in points])
    w, e, s, n = bbox
    return max(xs) >= w and min(xs) <= e and max(ys) >= s and min(ys) <= n


def line_parts(geometry):
    kind, coords = geometry['type'], geometry['coordinates']
    if kind == 'LineString':
        yield coords
    elif kind == 'MultiLineString':
        yield from coords
    else:
        raise ValueError(f'Line conversion does not accept {kind}')


def write_gmt(path, features):
    """One segment per line part; GeoJSON remains authoritative for all attributes."""
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('# longitude latitude; UTF-8; linework only, not polygon topology\n')
        for i, feature in enumerate(features):
            for j, part in enumerate(line_parts(feature['geometry'])):
                stream.write(f'> feature_index={i} part={j}\n')
                for lon, lat, *_ in part:
                    stream.write(f'{lon:.8f} {lat:.8f}\n')


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def city_rows(features):
    result = []
    for feature in features:
        p = feature['properties']
        lon, lat = feature['geometry']['coordinates'][:2]
        result.append(dict(ne_id=p['NE_ID'], name=p['NAME'], name_zh=p.get('NAME_ZH'),
            longitude=lon, latitude=lat, wikidata_id=p.get('WIKIDATAID'),
            source_adm0_a3=p.get('ADM0_A3'), source_adm1_name=p.get('ADM1NAME'),
            source_feature_class=p.get('FEATURECLA'), source_scalerank=p.get('SCALERANK'),
            source_pop_max=p.get('POP_MAX'), source_id='ne-ne_10m_populated_places'))
    return sorted(result, key=lambda row: row['ne_id'])


def main():
    sources = json.loads(LOCK.read_text())['sources']
    required = [s for s in sources if s['storage'] != 'local_only']
    for s in required:
        if not verified(ROOT / s['path'], s):
            raise RuntimeError(f"Missing/changed {s['path']}; run fetch_public_data.py --include-cache")
    output = ROOT / 'data/derived'
    output.mkdir(exist_ok=True)
    derivatives = []

    def record(path, parents, license, transform, count):
        derivatives.append(dict(path=str(path.relative_to(ROOT)), source_ids=parents, license=license,
            transformation=transform, count=count, bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

    city_source = next(s for s in sources if s['id'] == 'ne-ne_10m_populated_places')
    cities = city_rows(json.loads((ROOT / city_source['path']).read_text())['features'])
    cn = [c for c in cities if c['source_adm0_a3'] in ('CHN', 'HKG', 'MAC', 'TWN')]
    major = [c for c in cities if c['source_scalerank'] <= 3 or c['source_pop_max'] >= 1000000]
    capitals = [dict(c, label_admin_unit=CAPITALS[c['name_zh']]) for c in cn if c['name_zh'] in CAPITALS]
    if len(capitals) != 34 or {c['name_zh'] for c in capitals} != set(CAPITALS):
        raise RuntimeError('Capital matching is ambiguous or incomplete; review upstream changes')
    for name, rows, rule in [
        ('cities_world', cities, 'All source points; reduced fields; geometry coordinates, not label fields'),
        ('cities_world_major', major, 'source SCALERANK <= 3 OR source POP_MAX >= 1000000; not current population'),
        ('cities_china', cn, 'Source ADM0_A3 in CHN/HKG/MAC/TWN; preserve upstream codes, not a sovereignty classification'),
        ('cities_china_34_labels', capitals, 'Explicit 34-city editorial label list; coordinates from Natural Earth; not official administrative data')]:
        path = output / (name + '.csv')
        write_csv(path, rows)
        record(path, [city_source['id']], 'Public Domain', rule, len(rows))
        # Compact point GeoJSON for GIS; CSV holds the same coordinates and fields.
        if name != 'cities_world':
            path = output / (name + '.geojson')
            write_json(path, dict(type='FeatureCollection', features=[dict(type='Feature',
                properties=r, geometry=dict(type='Point', coordinates=[r['longitude'], r['latitude']])) for r in rows]))
            record(path, [city_source['id']], 'Public Domain', rule, len(rows))
    path = output / 'cities_china_34_labels.gmt'
    with path.open('w', encoding='utf-8') as stream:
        stream.write('# longitude latitude label; Natural Earth, not official coordinates\n')
        for c in capitals:
            stream.write(f"{c['longitude']} {c['latitude']} {c['name_zh']}\n")
    record(path, [city_source['id']], 'Public Domain', '34-city label list; UTF-8 lon lat Chinese label', 34)

    gem_source = next(s for s in sources if s['id'] == 'gem-gem_active_faults')
    faults = json.loads((ROOT / gem_source['path']).read_text())['features']
    regional = [f for f in faults if bbox_intersects(f['geometry'])]
    path = output / 'gem_faults_east_asia_bbox.geojson'
    write_json(path, dict(type='FeatureCollection', features=regional))
    record(path, [gem_source['id']], 'CC-BY-SA-4.0',
           'Whole features whose bounding boxes intersect 70/140/0/60; NOT clipped, NOT a China boundary; all attributes retained', len(regional))
    for source_id, filename, features in [
        ('gem-gem_active_faults', 'gem_faults_east_asia_bbox.gmt', regional),
        ('pb-PB2002_boundaries', 'PB2002_boundaries.gmt', json.loads((ROOT / 'data/raw/pb2002/PB2002_boundaries.json').read_text())['features'])]:
        path = output / filename
        write_gmt(path, features)
        record(path, [source_id], 'CC-BY-SA-4.0' if source_id.startswith('gem') else 'ODC-By-1.0',
               'Line parts exported independently; rounded to 8 decimals; attributes in companion GeoJSON; no simplification', len(features))
    river_source = next(s for s in sources if s['id'] == 'ne-ne_50m_rivers_lake_centerlines')
    rivers = json.loads((ROOT / river_source['path']).read_text())['features']
    nonempty = [f for f in rivers if f['geometry'] and list(positions(f['geometry']['coordinates']))]
    path = output / 'ne_50m_rivers_nonempty.geojson'
    write_json(path, dict(type='FeatureCollection', features=nonempty))
    record(path, [river_source['id']], 'Public Domain',
           'Remove empty geometries only (source zero-based feature 460, Loire); preserve other geometry and attributes', len(nonempty))
    metadata = dict(schema_version=1, generator='scripts/build_public_data.py', files=derivatives)
    (ROOT / 'data/metadata/derivatives.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({x['path']: x['count'] for x in derivatives}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
