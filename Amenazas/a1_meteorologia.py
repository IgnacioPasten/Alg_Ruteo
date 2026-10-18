"""A1 · Condiciones meteorológicas adversas derivadas de M4."""

from shapely.geometry import mapping


def transformar(m4_rows, area, profile):
    """Genera amenazas meteorológicas activas o desconocidas a partir de M4."""
    registros = []
    for row in m4_rows:
        missing = any(row[key] is None for key in [
            'wind_speed_ms', 'wind_gust_ms', 'temperature_c', 'wind_direction_deg'])
        bad = not missing and (
            max(row['wind_speed_ms'], row['wind_gust_ms']) >= profile['wind_limit_ms']
            or not profile['temperature_min_c'] <= row['temperature_c'] <= profile['temperature_max_c'])
        if missing or bad:
            registros.append(dict(
                provider_id=row['valid_at'],
                geometry=mapping(area),
                valid_at=row['valid_at'],
                state='unknown' if missing else 'active',
                reason='missing_weather' if missing else 'weather_outside_academic_profile'))
    return registros

if __name__ == '__main__':
    from core.aerial_etl import main  # import local para evitar import circular
    main('A1')
