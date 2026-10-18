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

Esta transformación no omite casos sin dejar constancia ni constituye una
autorización de vuelo. Los límites verticales se conservan como texto fuente;
la planificación actual mantiene la exclusión espacial 2D conservadora.
