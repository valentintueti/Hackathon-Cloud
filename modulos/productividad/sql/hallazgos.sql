WITH semana AS (
  SELECT
    maquina_id,
    MAX(modelo_id) AS modelo_id,
    ARRAY_AGG(zona_id IGNORE NULLS ORDER BY dia DESC LIMIT 1)[SAFE_OFFSET(0)] AS zona_id,
    COUNT(*) AS dias,
    ROUND(AVG(utilizacion_pct), 1) AS utilizacion_pct,
    ROUND(AVG(horas_trabajadas), 2) AS horas_promedio,
    COUNTIF(horas_trabajadas > @horas_max) AS dias_excesivos,
    ROUND(AVG(ralenti_pct), 1) AS ralenti_pct,
    ROUND(SUM(costo), 2) AS costo_total,
    ROUND(AVG(carga_promedio_t), 2) AS carga_promedio_t,
    ROUND(AVG(costo_hora_por_t), 3) AS costo_hora_por_t
  FROM `{dataset}.kpi_diario`
  WHERE dia >= DATE_SUB(CURRENT_DATE('America/Lima'), INTERVAL @dias_analisis DAY)
  GROUP BY maquina_id
),

modelo AS (
  SELECT
    modelo_id,
    COUNT(*) AS maquinas,
    APPROX_QUANTILES(carga_promedio_t, 2)[SAFE_OFFSET(1)] AS carga_mediana_modelo,
    APPROX_QUANTILES(costo_hora_por_t, 2)[SAFE_OFFSET(1)] AS costo_mediana_modelo
  FROM semana
  WHERE modelo_id IS NOT NULL
  GROUP BY modelo_id
)

SELECT *
FROM (
  SELECT
    s.*,
    m.carga_mediana_modelo,
    m.costo_mediana_modelo,
    ARRAY_CONCAT(
      IF(s.utilizacion_pct < @util_min, ['baja_utilizacion'], []),
      IF(s.dias_excesivos >= @dias_excesivos_min, ['jornada_excesiva'], []),
      IF(m.maquinas >= 3
         AND s.costo_hora_por_t > m.costo_mediana_modelo * (1 + @pct_costo / 100)
         AND s.carga_promedio_t < m.carga_mediana_modelo * (1 - @pct_carga / 100),
         ['baja_productividad_alto_costo'], [])
    ) AS hallazgos
  FROM semana s
  LEFT JOIN modelo m ON m.modelo_id = s.modelo_id
)
WHERE ARRAY_LENGTH(hallazgos) > 0
ORDER BY ARRAY_LENGTH(hallazgos) DESC, costo_total DESC
