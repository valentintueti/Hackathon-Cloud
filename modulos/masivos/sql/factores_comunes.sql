WITH lecturas AS (
  SELECT maquina_id, ts, temperatura, vibracion, presion, consumo_combustible, rpm
  FROM `{dataset}.lectura_telemetria_unica`
  WHERE maquina_id IN UNNEST(SPLIT(@maquinas, ','))
    AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @dias DAY)
),

historia AS (
  SELECT
    maquina_id,
    AVG(temperatura) AS temperatura_media, STDDEV(temperatura) AS temperatura_desv,
    AVG(vibracion)   AS vibracion_media,   STDDEV(vibracion)   AS vibracion_desv,
    AVG(presion)     AS presion_media,     STDDEV(presion)     AS presion_desv,
    AVG(consumo_combustible) AS consumo_combustible_media, STDDEV(consumo_combustible) AS consumo_combustible_desv,
    AVG(rpm)         AS rpm_media,         STDDEV(rpm)         AS rpm_desv
  FROM lecturas
  WHERE ts < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @minutos MINUTE)
  GROUP BY maquina_id
),

recientes AS (
  SELECT *
  FROM lecturas
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @minutos MINUTE)
),

valores AS (
  SELECT r.maquina_id, r.ts, v.variable, v.valor, v.media, v.desv
  FROM recientes r
  JOIN historia h ON h.maquina_id = r.maquina_id,
  UNNEST([
    STRUCT('temperatura' AS variable, r.temperatura AS valor, h.temperatura_media AS media, h.temperatura_desv AS desv),
    STRUCT('vibracion' AS variable, r.vibracion AS valor, h.vibracion_media AS media, h.vibracion_desv AS desv),
    STRUCT('presion' AS variable, r.presion AS valor, h.presion_media AS media, h.presion_desv AS desv),
    STRUCT('consumo_combustible' AS variable, r.consumo_combustible AS valor, h.consumo_combustible_media AS media, h.consumo_combustible_desv AS desv),
    STRUCT('rpm' AS variable, r.rpm AS valor, h.rpm_media AS media, h.rpm_desv AS desv)
  ]) AS v
),

desvios AS (
  SELECT maquina_id, ts, variable, (valor - media) / desv AS z
  FROM valores
  WHERE valor IS NOT NULL
    AND desv > 0
    AND ABS((valor - media) / desv) >= @z
)

SELECT
  maquina_id,
  variable,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%S', MIN(ts), 'America/Lima') AS inicio,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%S', MAX(ts), 'America/Lima') AS fin,
  COUNT(*) AS lecturas,
  AVG(z) AS direccion
FROM desvios
GROUP BY maquina_id, variable
ORDER BY variable, inicio