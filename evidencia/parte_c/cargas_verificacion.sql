-- Conteos de las cuatro amenazas para la última publicación completa.
-- El dataset A2 vacío debe existir con status='empty' y record_count=0.
WITH selected_run AS (
    SELECT run_id
    FROM routing.runs
    WHERE status = 'ready' AND scope = 'completo'
    ORDER BY finished_at DESC
    LIMIT 1
),
counts AS (
    SELECT 'routing.datasets'::text AS tabla, d.dataset_key,
           count(*)::bigint AS filas, sum(d.record_count)::bigint AS registros,
           max(d.status) AS estado
    FROM routing.datasets d
    JOIN selected_run r USING (run_id)
    WHERE d.dataset_key IN ('A1', 'A2', 'A3', 'A4')
    GROUP BY d.dataset_key
    UNION ALL
    SELECT 'routing.hazards', h.dataset_key, count(*)::bigint, NULL::bigint, NULL::text
    FROM routing.hazards h
    JOIN selected_run r USING (run_id)
    WHERE h.dataset_key IN ('A1', 'A2', 'A3', 'A4')
    GROUP BY h.dataset_key
    UNION ALL
    SELECT 'routing.weather_hazards', 'A1', count(*)::bigint, NULL::bigint, NULL::text
    FROM routing.weather_hazards t
    JOIN selected_run r USING (run_id)
    UNION ALL
    SELECT 'routing.thermal_events', 'A2', count(*)::bigint, NULL::bigint, NULL::text
    FROM routing.thermal_events t
    JOIN selected_run r USING (run_id)
    UNION ALL
    SELECT 'routing.airspace_zones', 'A3', count(*)::bigint, NULL::bigint, NULL::text
    FROM routing.airspace_zones t
    JOIN selected_run r USING (run_id)
    UNION ALL
    SELECT 'routing.historical_risk', 'A4', count(*)::bigint, NULL::bigint, NULL::text
    FROM routing.historical_risk t
    JOIN selected_run r USING (run_id)
)
SELECT tabla, dataset_key, filas, registros, estado
FROM counts
ORDER BY tabla, dataset_key;
