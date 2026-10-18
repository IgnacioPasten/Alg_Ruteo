import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, shape
from shapely.ops import transform

from Amenazas.a3_aip import transformar
from core.aerial_etl import extract
from core.aerial_data import build
from core.contracts import ROOT


class A3Aip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / 'config/proyecto.json').read_text(encoding='utf-8'))
        cls.profile = json.loads((ROOT / cls.config['aerial_profile']).read_text(encoding='utf-8'))
        cls.area = shape(json.loads((ROOT / cls.config['aoi_geojson']).read_text(encoding='utf-8'))
                         ['features'][0]['geometry'])
        cls.pdf = ROOT / cls.config['aerial_raw_directory'] / 'S6_fd2d8e065ebd2098.pdf'
        cls.records, cls.report = transformar(
            cls.pdf, cls.area, cls.profile['aip_margin_m'])
        cls.doc, cls.context = build(cls.config)

    def test_real_pdf_selects_p29_p50_with_original_circle_parameters(self):
        self.assertEqual([row['code'] for row in self.records], ['SC-P29', 'SC-P50'])
        reference = json.loads((ROOT / 'evidencia/a3_v1.json').read_text(encoding='utf-8'))
        reference_by_code = {row['code']: row for row in reference}
        by_code = {row['code']: row for row in self.records}
        for code in ('SC-P29', 'SC-P50'):
            self.assertEqual(by_code[code]['center'], reference_by_code[code]['center'])
            self.assertEqual(by_code[code]['radius_m'], reference_by_code[code]['radius_m'])
        report_by_code = {row['code']: row for row in self.report['records']}
        self.assertEqual(report_by_code['SC-P30']['status'], 'fuera_del_margen')
        self.assertEqual(by_code['SC-P29']['upper_limit'], '1000 FT AGL')
        self.assertEqual(by_code['SC-P29']['lower_limit'], 'GND')
        self.assertEqual(by_code['SC-P50']['upper_limit'], '3 000 FT ALT')
        self.assertEqual(by_code['SC-P50']['lower_limit'], 'GND / MSL')

    def test_report_accounts_for_all_zones_vertical_limits_and_exceptions(self):
        self.assertEqual(self.report['counts'], {'SC-P': 32, 'SC-R': 37, 'SC-D': 9})
        self.assertEqual(self.report['total_records'], 78)
        self.assertTrue(all(row['lower_limit'] and row['upper_limit']
                            for row in self.report['records']))
        statuses = {row['code']: row['status'] for row in self.report['records']}
        for code in ('SC-P10', 'SC-R32', 'SC-R45', 'SC-R46', 'SC-R47', 'SC-R48'):
            self.assertEqual(statuses[code], 'no_soportada_lejana')
        self.assertEqual(statuses['SC-P51'], 'excepcion_sin_geometria')
        exceptions = {row['code'] for row in self.report['explicit_exceptions']}
        self.assertTrue({'SC-P51', 'SC-R45', 'SC-R46', 'SC-R47', 'SC-R48'} <= exceptions)

    def test_reordered_polygon_hull_near_aoi_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SC-P99.*convex hull'):
            self._transform_synthetic_polygon(near=True)

    def test_reordered_polygon_hull_far_from_aoi_is_reported(self):
        records, report = self._transform_synthetic_polygon(near=False)
        entry = next(row for row in report['records'] if row['code'] == 'SC-P99')
        self.assertTrue(entry['geometry_reordered'])
        self.assertGreater(entry['convex_hull_distance_m'], 300)
        self.assertEqual(entry['status'], 'fuera_del_margen')
        self.assertTrue(all(row['code'] != 'SC-P99' for row in records))

    def _transform_synthetic_polygon(self, near):
        area = Polygon([
            (-71.01, -33.01), (-70.99, -33.01),
            (-70.99, -32.99), (-71.01, -32.99),
        ])
        offset = 0 if near else 0.2

        def coordinate_text(longitude, latitude):
            lat_total = round(abs(latitude) * 3600)
            lat_deg, lat_remainder = divmod(lat_total, 3600)
            lat_min, lat_sec = divmod(lat_remainder, 60)
            lon_total = round(abs(longitude) * 3600)
            lon_deg, lon_remainder = divmod(lon_total, 3600)
            lon_min, lon_sec = divmod(lon_remainder, 60)
            return (
                f'{lat_deg:02d} {lat_min:02d} {lat_sec:02d} S '
                f'{lon_deg:03d} {lon_min:02d} {lon_sec:02d} W'
            )

        vertices = [
            (-71.005 + offset, -33.005 + offset),
            (-70.995 + offset, -32.995 + offset),
            (-71.005 + offset, -32.995 + offset),
            (-70.995 + offset, -33.005 + offset),
        ]
        polygon_block = '\n'.join(coordinate_text(*point) for point in vertices)
        circle_point = coordinate_text(-71.0, -33.0)
        entries = [
            ('SC-P99', 1, polygon_block, []),
            ('SC-R1', 1, f'circle radius 10 M {circle_point}', []),
            ('SC-D1', 1, f'circle radius 10 M {circle_point}', []),
        ]
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / 'synthetic.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            with pdf.open('wb') as stream:
                writer.write(stream)
            with (
                patch('Amenazas.a3_aip._entry_blocks', return_value=iter(entries)),
                patch('Amenazas.a3_aip._vertical_limits', return_value=('SFC', 'FL 100')),
            ):
                return transformar(pdf, area, 300)

    def test_graph_arcs_intersecting_a3_are_unchanged_from_v1(self):
        to_metric = Transformer.from_crs(4326, 32719, always_xy=True).transform
        old_records = json.loads((ROOT / 'evidencia/a3_v1.json').read_text(encoding='utf-8'))
        old_zones = [transform(to_metric, shape(row['geometry'])) for row in old_records]
        new_zones = [
            transform(to_metric, shape(row['geometry']))
            for row in self.context['records']['A3']
        ]

        def intersecting_arcs(zones):
            return {
                edge['id'] for edge in self.doc['edges']
                if any(transform(to_metric, LineString(edge['geometry']['coordinates']))
                       .intersects(zone) for zone in zones)
            }

        self.assertEqual(intersecting_arcs(old_zones), intersecting_arcs(new_zones))
        self.assertEqual(self.context['aip_parser_report']['selected_codes'], ['SC-P29', 'SC-P50'])
        r68 = next(
            row for row in self.report['records'] if row['code'] == 'SC-R68')
        self.assertTrue(r68['geometry_reordered'])
        self.assertEqual(r68['status'], 'fuera_del_margen')
        self.assertGreater(r68['convex_hull_distance_m'], self.profile['aip_margin_m'])

    def test_a3_extraction_packet_includes_the_full_parser_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / 'datos/runs' / self.doc['run_id']
            run_dir.mkdir(parents=True)
            (run_dir / 'infraestructura.json').write_text(
                json.dumps(self.doc, ensure_ascii=False), encoding='utf-8')
            (run_dir / 'context.json').write_text(
                json.dumps(self.context, ensure_ascii=False), encoding='utf-8')
            output = root / 'A3.json'
            with patch('core.aerial_etl.ROOT', root):
                extract('A3', self.doc['run_id'], output)
            packet = json.loads(output.read_text(encoding='utf-8'))
        self.assertEqual(packet['parser_report'], self.context['aip_parser_report'])
        self.assertEqual(
            packet['records'],
            json.loads(json.dumps(self.context['records']['A3'], ensure_ascii=False)),
        )


if __name__ == '__main__':
    unittest.main()
