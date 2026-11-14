CREATE TABLE IF NOT EXISTS `arquifusion-hackathon.arquifusion.lectura_telemetria` (
  maquina_id            STRING    NOT NULL,
  ts                    TIMESTAMP NOT NULL,
  modelo_id             STRING,
  zona_id               STRING,
  lat                   FLOAT64,
  lon                   FLOAT64,
  horas_funcionamiento  FLOAT64,
  temperatura           FLOAT64,
  vibracion             FLOAT64,
  presion               FLOAT64,
  consumo_combustible   FLOAT64,
  carga_transportada    FLOAT64,
  velocidad             FLOAT64,
  rpm                   FLOAT64,
  estado                STRING
)
PARTITION BY DATE(ts)
CLUSTER BY maquina_id;


CREATE OR REPLACE VIEW `arquifusion-hackathon.arquifusion.lectura_telemetria_unica` AS
SELECT * EXCEPT (fila)
FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY maquina_id, ts) AS fila
  FROM `arquifusion-hackathon.arquifusion.lectura_telemetria`
)
WHERE fila = 1;