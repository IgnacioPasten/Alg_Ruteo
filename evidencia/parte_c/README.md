# Evidencia de Parte C: amenazas, pesos y cargas

Paquete de fragmentos verificables para preparar las láminas 11–15. Las
capturas de interfaz se conservan de la prueba funcional existente; los
resultados de ETL, SQL, pruebas y hashes son evidencia reproducible de esta
rama.

## Lámina 11 — Modelos de falla

| Amenaza | Regla aplicada |
|---|---|
| A1 clima | Cierre global por M4 fuera del perfil o incompleto; validez horaria. |
| A2 FIRMS | Exclusión dura de arcos/extremos dentro del buffer, foco de hasta 24 h. |
| A3 AIP | Exclusión horizontal 2D; geometrías seleccionadas al preparar la instantánea. |
| A4 historial | Penalización de exposición en metros ponderados; no cierra rutas. |

Detalle y supuestos: [modelos de falla](../../docs/DATOS_AEREOS.md#modelos-de-falla-aplicados-por-el-ruteador).
Implementación consultada: `core/aerial_routing.py`, funciones `available`,
`exposure` y `calculate`. Capturas existentes:
[rutas](../aereo_2026-10-17/interfaz/rutas.png) y
[bloqueo](../aereo_2026-10-17/interfaz/bloqueo.png).

## Lámina 12 — Costo y defaults

El costo propuesto es `L_m / V_gs` en segundos; A4 es orden secundario y no un
peso sumado al tiempo. Un arco de 1.000 m cuesta 100 s en calma, 125 s con 2 m/s
de viento frontal y queda excluido si FIRMS/AIP lo intersecta. La exposición
histórica de ejemplo es 750 m ponderados para 500 m de clase 5 y 500 m de clase
3.

Fórmula, unidades y tabla completa:
[costo y defaults](../../docs/DATOS_AEREOS.md#costo-criterio-de-alternativas-y-defaults).
Configuración fuente: `config/aereo.json`.

## Lámina 13 — Cargas y consulta SQL

La ejecución Docker completa verificada fue el run
`8af11e49-f152-525a-ba52-4c5c5881b6f3`.

| Amenaza | Filas en datasets | `record_count` | `routing.hazards` | Tabla tipada | Filas tipadas | Estado |
|---|---:|---:|---:|---|---:|---|
| A1 | 1 | 9 | 9 | `weather_hazards` | 9 | `valid` |
| A2 | 1 | 0 | 0 | `thermal_events` | 0 | `empty` |
| A3 | 1 | 2 | 2 | `airspace_zones` | 2 | `valid` |
| A4 | 1 | 17 | 17 | `historical_risk` | 17 | `valid` |

`routing.datasets` guarda exactamente una fila por dataset y el estado vacío
de A2; no se inventa un foco ni un evento placeholder. El SQL reproducible,
que selecciona la última publicación completa y cuenta tablas generales y
tipadas, está en [cargas_verificacion.sql](cargas_verificacion.sql). Los
conteos se consultaron directamente en PostgreSQL del servicio Docker.

## Lámina 14 — Diccionarios

- [A1](../../Amenazas/a1_meteorologia.md#diccionario-del-registro-a1): cinco
  campos del registro; carga común + enlace `weather_id` a M4.
- [A2](../../Amenazas/a2_firms.md#diccionario-del-registro-a2): siete campos;
  confianza `l` excluida y cero filas representado como `empty`.
- [A3](../../Amenazas/a3_aip.md#diccionario-del-registro-a3): límites, texto,
  página, geometría y reporte separado de registros.
- [A4](../../Amenazas/a4_historial.md#diccionario-del-registro-a4): siete
  campos; periodo histórico, clase ordinal y marca de reparación.

Contraste de carga: `core/aerial_etl.py`, rama de insert por `dataset_key`.

## Lámina 15 — Salvaguarda AIP y reproducibilidad

Los polígonos inválidos se validan usando su convex hull en EPSG:32719. Si el
hull intersecta `AOI.buffer(aip_margin_m)`, se aborta con el código; los casos
lejanos se reordenan y registran `geometry_reordered` y la distancia al AOI.
R68 real pasa como caso lejano. Los casos sintéticos cercanos/lejanos están en
`tests/test_a3_aip.py`.

La línea base actualizada es
[linea_base_amenazas_v2.json](../linea_base_amenazas_v2.json): los hashes de
A1–A4 permanecen iguales a la v2 previa; solo cambia `context_sha256` por el
nuevo detalle del reporte parser. Se preserva
[a3_v1.json](../a3_v1.json). Suite Docker: ver `pruebas_resultado.json`
con 99 pruebas, 0 fallas, 0 errores y 0 omisiones. El resultado focalizado real
y los dos casos sintéticos se pueden regenerar con
`docker compose run --rm etl python -m unittest tests.test_a3_aip -v`.
