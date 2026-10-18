"""A4 · Recurrencia histórica de incendios (S7, SENAPRED 2020-2024).

Extracción: Infraestructura/descargar_aereo.py (S7, ArcGIS REST paginado por objectIds).
Transformación: transformar() en este archivo.
Carga: core.aerial_etl.load -> routing.hazards + routing.historical_risk.
"""
from shapely import make_valid
from shapely.geometry import shape, mapping

PERIODO = (2020, 2024)


def transformar(features, area, id_field, polygonal):
    """Recorta los polígonos al AOI, repara geometrías y valida la clase ordinal 1-5."""
    registros, reparados = [], 0
    for f in features:
        geom = shape(f['geometry']); malo = not geom.is_valid
        if malo:
            geom = make_valid(geom); reparados += 1
        geom = polygonal(geom.intersection(area))
        if geom.is_empty:
            continue
        p = f['properties']
        clase = int(p['gridcode'])
        if not 1 <= clase <= 5:
            raise ValueError('Clase histórica desconocida')
        registros.append(dict(provider_id=str(p[id_field]), geometry=mapping(geom), repaired=malo,
                              ordinal_class=clase, class_label=p['recurrencia'],
                              period_start=PERIODO[0], period_end=PERIODO[1]))
    return registros, reparados


if __name__ == '__main__':
    from core.aerial_etl import main  # import local para evitar import circular
    main('A4')