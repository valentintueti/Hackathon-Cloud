CREATE OR REPLACE TABLE `{dataset}.kpi_diario`
PARTITION BY dia
CLUSTER BY maquina_id
AS
WITH lecturas AS (
  SELECT
    maquina_id, modelo_id, zona_id,
    DATE(ts, 'America/Lima') AS dia,
    horas_funcionamiento, consumo_combustible, carga_transportada, rpm, estado
  FROM `{dataset}.lectura_telemetria_unica`
  WHERE DATE(ts, 'America/Lima') BETWEEN DATE_SUB(CURRENT_DATE('America/Lima'), INTERVAL {dias} DAY)
                                     AND DATE_SUB(CURRENT_DATE('America/Lima'), INTERVAL 1 DAY)
),

por_dia AS (
  SELECT
    maquina_id,
    dia,
    MAX(modelo_id) AS modelo_id,
    MAX(zona_id) AS zona_id,
    GREATEST(MAX(horas_funcionamiento) - MIN(horas_funcionamiento), 0) AS horas,
    AVG(IF(COALESCE(estado, '') != 'detenida' AND COALESCE(rpm, 1) > 0, consumo_combustible, NULL)) AS consumo_l_h,
    AVG(IF(carga_transportada > 0, carga_transportada, NULL)) AS carga_t,
    COUNTIF(rpm > 0 AND rpm < {rpm_ralenti}) AS lecturas_ralenti,
    COUNTIF(rpm > 0) AS lecturas_encendida
  FROM lecturas
  GROUP BY maquina_id, dia
)

SELECT
  maquina_id,
  dia,
  modelo_id,
  zona_id,
  ROUND(horas, 2) AS horas_trabajadas,
  ROUND(horas / {horas_turno} * 100, 1) AS utilizacion_pct,
  ROUND(SAFE_DIVIDE(lecturas_ralenti, lecturas_encendida) * 100, 1) AS ralenti_pct,
  ROUND(consumo_l_h * horas, 1) AS litros,
  ROUND(carga_t, 2) AS carga_promedio_t,
  ROUND(COALESCE(consumo_l_h, 0) * horas * {precio_litro} + horas * {costo_hora}, 2) AS costo,
  ROUND(SAFE_DIVIDE(COALESCE(consumo_l_h, 0) * {precio_litro} + {costo_hora}, carga_t), 3) AS costo_hora_por_t
FROM por_dia