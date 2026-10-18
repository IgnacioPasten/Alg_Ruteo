# A2 firms

Contrato y campos: ver docs/DATOS_AEREOS.md.
Productor: python -m Amenazas.a2_firms. Cargador: mismo comando con --load RUTA.

## Diccionario del registro A2

Se conservan únicamente detecciones cubiertas por el AOI y de confianza `n` o
`h`. La carga real actual puede ser vacía: dataset `A2` con
`record_count=0`, `status=empty`, sin filas en las tablas de amenazas.

| Campo | Significado |
|---|---|
| `provider_id` | Clave determinista `acquired_at:latitude:longitude`. |
| `point` | Punto FIRMS original, WGS84 [longitud, latitud]. |
| `geometry` | Buffer del punto, creado en EPSG:32719 con radio `buffer_m`, y publicado WGS84. |
| `acquired_at` | Fecha/hora de detección FIRMS en UTC, `YYYY-MM-DDTHH:MM:00+00:00`. |
| `confidence` | `n` o `h`; `l` se descarta. |
| `fire_radiative_power_mw` | FRP en MW. |
| `buffer_m` | Radio métrico del buffer, definido por `thermal_buffer_m`. |

Carga: `routing.hazards` (`dataset_key=A2`, `kind=thermal`, geometría y
`valid_from=acquired_at`) y `routing.thermal_events` (`acquired_at`,
`confidence`, FRP, `buffer_m`). Si no hay focos válidos, el manifest/data set
declara explícitamente `empty`; no se inserta una fila ficticia.

## Modelo de falla en rutas

Cada detección FIRMS dentro del AOI, con confianza `n` o `h`, se representa
como un buffer de `thermal_buffer_m` (250 m por defecto) alrededor del punto,
construido en EPSG:32719. Confianza `l` se omite y una clase desconocida falla
la transformación. La ruta propuesta excluye cualquier arco cuya línea
intersecte un buffer; también rechaza el escenario si el buffer intersecta un
extremo de ruta o la base de regreso. No se asigna un riesgo gradual.

Una detección rige para la consulta si no es futura y su antigüedad es como
máximo `thermal_window_hours` (24 h por defecto), incluido el límite de 24 h.
La extracción conserva hasta siete días del producto, pero eso no prolonga su
efecto de ruteo. Se supone que el buffer circular fijo aproxima la extensión
del foco; no modela crecimiento, dirección de propagación ni intensidad FRP.
