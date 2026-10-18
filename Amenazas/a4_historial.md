# A4 historial

Contrato y campos: ver docs/DATOS_AEREOS.md.
Productor: python -m Amenazas.a4_historial. Cargador: mismo comando con --load RUTA.

## Diccionario del registro A4

| Campo | Significado |
|---|---|
| `provider_id` | ID de la entidad original de SENAPRED como texto. |
| `geometry` | Polígono recortado al AOI y publicado como MultiPolygon GeoJSON WGS84. |
| `repaired` | `true` cuando se reparó la geometría de origen antes del recorte. |
| `ordinal_class` | Clase ordinal de recurrencia, entero 1–5. |
| `class_label` | Etiqueta original `recurrencia`. |
| `period_start` / `period_end` | Años inclusivos 2020 y 2024. |

Carga: `routing.hazards` (`dataset_key=A4`, `kind=historical`,
`state=historical`) y `routing.historical_risk` (clase, etiqueta y período).
La geometría almacenada es métrica en EPSG:32719.

## Modelo de falla en rutas

A4 no cierra nodos ni arcos. Para cada arco, la ruta calcula la longitud dentro
de polígonos históricos de 2020–2024 y asigna a cada tramo cubierto un factor
`(ordinal_class - 1) / 4`. En solapamientos usa la clase de mayor factor, sin
contar dos veces el tramo. La longitud no cubierta se marca como desconocida y
recibe factor 1, la penalización máxima. La exposición del trayecto es la suma
de longitud por factor, expresada en metros equivalentes; no es una
probabilidad.

La exposición solo ordena alternativas temporalmente factibles: primero se
limitan por presupuesto y por el desvío máximo de 1,2 respecto de la misión más
rápida, y luego se ordenan por exposición y tiempo. A4 es estático dentro de la
instantánea, representa recurrencia histórica 2020–2024 y no caduca según el
reloj de consulta. Se supone que la clase ordinal es comparable linealmente y
que la falta de cobertura merece la penalización máxima.
