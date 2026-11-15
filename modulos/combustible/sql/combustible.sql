WITH dias AS (
  SELECT
    maquina_id,
    DATE(ts, 'America/Lima') AS dia,
    MAX(modelo_id) AS modelo_id,
    MAX(zona_id) AS zona_id,
    AVG(consumo_combustible) AS consumo_hora,
    AVG(carga_transportada) AS carga
  FROM `{dataset}.lectura_telemetria_unica`
  WHERE DATE(ts, 'America/Lima') BETWEEN DATE_SUB(CURRENT_DATE('America/Lima'), INTERVAL (@dias + 1) DAY)
                                     AND DATE_SUB(CURRENT_DATE('America/Lima'), INTERVAL 1 DAY)
    AND consumo_combustible IS NOT NULL
    AND COALESCE(estado, '') != 'detenida'
    AND (rpm IS NULL OR rpm > 0)
  GROUP BY maquina_id, dia
),

metrica AS (
  SELECT
    *,
    IF(carga > 0, consumo_hora / carga, consumo_hora) AS valor,
    IF(carga > 0, 'L/h por tonelada', 'L/h') AS unidad
  FROM dias
),

ayer AS (
  SELECT *
  FROM metrica
  WHERE dia = DATE_SUB(CURRENT_DATE('America/Lima'), INTERVAL 1 DAY)
),

-- Caso 1: ayer vs su propio historial
historia AS (
  SELECT maquina_id, unidad, AVG(valor) AS media, STDDEV(valor) AS desv, COUNT(*) AS n
  FROM metrica
  WHERE dia < DATE_SUB(CURRENT_DATE('America/Lima'), INTERVAL 1 DAY)
  GROUP BY maquina_id, unidad
),

caso_propio AS (
  SELECT
    a.maquina_id,
    a.unidad,
    h.media AS media_propia,
    SAFE_DIVIDE(a.valor - h.media, h.desv) AS z_propio,
    SAFE_DIVIDE(a.valor - h.media, h.media) * 100 AS pct_propio
  FROM ayer a
  JOIN historia h ON h.maquina_id = a.maquina_id AND h.unidad = a.unidad
  WHERE h.n >= 5
),

-- Caso 2: vs las otras maquinas de su modelo
promedio_maquina AS (
  SELECT maquina_id, modelo_id, unidad, AVG(valor) AS media
  FROM metrica
  WHERE modelo_id IS NOT NULL
  GROUP BY maquina_id, modelo_id, unidad
),

por_modelo AS (
  SELECT modelo_id, unidad, SUM(media) AS suma, COUNT(*) AS maquinas
  FROM promedio_maquina
  GROUP BY modelo_id, unidad
),

caso_modelo AS (
  SELECT
    p.maquina_id,
    p.unidad,
    p.media AS media_maquina,
    (m.suma - p.media) / (m.maquinas - 1) AS media_modelo,
    SAFE_DIVIDE(p.media - (m.suma - p.media) / (m.maquinas - 1),
                (m.suma - p.media) / (m.maquinas - 1)) * 100 AS pct_modelo,
    m.maquinas AS maquinas_modelo
  FROM promedio_maquina p
  JOIN por_modelo m ON m.modelo_id = p.modelo_id AND m.unidad = p.unidad
  WHERE m.maquinas >= @min_maquinas_modelo
),

-- Caso 3: tendencia de los ultimos dias
caso_tendencia AS (
  SELECT
    maquina_id,
    unidad,
    SAFE_DIVIDE(COVAR_SAMP(DATE_DIFF(dia, DATE '2000-01-01', DAY), valor),
                VAR_SAMP(DATE_DIFF(dia, DATE '2000-01-01', DAY))) AS pendiente,
    CORR(DATE_DIFF(dia, DATE '2000-01-01', DAY), valor) AS r,
    COUNT(*) AS n
  FROM metrica
  WHERE dia >= DATE_SUB(CURRENT_DATE('America/Lima'), INTERVAL @dias_tendencia DAY)
  GROUP BY maquina_id, unidad
  HAVING COUNT(*) >= 4
)

SELECT *
FROM (
  SELECT
    a.maquina_id,
    a.modelo_id,
    a.zona_id,
    a.unidad,
    ROUND(a.valor, 3) AS consumo_ayer,
    ROUND(p.media_propia, 3) AS media_propia,
    ROUND(p.z_propio, 2) AS z_propio,
    ROUND(p.pct_propio, 1) AS pct_propio,
    ROUND(m.media_modelo, 3) AS media_modelo,
    ROUND(m.pct_modelo, 1) AS pct_modelo,
    m.maquinas_modelo,
    ROUND(t.pendiente, 4) AS pendiente_diaria,
    ROUND(t.r, 2) AS r_tendencia,
    ARRAY_CONCAT(
      IF(p.z_propio >= @z OR p.pct_propio >= @pct_propio, ['propio'], []),
      IF(m.pct_modelo >= @pct_modelo, ['modelo'], []),
      IF(t.pendiente > 0 AND t.r >= @r_tendencia, ['tendencia'], [])
    ) AS casos
  FROM ayer a
  LEFT JOIN caso_propio p ON p.maquina_id = a.maquina_id AND p.unidad = a.unidad
  LEFT JOIN caso_modelo m ON m.maquina_id = a.maquina_id AND m.unidad = a.unidad
  LEFT JOIN caso_tendencia t ON t.maquina_id = a.maquina_id AND t.unidad = a.unidad
)
WHERE ARRAY_LENGTH(casos) > 0
ORDER BY ARRAY_LENGTH(casos) DESC, maquina_id