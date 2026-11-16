# Datos simulados

Scripts para cargar datos de prueba **sin invocar Lambdas en masa**: escriben directo en S3 y DynamoDB con boto3 desde la EC2.

## Qué se genera

- 12 máquinas (4 camiones, 4 excavadoras, 4 cargadores) en 3 zonas, con 30 días de telemetría cada 30 minutos (~7 200 lecturas).
- 8 fallas históricas con su orden correctiva cerrada, su alerta y los repuestos usados:
  - 5 de motor (antes de fallar: temperatura y vibración altas)
  - 3 hidráulicas (antes de fallar: presión baja y consumo alto)
  - CAM-01 tiene una reincidencia.
- Casos preparados para cada módulo:
  - Preventivo: EXC-01 y CAR-02 cerca del 100 % de su intervalo.
  - Combustible: CAM-02 con consumo en subida los últimos 7 días, EXC-02 con un pico ayer y CAM-04 sobre su modelo.
  - Productividad: CAR-01 con jornadas de 14 h, CAR-03 con 3 h de uso al día y CAM-04 con poca carga y alto costo.
  - Planificación: EXC-03 muestra hoy el patrón que precedió a las fallas de motor.
  - Repuestos: catálogo de 10 componentes, stock por zona (algunos bajo el punto de reorden) y consumos de 30 días.
- 6 técnicos con especialidades y ubicación.

Los IDs son fijos: volver a ejecutar el script sobrescribe los mismos registros en lugar de duplicarlos.

## Pasos (en la EC2, desde la raíz del repo)

```bash
source ~/venv-layer/bin/activate && pip install boto3
```

```bash
python3 datos/generar_datos.py
```

```bash
python3 datos/ejecutar_procesos.py
```

`ejecutar_procesos.py` espera 2,5 minutos, exporta la telemetría a BigQuery con **una** invocación y después corre las Step Functions **una por una**, esperando a que termine cada una: líneas base, preventivo, combustible, productividad, planificación y repuestos.

## Demo en vivo (opcional)

```bash
python3 datos/enviar_en_vivo.py --intervalo 300
```

Envía una sola petición cada 5 minutos con las 12 máquinas, para que la flota se vea con señal. Opciones:

- `--anomalia EXC-04`: la primera lectura de esa máquina sale anómala (alerta, incidente, asignación y avisos).
- `--masivo Z-CENTRO`: 3 máquinas de la zona reciben lecturas anómalas, una cada 90 s, para provocar un evento masivo.
- `--ciclos 1`: envía un solo ciclo y termina.

## Reglas para no superar 10 Lambdas a la vez

- No ejecutes dos scripts al mismo tiempo.
- No bajes `--intervalo` de 60 s en el envío en vivo.
- No lances varias Step Functions juntas desde la consola: usa `ejecutar_procesos.py`.
- La ingesta del núcleo tiene `maximumConcurrency: 2` en la cola SQS.
