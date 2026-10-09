import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_public_data import bbox_intersects, line_parts, write_gmt, city_rows
from fetch_public_data import fetch, verified
from validate_public_data import check_position, geometry_stats


class DataTests(unittest.TestCase):
    def test_coordinates(self):
        check_position([180, -90])
        for p in ([200, 0], [0, 91], [float('nan'), 0], [0], ['x', 0]):
            with self.assertRaises(ValueError):
                check_position(p)

    def test_bbox_keeps_crossing_line_without_vertices_inside(self):
        self.assertTrue(bbox_intersects({'coordinates': [[60, 30], [150, 30]]}))
        self.assertFalse(bbox_intersects({'coordinates': [[-120, 30], [-110, 40]]}))

    def test_no_merge_of_multiline_parts(self):
        g = {'type': 'MultiLineString', 'coordinates': [[[1, 2], [3, 4]], [[5, 6], [7, 8]]]}
        self.assertEqual(len(list(line_parts(g))), 2)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'line.gmt'
            write_gmt(p, [{'geometry': g}])
            self.assertEqual(p.read_text().count('> feature_index='), 2)

    def test_refuses_polygon_line_conversion(self):
        with self.assertRaises(ValueError):
            list(line_parts({'type': 'Polygon', 'coordinates': []}))

    def test_empty_geometry_is_explicit_exception_only(self):
        data = {'type': 'FeatureCollection', 'features': [
            {'geometry': {'type': 'LineString', 'coordinates': [[1, 2], [3, 4]]}},
            {'geometry': {'type': 'MultiLineString', 'coordinates': []}}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'data.json'
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                geometry_stats(p)
            self.assertEqual(geometry_stats(p, [1])['known_empty_feature_indices'], [1])

    def test_closed_ring_required(self):
        data = {'type': 'FeatureCollection', 'features': [
            {'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 1]]]}}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'polygon.json'
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                geometry_stats(p)

    def test_hash_and_size(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'x'
            p.write_bytes(b'abc')
            item = {'bytes': 3, 'sha256': hashlib.sha256(b'abc').hexdigest()}
            self.assertTrue(verified(p, item))
            p.write_bytes(b'abd')
            self.assertFalse(verified(p, item))

    def test_bad_download_does_not_replace_original(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'x'
            p.write_bytes(b'original')
            item = {'path': 'x', 'id': 'test', 'bytes': 3,
                    'sha256': hashlib.sha256(b'abc').hexdigest(),
                    'api_url': 'https://api.github.com/repos/test/test/contents/x?ref=abc'}
            def download(*args, **kwargs):
                kwargs['stdout'].write(b'bad')
            with patch('fetch_public_data.ROOT', Path(d)), patch('fetch_public_data.subprocess.run', side_effect=download):
                with self.assertRaises(RuntimeError):
                    fetch(item, force=True)
            self.assertEqual(p.read_bytes(), b'original')
            self.assertEqual(list(Path(d).iterdir()), [p])

    def test_city_coordinates_from_geometry_not_label_fields(self):
        f = {'geometry': {'coordinates': [120, 30]}, 'properties': {
            'NE_ID': 1, 'NAME': 'Test', 'LONGITUDE': 0, 'LATITUDE': 0}}
        row = city_rows([f])[0]
        self.assertEqual((row['longitude'], row['latitude']), (120, 30))


if __name__ == '__main__':
    unittest.main()
