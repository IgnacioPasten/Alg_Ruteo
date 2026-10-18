import csv
import io
import math
import unittest

from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape
from shapely.ops import transform

from Amenazas.a2_firms import transformar


class A2Firms(unittest.TestCase):
    def setUp(self):
        self.longitude = -71.65
        self.latitude = -33.10
        self.area = Polygon([
            (self.longitude - 0.05, self.latitude - 0.05),
            (self.longitude + 0.05, self.latitude - 0.05),
            (self.longitude + 0.05, self.latitude + 0.05),
            (self.longitude - 0.05, self.latitude + 0.05),
        ])
        self.radius = 100

    def csv_text(self, rows):
        output = io.StringIO()
        writer = csv.DictWriter(
            output, fieldnames=['latitude', 'longitude', 'acq_date', 'acq_time', 'confidence', 'frp'])
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()

    def rows(self):
        return [
            dict(latitude=self.latitude, longitude=self.longitude,
                 acq_date='2024-01-02', acq_time='304', confidence='h', frp='12.5'),
            dict(latitude=self.latitude, longitude=self.longitude + 0.001,
                 acq_date='2024-01-02', acq_time='304', confidence='n', frp='8.0'),
            dict(latitude=self.latitude, longitude=self.longitude + 0.002,
                 acq_date='2024-01-02', acq_time='304', confidence='l', frp='5.0'),
            dict(latitude=self.latitude, longitude=self.longitude + 1,
                 acq_date='2024-01-02', acq_time='304', confidence='h', frp='20.0'),
        ]

    def test_synthetic_csv_filters_aoi_and_confidence_and_makes_metric_buffers(self):
        records = transformar(self.csv_text(self.rows()), self.area, self.radius)

        self.assertEqual(len(records), 2)
        self.assertEqual([row['confidence'] for row in records], ['h', 'n'])
        self.assertTrue(all(self.area.covers(Point(row['point']['coordinates'])) for row in records))
        self.assertTrue(all(row['acquired_at'] == '2024-01-02T03:04:00+00:00' for row in records))

        to_metric = Transformer.from_crs(4326, 32719, always_xy=True).transform
        for row in records:
            buffer_area = transform(to_metric, shape(row['geometry'])).area
            expected_area = math.pi * self.radius ** 2
            self.assertAlmostEqual(buffer_area, expected_area, delta=expected_area * 0.01)

    def test_unknown_confidence_raises_value_error_inside_aoi(self):
        rows = self.rows()
        rows[0]['confidence'] = 'x'
        with self.assertRaisesRegex(ValueError, 'Confianza FIRMS desconocida'):
            transformar(self.csv_text(rows), self.area, self.radius)


if __name__ == '__main__':
    unittest.main()
