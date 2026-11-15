CREATE OR REPLACE TABLE `{dataset}.linea_base` AS
WITH datos AS (
  SELECT maquina_id, modelo_id, temperatura, vibracion, presion, consumo_combustible, rpm
  FROM `{dataset}.lectura_telemetria_unica`
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @dias DAY)
    AND COALESCE(estado, '') != 'detenida'
    AND (rpm IS NULL OR rpm > 0)
),
por_maquina AS (
  SELECT
    'maquina' AS ambito, maquina_id AS id, COUNT(*) AS n,
    AVG(temperatura) AS temperatura_media,                 STDDEV(temperatura) AS temperatura_desv,
    AVG(vibracion) AS vibracion_media,                     STDDEV(vibracion) AS vibracion_desv,
    AVG(presion) AS presion_media,                         STDDEV(presion) AS presion_desv,
    AVG(consumo_combustible) AS consumo_combustible_media, STDDEV(consumo_combustible) AS consumo_combustible_desv,
    AVG(rpm) AS rpm_media,                                 STDDEV(rpm) AS rpm_desv
  FROM datos
  GROUP BY maquina_id
),
por_modelo AS (
  SELECT
    'modelo' AS ambito, modelo_id AS id, COUNT(*) AS n,
    AVG(temperatura), STDDEV(temperatura),
    AVG(vibracion), STDDEV(vibracion),
    AVG(presion), STDDEV(presion),
    AVG(consumo_combustible), STDDEV(consumo_combustible),
    AVG(rpm), STDDEV(rpm)
  FROM datos
  WHERE modelo_id IS NOT NULL
  GROUP BY modelo_id
)
SELECT *, CURRENT_TIMESTAMP() AS calculado_en FROM por_maquina
UNION ALL
SELECT *, CURRENT_TIMESTAMP() AS calculado_en FROM por_modelo;