"""A2 · Focos de calor FIRMS (S5).

Transformación: transformar() en este archivo.
Carga: core.aerial_etl.load -> routing.hazards.
"""
import csv
import io

from pyproj import Transformer
from shapely.geometry import Point, mapping
from shapely.ops import transform

FWD = Transformer.from_crs(4326, 32719, always_xy=True).transform
INV = Transformer.from_crs(32719, 4326, always_xy=True).transform


def transformar(csv_text, area, thermal_buffer_m):
    """Filtra los focos por AOI y crea buffers métricos para focos de confianza n/h."""
    registros = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        point = Point(float(row['longitude']), float(row['latitude']))
        if area.covers(point):
            hh = row['acq_time'].zfill(4)
            date = row['acq_date'] + 'T' + hh[:2] + ':' + hh[2:] + ':00+00:00'
            if row['confidence'] not in ['l', 'n', 'h']:
                raise ValueError('Confianza FIRMS desconocida')
            if row['confidence'] == 'l':
                continue
            registros.append(dict(
                provider_id=f'{date}:{row["latitude"]}:{row["longitude"]}',
                point=mapping(point),
                geometry=mapping(transform(
                    INV, transform(FWD, point).buffer(thermal_buffer_m))),
                acquired_at=date,
                confidence=row['confidence'],
                fire_radiative_power_mw=float(row['frp']),
                buffer_m=thermal_buffer_m))
    return registros

if __name__ == '__main__':
    from core.aerial_etl import main  # import local para evitar import circular
    main('A2')
