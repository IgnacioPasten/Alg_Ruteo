# A3 · Zonas AIP ENR 5.1

El extractor recorre todos los registros SC-P, SC-R y SC-D de ENR 5.1.
Interpreta círculos con centro/radio (NM, km o m) y polígonos con vértices,
incluidas coordenadas DMS compactas. Convierte las geometrías a EPSG:32719 y
selecciona las que intersectan `AOI.buffer(aip_margin_m)`. El margen reside en
`config/aereo.json` (300 m por defecto); la geometría publicada conserva el
alcance original, sin agrandar la zona.

Cada registro seleccionado conserva su geometría, centro/radio o cantidad de
vértices, límites verticales extraídos del PDF, página, texto original y
condiciones. El paquete A3 incluye `parser_report` con el inventario, el estado
de cada registro, el margen y las excepciones. P10, R32 y R45–R48 son formas
no soportadas: si una coordenada legible está a menos de 50 km del AOI, el
extractor falla; si están lejos, quedan reportadas como `no_soportada_lejana`.
P51 y los sectores R45–R48 sin pares de coordenadas completos aparecen en la
lista explícita de excepciones, con motivo.
Si un polígono soportado necesita reordenamiento por vértices inválidos, su
envolvente convexa se mide en EPSG:32719: si intersecta el AOI más el margen AIP
la transformación falla con el código; si está lejos se conserva el
reordenamiento y se reporta la distancia hull–AOI.

Esta transformación no omite casos sin dejar constancia ni constituye una
autorización de vuelo. Los límites verticales se conservan como texto fuente;
la planificación actual mantiene la exclusión espacial 2D conservadora.

## Diccionario del registro A3

| Campo | Significado |
|---|---|
| `provider_id` / `code` | Código estable, p. ej. `SC-P29`. |
| `geometry` | Polígono/círculo original GeoJSON WGS84; el análisis usa EPSG:32719. |
| `lower_limit` / `upper_limit` | Límites verticales extraídos; texto fuente, no se aplican al ruteo. |
| `conditions` / `original_record` | Texto ENR 5.1 conservado para auditoría. |
| `document_page` | Página PDF donde se ubicó el registro. |
| `geometry_type` | `circle` o `polygon`. |
| `center`, `radius_m` | Centro WGS84 y radio en m para círculos. |
| `vertices` | Cantidad de vértices leídos para polígonos. |

El paquete de extracción agrega `parser_report` (inventario, márgenes, selección,
distancia/estado, formas no soportadas y excepciones); no es una columna de
`routing.airspace_zones`. La carga persiste en `routing.hazards` y
`routing.airspace_zones` (`code`, límites, condiciones, página y texto original).

## Modelo de falla en rutas

Las zonas A3 seleccionadas se tratan como restricciones duras y estáticas en
2D. Se excluye todo arco cuya línea intersecte una geometría publicada, y se
rechaza la consulta si una zona intersecta el origen, destino o base que
corresponda al modo. El margen de 300 m solo determina qué zonas del PDF se
cargan; la geometría aplicada a rutas conserva el límite original. No se
filtran por fecha ni se usan los límites verticales o condiciones para permitir
el paso. Las restricciones permanecen vigentes hasta reemplazar la instantánea
de datos.

El modelo supone que toda intersección horizontal implica exclusión,
independientemente de altitud, horario o condición operacional. El catálogo
extraído de ENR 5.1 tampoco equivale a todas las restricciones aeronáuticas
vigentes; el sistema no certifica autorización ni despeje vertical.
