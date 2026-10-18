# Datos del simulador aéreo y contratos

## Fuentes y adquisición

Solo se usan S1-S7 del informe de referencia: SENAPRED BOMBEROS; vegetación CONAF
2019 distribuida por CIREN; Copernicus GLO-30 S34/W072; Open-Meteo ECMWF IFS 0,25°;
NASA FIRMS VIIRS NOAA-20 C2 regional de siete días; DGAC AIP ENR 5.1; densidad de
incendios SENAPRED 2020-2024. OSM queda como fondo opcional, sin intervenir en rutas.
La capa CARABINEROS y la red vial se conservan únicamente para regresiones.

`Infraestructura.descargar_aereo` obtiene S1-S7. ArcGIS se consulta primero por
IDs y después por bloques de 200, conservando cada respuesta original. Se compara
el conjunto de IDs, sin duplicados ni páginas truncadas. El manifiesto activo se
reemplaza solamente si las siete adquisiciones terminan bien. Un fallo produce
`adquisicion_incompleta.json`, conserva el manifiesto previo y aborta la publicación.

Los originales están en `datos/entrada/aereo`. Los nombres contienen el SHA-256 de
sus bytes. `manifest.json` documenta versión, envolvente WGS84, fecha UTC, errores
y `sources.S1..S7`: producto, URL, HTTP, archivo, bytes, SHA-256 y obtención.
Los servicios ArcGIS añaden `ids`, `pages`, `id_field` y `record_count`.
La envolvente sirve para adquisición; después se filtra con el polígono completo.
No se asigna una licencia no declarada por un proveedor: conservar atribución y
revisar sus términos antes de redistribuir datos para otros usos.

## Infraestructura I, contrato 3.0

Se conserva el sobre general de `Infraestructura/DICCIONARIO.md`: UUID de run y
dataset, fuente, fechas, CRS, hashes, linaje, nodos y arcos. La fuente nueva es
`DERIVED_AERIAL`, el constructor `aerial-grid-v1` y el perfil está en
`config/aereo.json`. Los parámetros y todos los insumos participan en la identidad
de la salida. Diferentes alcances tienen runs distintos.

Los nodos tienen ID estable, clave natural, tipo y Point WGS84. `navegacion` es
un punto derivado de malla; `vigilancia` es uno situado en Bosques o Praderas y
Matorrales de S2; `base_candidata` conserva un punto real S1 sin ajustarlo a una
calle. Los puntos de navegación no son instalaciones observadas.

La malla está anclada a múltiplos UTM de 800 m. Se toma la unión simétrica de
hasta ocho vecinos a menos de 1.500 m, verificando el segmento completo contra
el AOI WGS84, sin buffer. Cada sentido es una fila, `reverse_cost=-1`; solo el
viento puede hacer diferentes sus tiempos. Las longitudes las calcula PostGIS
en EPSG:32719. No se aplican giros, sentidos de calles ni proximidad a OSM.

La malla de navegación ahora cubre todo el polígono, no solo la vegetación; esta
es una modificación metodológica explícita respecto del informe original. La
resolución discretiza el espacio y no acredita el óptimo en todo el espacio libre.
Los extremos de consulta se incorporan temporalmente, conservando su posición,
con vecinos admisibles. Se incluye el segmento directo entre extremos cuando
queda completamente dentro del AOI. Ese enlace directo no tiene el límite local
de 1.500 m y no se persiste ni se presenta como corredor observado.

`lineage` incluye límite exacto y hash, configuración, perfil, manifest y fuentes,
`context_sha256` y la marca `derived_corridors=true`. `context.json` es un artefacto
interno preparado por I: contiene `records`, hora de referencia, adquisición de
S4, perfil, reparaciones y metadata raster. Su hash se verifica antes de extraer
M1-M4/A1-A4. No cuenta como otra fuente. `aerial_models` almacena este contexto
inmutable de la instantánea; los endpoints no modifican nodos ni arcos publicados.

## Ocho salidas ET y cargas

Cada módulo en Metadata/Amenazas extrae un JSON y el mismo módulo con
`--load RUTA` realiza su carga. No vuelve a descargar al cargar. El sobre común es:

| Campo | Tipo y significado |
|---|---|
| schema_version | `aerial-dataset-1`. |
| run_id / dataset_id | UUID; dataset_id=UUIDv5(run_id, clave). |
| dataset_key / source_id | M1-M4/A1-A4 y S1-S7 según la tabla. |
| observed_at / extracted_at | Fechas UTC del corte de adquisición conjunto; no fechas históricas de captura de todos los productos ni emisión del pronóstico. Las fechas específicas del proveedor se conservan por registro/linaje. |
| lineage | Fuente con sus respuestas/hashes, AOI y hash del contexto preparado. |
| records | Lista tipada descrita abajo; una colección legítimamente vacía tiene estado `empty` en la BD. |

| Salida → tablas | Campos de cada registro |
|---|---|
| M1/S1 → base_metadata | `provider_id` texto del objectid_1, `node_id` BIGINT del nodo exacto, `name`, `commune`, `address` originales, `geometry` Point. Una base candidata no acredita espacio de despegue ni permiso. |
| M2/S2 → landcover | `provider_id`, `category`=uso original, `source_year=2019`, `repaired` booleano y `geometry` MultiPolygon recortada. Los atributos originales no usados siguen conservados en las respuestas. |
| M3/S3 → node_elevation | `node_id`, `elevation_m` metros sobre el datum vertical del producto, `quality=valid/nodata`. `null` conserva NoData. Muestreo del píxel en cada nodo, sin inventar altura de vuelo ni interpolar un inventario de obstáculos. |
| M4/S4 → weather | `valid_at` UTC, `cell` [lon,lat] efectivamente devuelta; temperatura °C, humedad %, viento y rachas m/s, dirección meteorológica en grados y precipitación mm. La misma celda se asigna al área; no se inventa variación local. `issued_at` SQL queda NULL: el servicio no declara emisión en esta respuesta. |
| A1/S4 → hazards + weather_hazards | Hora `valid_at`, `provider_id`=hora, `state` active/unknown, `reason`, `geometry` del área. Se deriva una fila por hora fuera del perfil o con campos requeridos ausentes, vinculada a M4. |
| A2/S5 → hazards + thermal_events | ID fecha/coordenadas, `point` original y `geometry` buffer, `acquired_at` UTC de detección, `confidence` n/h, FRP en MW, `buffer_m=250`. Se excluye confianza l; un valor desconocido falla. Se conservan detecciones del AOI del original de siete días; por consulta solo afectan las de las últimas 24 h y no futuras. |
| A3/S6 → hazards + airspace_zones | Código, centro/radio o vértices, geometría y página, texto original, condiciones y límites verticales conservados. El parser inventaría ENR 5.1 y carga las geometrías soportadas que intersectan el AOI ampliado por `aip_margin_m`; la instantánea actual selecciona SC-P29 y SC-P50. No es un inventario completo de restricciones de vuelo. Se aplica exclusión 2D conservadora. |
| A4/S7 → hazards + historical_risk | ID, clase ordinal 1-5, etiqueta, período 2020-2024, reparación y MultiPolygon. Estado `historical`, nunca un incendio activo. |

Los cargadores comprueban identidad, contenido contra el contexto validado,
transacción e idempotencia por bytes. `record_count` cuenta una amenaza una vez,
aunque ocupe la tabla general y un subtipo. No se reinterpretan errores HTTP como
colecciones vacías. Un valor desconocido no se sustituye por cero.

## CRS, raster y reglas del modelo

GeoJSON y API usan WGS84 `[longitud,latitud]`; BD y medidas usan UTM 19S,
EPSG:32719. Se comprueban geometrías completas y se registran reparaciones de
polígonos temáticos; el AOI del usuario no se repara ni cambia silenciosamente.

El TIFF S3 conserva su CRS, affine, dimensiones, bandas, escalas, offsets,
unidades y NoData en el contexto. La escala/offset se aplica una vez. El GLO-30
es un DSM, aproximadamente 30 m, con alturas referidas a EGM2008; no se realiza
conversión de datum vertical ni cálculo de despeje.
[Documentación del producto Copernicus](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM).

## Modelos de falla aplicados por el ruteador

La tabla resume la ruta `proposed` de `core/aerial_routing.py`. Los controles
duros eliminan arcos intersectados y rechazan extremos afectados; la referencia
matemática por distancia (`method=reference`) omite estas amenazas.

| Amenaza | Efecto en nodos y arcos | Vigencia en una consulta | Supuestos y tratamiento de desconocidos |
|---|---|---|---|
| A1 clima, derivada de M4 | Cierre global: no se evalúan rutas si la hora no tiene M4 válido, faltan variables requeridas o el tiempo excede el perfil. No es una máscara local de nodos/arcos. A1 se carga como diagnóstico horario; `available()` valida M4 directamente. | Fila válida en `[valid_at, valid_at + 1 h)`. Snapshot permite hora histórica del escenario; online rechaza adquisición con antigüedad >90 min y una hora del escenario a >1 h del reloj actual. Ida y regreso usan la misma hora. | Viento/racha ≥8 m/s o temperatura fuera de [-5,40] °C no son factibles; falta de datos da estado desconocido. Una celda meteorológica representa todo el AOI; el viento a 10 m aproxima el viento a altura de vuelo. |
| A2 FIRMS | Buffer métrico de cada foco `n/h`: arcos que lo intersectan quedan excluidos; el escenario se rechaza si afecta origen, destino o base de regreso. No tiene penalización gradual. | Desde la detección hasta 24 h inclusive; no se consideran focos futuros. | Radio fijo configurable (250 m por defecto), confianza `l` omitida; confianza desconocida falla. El buffer no modela propagación ni crecimiento del incendio. |
| A3 AIP | Exclusión dura 2D: se eliminan arcos intersectados y se rechazan extremos afectados. El margen de 300 m selecciona zonas al cargar, pero no agranda la geometría usada al rutear. | Sin vencimiento temporal dentro de la instantánea; cambia al reemplazar los datos. | No se filtra por límites verticales, horario ni condiciones: cualquier intersección horizontal bloquea. El catálogo ENR 5.1 parseado no certifica la totalidad de restricciones ni autorización de vuelo. |
| A4 historial | No bloquea nodos ni arcos. Cada arco recibe exposición según longitud por clase; las alternativas generadas se ordenan por exposición y luego tiempo después de límites de presupuesto y desvío. | Cartografía histórica 2020–2024, sin caducidad por hora de consulta. | Factor `(clase-1)/4`; tramos solapados usan la clase máxima. Tramos sin cobertura se consideran desconocidos y reciben factor 1, la penalización máxima. Es un indicador, no probabilidad. |

En A2/A3, además de filtrar arcos, el ruteador verifica intersección de la
geometría bloqueada con los extremos relevantes del modo. No elimina de forma
persistente los nodos de la red publicada. Las geometrías se transforman a
EPSG:32719 para el análisis. Los eventos enviados por API son escenarios
sintéticos y no modifican las cargas A1–A4.

El tiempo de arco usa la ecuación horizontal del informe: velocidad aérea
10 m/s, vector de viento transformado desde su dirección de procedencia y
avance dirigido; se rechazan avances no positivos. La exposición A4 no se suma
al costo temporal de pgRouting: sirve como criterio de ordenación secundaria
entre alternativas generadas (hasta `alternatives` rutas por tramo) que ya satisfacen
los límites temporales; no garantiza un óptimo global de exposición.

## Costo, criterio de alternativas y defaults

En `method=proposed`, pgRouting minimiza tiempo de vuelo. Para un arco dirigido
de longitud `L_m` metros, velocidad aérea `V_a` m/s y vector de viento horizontal
`w` m/s, sea `u` el vector unitario del arco, `w_parallel = w·u` y
`w_cross² = max(0, |w|² - w_parallel²)`. Si
`w_cross² >= V_a²` o `V_gs <= 0`, el arco se descarta; si no:

```text
V_gs = sqrt(V_a² - w_cross²) + w_parallel            [m/s]
costo_arco = L_m / V_gs                               [s]
costo_misión = Σ costo_arco(ida) + Σ costo_arco(vuelta) + observación [s]
```

La dirección meteorológica se convierte en vector de procedencia antes de
proyectarla sobre cada arco; por eso el costo puede diferir entre sentidos. El
presupuesto disponible es `flight_minutes * 60 * (1 - reserve_fraction) -
elapsed_s`. Se generan hasta `alternatives` rutas por tramo; se conservan las
parejas de ida/vuelta cuyo tiempo no excede ni ese presupuesto ni
`detour_factor * tiempo_mínimo`. A4 no tiene un peso sumado al tiempo: `exposure_m`
es metros ponderados (metros equivalentes) que se usan para ordenar las parejas
admisibles antes del tiempo y los IDs. Los bloqueos A2/A3 y el cierre climático
A1 son restricciones duras, no pesos compensables. `method=reference` minimiza
longitud en km y omite amenazas, viento, retorno y autonomía.

| Parámetro (`config/aereo.json`) | Default | Unidad/efecto |
|---|---:|---|
| `air_speed_ms` | 10 | m/s; velocidad aérea usada en `V_gs`. |
| `flight_minutes` | 25 | min de misión. |
| `reserve_fraction` | 0.2 | fracción no utilizable; deja 1.200 s antes de descontar lo consumido. |
| `observation_s` | 60 | s de observación, una vez en ida de misión. |
| `wind_limit_ms` | 8 | m/s; velocidad o racha igual/superior invalida clima. |
| `temperature_min_c` / `temperature_max_c` | -5 / 40 | °C; extremos inclusivos. |
| `weather_max_age_minutes` | 90 | min de antigüedad máxima de adquisición en modo online. |
| `thermal_buffer_m` / `thermal_window_hours` | 250 / 24 | m de radio / h desde FIRMS. |
| `aip_margin_m` | 300 | m para seleccionar zonas ENR 5.1 al preparar el contexto. |
| `alternatives` / `detour_factor` | 3 / 1.2 | alternativas por tramo / máximo relativo al tiempo mínimo. |
| `grid_m` / `neighbours` / `max_link_m` | 800 / 8 / 1.500 | m / vecinos / distancia máxima de enlace persistente. |
| `clearance_verified` / `operationally_certified` | false / false | indicadores de seguridad/certificación; no se afirman. |

**Ejemplo de un arco de 1.000 m:** sin viento ni amenazas,
`V_gs=10 m/s` y cuesta `100 s`. Con viento de frente de 2 m/s,
`V_gs=8 m/s` y cuesta `125 s`. Si el buffer FIRMS vigente o una zona AIP
intersecta el arco, se excluye en lugar de asignarle un costo alto. Si es
admisible, pero 500 m caen en clase histórica 5 y 500 m en clase 3, su exposición
es `500*(5-1)/4 + 500*(3-1)/4 = 750 m ponderados`; este valor ordena rutas
factibles y no se suma a los segundos. Un arco fuera del mapa histórico recibe
factor 1 en la parte desconocida.

## API aérea

`GET /api/aereo/mapa`: red, bases, ejemplos, perfil, hora de referencia, las cuatro
metadata y amenazas del contexto. Vegetación se simplifica **solo para dibujar**
a 3 m; cálculo y originales mantienen la geometría completa. Elevación se muestra
en tooltips y meteorología en el selector de horas.

`POST /api/aereo/rutas` y `/api/aereo/replanificar` reciben JSON:

```json
{
  "origin": [-71.657239211, -33.10190169],
  "destination": [-71.657216935, -33.093556172],
  "mode": "mission",
  "method": "proposed",
  "time": "2026-10-17T00:00:00Z",
  "events": [],
  "phase": "outbound",
  "elapsed_s": 0,
  "on_edge": false
}
```

Es un ejemplo histórico reproducible, no una solicitud de vuelo actual.
`mode=trip` calcula solo ida; `mission` incluye observación y regreso al inicio.
`method=reference` es una referencia matemática por distancia, sin amenazas ni
presupuesto, y se etiqueta así. `proposed` aplica restricciones, tiempo y exposición.
`phase` puede ser outbound, return o emergency_return; las dos últimas requieren
misión. Replanificar admite `position` en un nodo existente o extremo de consulta,
con tolerancia de 1 mm; conserva el origen como lugar de retorno.

Los eventos recibidos son **siempre sintéticos**, con ID, geometría Point/Polygon,
estado blocked/unknown/resolved y observed_at UTC en el reloj del escenario.
Point admite radio 0<r≤10.000 m. Máximo 20 eventos y cuerpo de 256 KiB. No se
anticipan mensajes futuros y se ignoran los antiguos frente a uno más nuevo.
Resolver uno no rehabilita otro superpuesto ni una exclusión AIP.

La respuesta es FeatureCollection con `run_id`, estado, causa, extremos, hora,
tiempo consumido/restante y `alternatives`. Cada alternativa contiene `outbound`,
`return_path`, secuencias de IDs y coordenadas, longitud km, segundos de vuelo y
observación, exposición en metros ponderados y metros sin dato. El indicador
`within_50m_of_first_fraction` describe cercanía espacial de ida, no independencia
ante fallas. IDs BIGINT viajan como texto. Los arcos temporales tienen IDs negativos
distintos de -1, reservado al terminador de pgRouting.

La referencia produce D1 y D2 con pgr_dijkstra por km, excluyendo individualmente
arcos de D1 para encontrar la segunda. El propuesto usa pgr_KSP/Yen por segundos:
tres idas y tres retornos, hasta nueve parejas, presupuesto 1.200 s menos lo
consumido y límite 1,20 del mínimo restante. Ordena por exposición, tiempo e IDs.
No garantiza óptimo global de exposición ni caminos disjuntos.

Estados normales: `ready`, `no_route`, `not_feasible`, `unknown`, `interrupted`.
HTTP 422 indica entrada inválida; HTTP 503, servicio/consulta no disponible.
Todas las respuestas mantienen `clearance_verified=false` y
`operationally_certified=false`. La interrupción durante un segmento no genera
maniobras autónomas. La observación se suma una sola vez y regresar sin completar
la vigilancia no se registra como misión completada.

`/health` separa `etl_complete` de `phase2_complete`: tener nueve cargas no
acredita toda la rúbrica, sus métricas comparativas ni una validación de vuelo.

## Software y habilidades aplicadas

Geomaster se utilizó para procedencia, CRS, unidades, NoData y resolución;
webapp-testing para pruebas Python Playwright, reconocimiento del DOM, capturas y
errores del navegador. Referencia verificada en arXiv (revisión disponible v2):
Kassis, T., Agarwal, V., He, Y., Patel, D. y Brueckner, A. M. (2026).
*Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*.
https://doi.org/10.48550/arXiv.2609.00065 . Esta referencia describe la habilidad,
no valida los resultados de ruteo de este proyecto.
