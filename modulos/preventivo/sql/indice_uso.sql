WITH lecturas_diarias AS (
  SELECT
    maquina_id,
    DATE(ts) AS dia,
    ARRAY_AGG(horas_funcionamiento ORDER BY ts DESC LIMIT 1)[OFFSET(0)] AS horas_fin_dia,
    AVG(carga_transportada) AS carga_promedio,
    AVG(rpm) AS rpm_promedio,
    AVG(temperatura) AS temperatura_promedio
  FROM `{dataset}.lectura_telemetria_unica`
  WHERE DATE(ts) >= DATE_SUB(@fecha_desde_global, INTERVAL 1 DAY)
  GROUP BY maquina_id, dia
)
SELECT
  maquina_id,
  dia,
  horas_fin_dia
    - LAG(horas_fin_dia) OVER (PARTITION BY maquina_id ORDER BY dia) AS horas_trabajadas_dia,
  carga_promedio,
  rpm_promedio,
  temperatura_promedio
FROM lecturas_diarias
ORDER BY maquina_id, dia;