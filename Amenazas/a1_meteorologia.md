# A1 meteorologia

Contrato y campos: ver docs/DATOS_AEREOS.md.
Productor: python -m Amenazas.a1_meteorologia. Cargador: mismo comando con --load RUTA.

## Diccionario del registro A1

La transformación produce solo horas activas o desconocidas; horas buenas
permanecen en M4 y no duplican filas en A1.

| Campo | Significado |
|---|---|
| `provider_id` | ISO-8601 UTC de `valid_at`; identifica la hora M4. |
| `geometry` | Polígono completo del AOI en GeoJSON WGS84. |
| `valid_at` | Inicio de validez de la observación/pronóstico horario M4. |
| `state` | `active` si excede el perfil, `unknown` si falta una variable requerida. |
| `reason` | `weather_outside_academic_profile` o `missing_weather`. |

Carga: `routing.hazards` (`dataset_key=A1`, `kind=weather`, `valid_from`,
`valid_until=valid_at+1 h`) y `routing.weather_hazards` (`weather_id`, `reason`).
`weather_id` enlaza la fila M4 de la misma hora. No se carga un registro A1 por
cada hora meteorológica segura.

## Modelo de falla en rutas

A1 deriva una fila por hora de M4 cuando falta viento, racha, dirección o
temperatura (`state=unknown`), o cuando viento/racha alcanza 8 m/s o la
temperatura queda fuera de [-5, 40] °C (`state=active`). La geometría de esa
fila es todo el AOI. No se aplica como polígono por arco: la ruta propuesta
consulta M4 directamente y, si la hora seleccionada falla esos mismos controles,
rechaza globalmente la misión (`unknown` si faltan datos; `not_feasible` si el
perfil meteorológico se excede). Por tanto, no queda ningún nodo o arco
habilitado por estar en una zona localmente favorable.

El control rige durante la hora de validez M4, `[valid_at, valid_at + 1 h)`.
Snapshot evalúa la hora solicitada (o `reference_time`); online además exige
adquisición menor de 90 minutos y una hora de escenario a no más de una hora
del reloj actual. La ida y el regreso usan el mismo corte meteorológico: no se
avanza el pronóstico durante el vuelo. Se supone que una sola celda M4
representa todo el AOI y el viento a 10 m aproxima, sin medir, las condiciones
a la altura de vuelo.
