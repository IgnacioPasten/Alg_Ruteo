# Simulador aéreo de drones en Valparaíso

Aplicación Docker con PostGIS, pgRouting y Leaflet. Permite elegir inicio y destino
en el polígono del usuario, comparar rutas aéreas, dibujar bloqueos simulados y
comprobar ida, observación, retorno y presupuesto restante.

**Es el simulador académico del informe: despeje vertical no verificado.**
Las calles no condicionan el vuelo. OSM solo es un fondo opcional. Los puntos de
navegación y corredores son derivados; no representan vuelos observados.

## Ejecutar

Desde Bash de Git o WSL, con Docker activo:

```bash
./main probar
./main
```

Abrir http://127.0.0.1:8080 . El host no necesita Python ni PostgreSQL.
El arranque predeterminado ejecuta los nueve ETL y sus cargas; .env se genera con
contraseñas aleatorias y nunca se versiona.

```bash
./main iniciar --mode online  # actualiza S1-S7 y crea otra instantánea
./main estado
./main detener               # conserva volúmenes
```

En la validación del 17 de octubre, la actualización online completa quedó
bloqueada por un fallo DNS de `aipchile.dgac.gob.cl`. El arranque snapshot sí
funcionó desde una BD vacía con el PDF oficial conservado y sus hashes verificados.
El proceso online aborta ante una fuente incompleta y conserva la publicación anterior.

La instancia validada en este equipo usa http://127.0.0.1:18081 :

```bash
COMPOSE_PROJECT_NAME=udp-ruteo-valpo-aereo WEB_PORT=18081 ./main estado
COMPOSE_PROJECT_NAME=udp-ruteo-valpo-aereo WEB_PORT=18081 ./main
```

## Usar el mapa

1. Elegir una base candidata o pulsar Seleccionar inicio y hacer clic en el mapa.
2. Elegir destino por clic, coordenadas o un objetivo de vigilancia de ejemplo.
3. Revisar la hora UTC y el selector de horas del pronóstico. La hora de descarga
   puede quedar fuera del perfil: no se relajan los umbrales para dibujar rutas.
4. Calcular hasta tres alternativas de misión o un trayecto de solo ida.
5. Dibujar un bloqueo circular/poligonal y recalcular. En Estado de misión pueden
   seleccionarse posición en un nodo, fase y tiempo ya consumido.
6. Descargar el resultado con el escenario para reproducirlo.

Una hora histórica admisible sirve para reproducir la simulación, no demuestra
que las condiciones actuales permitan volar. La referencia Dijkstra por distancia
ignora amenazas y autonomía y aparece identificada como referencia matemática.

## Red, fuentes y límites

La instantánea genera **87 nodos y 556 arcos**, con el GeoJSON original de
54,92 km². Se usa una malla UTM de 800 m, ocho vecinos y radio local de 1.500 m,
además de conexiones temporales verificadas de los extremos elegidos. No se
modifican snapshots publicados al consultar.

La base candidata inicial vuelve a ser **Décima Sexta de Valparaíso, Bomberos
SENAPRED 104**, en [-71.657239211, -33.10190169]. Su aislamiento vial no implica
un aislamiento aéreo. No se desplaza el punto ni se presupone autorización de uso.
El inicio puede cambiarse libremente dentro del polígono para la simulación.

S1-S7 del informe están adquiridas: instalaciones, vegetación CONAF 2019, DSM
Copernicus, pronóstico Open-Meteo, FIRMS, AIP y recurrencia histórica. Los nueve
ETL tienen diccionarios y cargas tipadas. FIRMS devuelve cero detecciones aceptadas
en este AOI; se registra como colección vacía, no como ausencia de incendio.
AIP ENR 5.1 inventaría zonas SC-P, SC-R y SC-D; selecciona geometrías soportadas
que alcanzan el AOI ampliado 300 m. El reporte A3 detalla formas no soportadas y
excepciones. No es autorización de vuelo.

El perfil académico conserva 10 m/s, 25 min, reserva 20 % y observación 60 s:
presupuesto utilizable 1.200 s. La selección propuesta compara tiempo y exposición,
respeta bloqueos y comprueba regreso. No modela energía vertical, sensores,
obstáculos individuales, navegación reactiva ni telemetría real.

## Documentación y evidencia

- [Datos, API, parámetros y diccionario](docs/DATOS_AEREOS.md).
- [Originales S1-S7](datos/entrada/aereo/README.md).
- [Informe y verificaciones](evidencia/aereo_2026-10-17/INFORME.md).
- [SQL inicial](BD/crear_bd.sql) y [migración aérea](BD/migraciones/003_red_aerea.sql).
- [Diagrama de la ampliación](BD/diagrama_aereo.svg).

Se conservan la malla antigua y la implementación vial para regresiones, con
config/proyecto_legacy.json y config/proyecto_vial.json. La migración nueva no
reescribe el DDL ni las migraciones existentes. El esquema tiene 26 tablas.
`etl_complete` acredita las nueve cargas; `phase2_complete=false` no declara
terminada toda la evaluación de rúbrica o resiliencia del trabajo grupal.

Las habilidades geomaster y webapp-testing se aplicaron; su uso y la referencia
bibliográfica verificada de Scientific Agent Skills están documentados en
[Datos aéreos](docs/DATOS_AEREOS.md#software-y-habilidades-aplicadas).
