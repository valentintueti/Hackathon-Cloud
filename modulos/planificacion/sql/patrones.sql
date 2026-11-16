WITH lecturas AS (
  SELECT
    maquina_id,
    COALESCE(MAX(modelo_id) OVER (PARTITION BY maquina_id), 'sin_modelo') AS modelo,
    ts, temperatura, vibracion, presion, consumo_combustible, rpm, estado
  FROM `{dataset}.lectura_telemetria_unica`
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @dias DAY)
),

stats_modelo AS (
  SELECT
    modelo,
    AVG(temperatura) AS temperatura_media, STDDEV(temperatura) AS temperatura_desv,
    AVG(vibracion)   AS vibracion_media,   STDDEV(vibracion)   AS vibracion_desv,
    AVG(presion)     AS presion_media,     STDDEV(presion)     AS presion_desv,
    AVG(consumo_combustible) AS consumo_combustible_media, STDDEV(consumo_combustible) AS consumo_combustible_desv,
    AVG(rpm) AS rpm_media, STDDEV(rpm) AS rpm_desv
  FROM lecturas
  GROUP BY modelo
),

fallas_cargadas AS (
  SELECT maquina_id, ts
  FROM `{dataset}.falla`
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @dias DAY)
),

fallas_telemetria AS (
  SELECT maquina_id, ts
  FROM (
    SELECT maquina_id, ts, estado,
           LAG(estado) OVER (PARTITION BY maquina_id ORDER BY ts) AS estado_anterior
    FROM lecturas
  )
  WHERE estado = 'requiere_intervencion'
    AND COALESCE(estado_anterior, '') != 'requiere_intervencion'
),

fallas AS (
  SELECT * FROM fallas_cargadas
  UNION ALL
  SELECT * FROM fallas_telemetria
  WHERE (SELECT COUNT(*) FROM fallas_cargadas) = 0
),

ventanas_falla AS (
  SELECT
    CONCAT('F#', f.maquina_id, '#', FORMAT_TIMESTAMP('%Y%m%d%H%M%S', f.ts)) AS ventana_id,
    'falla' AS tipo,
    l.maquina_id,
    l.modelo,
    AVG(l.temperatura) AS temperatura,
    AVG(l.vibracion) AS vibracion,
    AVG(l.presion) AS presion,
    AVG(l.consumo_combustible) AS consumo_combustible,
    AVG(l.rpm) AS rpm
  FROM fallas f
  JOIN lecturas l
    ON l.maquina_id = f.maquina_id
   AND l.ts BETWEEN TIMESTAMP_SUB(f.ts, INTERVAL @horas_desde HOUR)
                AND TIMESTAMP_SUB(f.ts, INTERVAL @horas_hasta HOUR)
  GROUP BY ventana_id, l.maquina_id, l.modelo
),

ventanas_normales AS (
  SELECT
    CONCAT('N#', l.maquina_id, '#', CAST(DATE(l.ts) AS STRING)) AS ventana_id,
    'normal' AS tipo,
    l.maquina_id,
    l.modelo,
    AVG(l.temperatura) AS temperatura,
    AVG(l.vibracion) AS vibracion,
    AVG(l.presion) AS presion,
    AVG(l.consumo_combustible) AS consumo_combustible,
    AVG(l.rpm) AS rpm
  FROM lecturas l
  WHERE DATE(l.ts) <= DATE_SUB(CURRENT_DATE(), INTERVAL @dias_sin_falla DAY)
    AND NOT EXISTS (
      SELECT 1 FROM fallas f
      WHERE f.maquina_id = l.maquina_id
        AND DATE(f.ts) BETWEEN DATE(l.ts) AND DATE_ADD(DATE(l.ts), INTERVAL @dias_sin_falla DAY)
    )
  GROUP BY ventana_id, l.maquina_id, l.modelo
),

ventanas_actuales AS (
  SELECT
    CONCAT('A#', l.maquina_id) AS ventana_id,
    'actual' AS tipo,
    l.maquina_id,
    l.modelo,
    AVG(l.temperatura) AS temperatura,
    AVG(l.vibracion) AS vibracion,
    AVG(l.presion) AS presion,
    AVG(l.consumo_combustible) AS consumo_combustible,
    AVG(l.rpm) AS rpm
  FROM lecturas l
  WHERE l.ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @horas_recientes HOUR)
  GROUP BY ventana_id, l.maquina_id, l.modelo
),

ventanas AS (
  SELECT * FROM ventanas_falla
  UNION ALL SELECT * FROM ventanas_normales
  UNION ALL SELECT * FROM ventanas_actuales
),

niveles AS (
  SELECT
    v.ventana_id,
    v.tipo,
    v.maquina_id,
    CONCAT(x.variable, ' ', IF(x.z > 0, x.palabra_alto, x.palabra_bajo)) AS item
  FROM ventanas v
  JOIN stats_modelo s ON s.modelo = v.modelo,
  UNNEST([
    STRUCT('temperatura' AS variable, SAFE_DIVIDE(v.temperatura - s.temperatura_media, s.temperatura_desv) AS z, 'alta' AS palabra_alto, 'baja' AS palabra_bajo),
    STRUCT('vibracion' AS variable, SAFE_DIVIDE(v.vibracion - s.vibracion_media, s.vibracion_desv) AS z, 'alta' AS palabra_alto, 'baja' AS palabra_bajo),
    STRUCT('presion' AS variable, SAFE_DIVIDE(v.presion - s.presion_media, s.presion_desv) AS z, 'alta' AS palabra_alto, 'baja' AS palabra_bajo),
    STRUCT('consumo_combustible' AS variable, SAFE_DIVIDE(v.consumo_combustible - s.consumo_combustible_media, s.consumo_combustible_desv) AS z, 'alto' AS palabra_alto, 'bajo' AS palabra_bajo),
    STRUCT('rpm' AS variable, SAFE_DIVIDE(v.rpm - s.rpm_media, s.rpm_desv) AS z, 'alta' AS palabra_alto, 'baja' AS palabra_bajo)
  ]) AS x
  WHERE ABS(x.z) >= @z_nivel
),

combinaciones AS (
  SELECT a.ventana_id, a.tipo, CONCAT(a.item, ' + ', b.item) AS combinacion
  FROM niveles a
  JOIN niveles b ON b.ventana_id = a.ventana_id AND a.item < b.item
  WHERE a.tipo != 'actual'
  UNION ALL
  SELECT a.ventana_id, a.tipo, CONCAT(a.item, ' + ', b.item, ' + ', c.item) AS combinacion
  FROM niveles a
  JOIN niveles b ON b.ventana_id = a.ventana_id AND a.item < b.item
  JOIN niveles c ON c.ventana_id = a.ventana_id AND b.item < c.item
  WHERE a.tipo != 'actual'
),

totales AS (
  SELECT
    COUNTIF(tipo = 'falla') AS n_fallas,
    COUNTIF(tipo = 'normal') AS n_normales
  FROM (SELECT DISTINCT ventana_id, tipo FROM ventanas WHERE tipo != 'actual')
),

conteo AS (
  SELECT
    combinacion,
    COUNT(DISTINCT IF(tipo = 'falla', ventana_id, NULL)) AS soporte,
    COUNT(DISTINCT IF(tipo = 'normal', ventana_id, NULL)) AS en_normales
  FROM combinaciones
  GROUP BY combinacion
),

patrones_finales AS (
  SELECT
    c.combinacion,
    c.soporte,
    c.en_normales,
    ROUND(SAFE_DIVIDE(c.soporte, t.n_fallas)
          / SAFE_DIVIDE(c.en_normales + 1, t.n_normales + 1), 2) AS lift
  FROM conteo c
  CROSS JOIN totales t
  WHERE c.soporte >= @min_soporte
)

SELECT
  'patron' AS tipo,
  CAST(NULL AS STRING) AS maquina_id,
  SPLIT(combinacion, ' + ') AS items,
  combinacion,
  soporte,
  lift
FROM (
  SELECT * FROM patrones_finales
  WHERE lift >= @min_lift
  ORDER BY lift DESC, soporte DESC
  LIMIT 50
)

UNION ALL

SELECT
  'actual' AS tipo,
  maquina_id,
  ARRAY_AGG(item ORDER BY item) AS items,
  CAST(NULL AS STRING) AS combinacion,
  CAST(NULL AS INT64) AS soporte,
  CAST(NULL AS FLOAT64) AS lift
FROM niveles
WHERE tipo = 'actual'
GROUP BY maquina_id