# UNAB-Ambiental — Laboratorio 5: plataforma propia (MQTT → InfluxDB → Grafana)

Inicio de la plataforma propia: se reemplaza Azure IoT Central por un stack que corre en una
VM con Docker Compose y que guarda y visualiza la telemetría de las 3 variables del escenario
(`temperature`, `humidity`, `illuminance`). Incluye la toma de 4 días, el dashboard de Grafana
y una alerta de umbral disparada y evidenciada.

**Integrantes:**
- Andi Lin – U00180153
- Juan Sebastián Buitrago Caballero – U00179631
- Miguel Ángel Solano Díaz – U00177983

Ningún archivo de este repositorio contiene credenciales. Las contraseñas y el token salen de un
archivo `.env` local que **no se sube** (ver `.env.example`). En las capturas de webhook.site se
tacharon la IP pública de la VM, la URL del webhook y su token.

> **Los datos son sintéticos.** El publicador genera valores con un ciclo día/noche más ruido,
> dentro de los rangos del escenario. No provienen de un sensor físico.

## Arquitectura

```
 publicador (Python)  ──MQTT──▶  Mosquitto  ──MQTT──▶  Telegraf  ──HTTP──▶  InfluxDB 2  ◀──Flux──  Grafana
 3 variables / 30 s             (broker)               (puente)              (TSDB)                 (dashboard + alerta)
```

| Pieza | Imagen | Rol |
|---|---|---|
| `publisher` | `python:3.12-slim` (build local) | Publica las 3 variables por MQTT cada 30 s. |
| `mosquitto` | `eclipse-mosquitto:2` | Broker MQTT. Solo accesible desde la red interna de Docker. |
| `telegraf` | `telegraf:1.32` | Se suscribe al broker (QoS 1, sesión persistente) y escribe en InfluxDB. |
| `influxdb` | `influxdb:2.7` | TSDB con el historial de la toma. |
| `grafana` | `grafana/grafana-oss:11.2.0` | Visualización y alertas. **Solo lee la TSDB**, no participa en la ingesta. |

> **Versión de InfluxDB fijada a propósito:** desde abril de 2026 el tag `latest` de la imagen de
> InfluxDB apunta a InfluxDB 3 Core, que es otro producto con otra API. Este stack usa la serie
> 2.x (Flux).

### Protocolo elegido: MQTT
Es el protocolo de menor latencia de los tres medidos en los Labs 3 y 4 (≈185–200 ms con QoS 1,
frente a ≈238–262 ms de AMQP y ≈778–888 ms de HTTP) y el más liviano para el microcontrolador al
que migrará la plataforma. El broker propio (Mosquitto) reemplaza al IoT Hub como punto de
entrada de los datos.

### Modelo de datos
- **Topic de telemetría:** `unab/ambiental/<sala>/telemetria`
- **Payload:** `{"temperature": 24.1, "humidity": 52.3, "illuminance": 430.2, "ts": 1760000000000}`
- **En InfluxDB:** measurement `ambiental`, tag `sala`, campos `temperature`, `humidity`,
  `illuminance` (float). La marca de tiempo es la del dato (`ts`, generada por el publicador).
- **Topic de control:** `unab/ambiental/<sala>/control` (ver "Forzar una alerta").

## Resultado de la toma de datos

**Criterio:** un día de toma es una ventana continua de **al menos 24 h**, medida desde el primer
dato guardado (no un día de calendario). Los días no son seguidos: entre bloques la VM se detuvo
(deallocate) desde el portal de Azure. Horas de Colombia (UTC-5).

| Bloque | Inicio | Fin | Duración | Puntos | Días de 24 h |
|---|---|---|---|---|---|
| 1 | 10 oct 12:38:26 | 12 oct 13:13:56 | 48 h 35 min | 5832 | 2 seguidos |
| 2 | 14 oct 14:05:45 | 15 oct 15:08:45 | 25 h 03 min | 3007 | 1 |
| 3 | 17 oct 12:00:38 | 18 oct 12:21:08 (*) | 24 h 20 min | 2922 | 1 |
| **Total** | | | **98 h 00 min** | **11 761** | **4** |

(*) Corte de análisis: la última consulta guardada (`evidencias/texto/consulta_final_toma.txt`). Si
la VM siguió encendida después, esos puntos no se cuentan. Puntos esperados de un bloque =
duración ÷ 30 s + 1; **los tres bloques coinciden exactamente**, es decir, no se perdió ninguna
muestra.

**Huecos** (consulta `queries/huecos.flux`, pausas de más de 2 minutos):

| Hueco | Duración | Qué es |
|---|---|---|
| 9 oct 20:12 → 10 oct 12:38 | 16 h 25 min | Entre la prueba de la Sesión 1 y el bloque 1 (anterior a la toma) |
| 12 oct 13:13 → 14 oct 14:05 | 48 h 52 min | Pausa entre los bloques 1 y 2 |
| 15 oct 15:08 → 16 oct 09:06 | 17 h 58 min | Pausa entre los bloques 2 y 3, antes del arranque breve |
| 16 oct 09:12 → 17 oct 12:00 | 26 h 48 min | Pausa entre los bloques 2 y 3, después del arranque breve |

Dentro de cada bloque no hay ningún hueco. Además de los tres bloques, la TSDB guarda:
- **15 puntos de la prueba de la Sesión 1** (9 oct 20:05:59 a 20:12:59), anteriores a la toma.
- **12 puntos de un arranque breve** el 16 oct (09:06:49 a 09:12:19): se encendió la VM para
  mostrar el avance al profesor. No cuenta como día de toma.

Total guardado en la TSDB al corte: 11 788 puntos (11 761 + 15 + 12).

### Consultas guardadas (`evidencias/texto/`)

| Archivo | Último dato (UTC-5) | Contenido |
|---|---|---|
| `consulta_bloque1_dia1.txt` | 11 oct 16:19:56 | Día 1 ya cumplido y día 2 en curso: 1364 + 1960 puntos hasta ese momento |
| `consulta_bloque1_final.txt` | 12 oct 13:13:26 | 1364 + 2880 + 1587 = 5831 puntos. El último punto del bloque 1 llegó 30 s después (13:13:56): la consulta final da 1588 el 12 oct y 5832 en total |
| `consulta_final_toma.txt` | 18 oct 12:21:08 | Toma completa: los tres bloques, los cuatro huecos y 11 788 puntos |
| `arranque_automatico_bloque2.txt`, `..._bloque3.txt` | 14 oct 14:05 / 17 oct 12:00 | Hora de arranque de la VM y de cada contenedor (UTC) |
| `forzado_publicador.txt` | 11 oct 11:00–11:10 | Log del publicador con el forzado de 38 °C |

Las capturas de pantalla de `consulta.sh` de cada bloque están en `evidencias/04_consultas/`.

### Arranque automático al encender la VM

Todos los servicios usan `restart: always` y Docker arranca con el sistema, así que al encender la
VM el stack sube solo. **Verificado en los bloques 2 y 3:** la VM arrancó y los cinco contenedores
lo hicieron 16 s después, con menos de 0,5 s de diferencia entre sí; el primer dato llegó a los
21 y 22 s (`evidencias/05_arranque_automatico/`). **En el bloque 1 no se guardó esa comprobación:**
el primer dato llegó unos 10 minutos después de encender la VM y no se puede confirmar si el
arranque fue automático.

## Requisitos

VM Ubuntu Server 24.04 con salida a Internet (para descargar las imágenes) y Docker:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # cerrar y volver a abrir la sesión SSH después
docker compose version             # debe responder una versión 2.x
systemctl is-enabled docker        # debe decir "enabled" (arranca solo con la VM)
```

No hace falta abrir ningún puerto de entrada en Azure: Grafana (3000) e InfluxDB (8086) solo
escuchan en el loopback de la VM y se consultan por túnel SSH.

## Puesta en marcha

1. **Copiar el proyecto a la VM** (desde tu PC, con `scp`; no pegar código en `nano`, que corrompe
   los archivos). La llave va con `-i`, no como un archivo más a copiar:
   ```powershell
   scp -i C:\ruta\llave.pem -r .\UNAB-Ambiental_lab5 azureuser@IP_PUBLICA:~/
   ```
2. **Corregir permisos y crear el `.env`** en la VM:
   ```bash
   cd ~/UNAB-Ambiental_lab5
   chmod +x scripts/*.sh
   ./scripts/preparar_permisos.sh
   cp .env.example .env
   openssl rand -hex 32               # copiar el resultado como INFLUX_TOKEN
   nano .env                          # rellenar contraseñas y token (sin espacios ni comillas)
   ```
   El paso de permisos es necesario: el `scp` desde Windows deja las carpetas con `drwx------` y
   Grafana no puede leer su aprovisionamiento (ver "Incidencias").
3. **Levantar el stack:**
   ```bash
   docker compose up -d --build
   docker compose ps             # los 5 servicios deben estar "running" (influxdb: healthy)
   ```
4. **Verificar la cadena completa:**
   ```bash
   docker compose logs --tail 5 publisher          # líneas "publish rc=0 {...}"
   docker compose exec mosquitto mosquitto_sub -t 'unab/ambiental/#' -C 3 -v
   docker compose logs --tail 20 telegraf          # sin errores de escritura
   ./scripts/consulta.sh                           # puntos guardados en InfluxDB
   ```

> **Atención:** InfluxDB solo toma el usuario, la contraseña y el token del `.env` en el
> **primer** arranque (cuando el volumen está vacío). Si los cambias después, no se aplican. Para
> empezar de cero hay que borrar los volúmenes con `docker compose down -v`, lo que **elimina
> todos los datos guardados**. No usar `-v` durante la toma.

## Acceso a Grafana e InfluxDB (túnel SSH)

Desde tu PC:
```powershell
ssh -i C:\ruta\llave.pem -L 3000:localhost:3000 -L 8086:localhost:8086 azureuser@IP_PUBLICA
```
- Grafana: <http://localhost:3000> — usuario `admin`, contraseña `GRAFANA_ADMIN_PASSWORD`.
- InfluxDB: <http://localhost:8086> — usuario/contraseña del `.env`.

La IP pública de la VM puede cambiar cada vez que se detiene y se vuelve a encender.

## Dashboard de Grafana

`grafana/dashboards/monitoreo-aula.json` es el dashboard **UNAB-Ambiental — Monitoreo de aula**,
exportado con la opción *Export for sharing externally*. Tiene 6 paneles: una serie temporal por
variable (con la línea de 30 °C en temperatura) y un gauge por variable con unidad y rango del
escenario (16–32 °C, 35–70 %, 100–800 lux). Los paneles de serie cortan la línea cuando pasan más
de 10 minutos sin datos, por eso las pausas entre bloques se ven como huecos y no como una línea
falsa.

**Cómo importarlo** (no se aprovisiona solo): Dashboards → New → Import → subir el JSON → elegir
el datasource `InfluxDB-Ambiental` → Import.

**Datasource.** Se aprovisiona desde `grafana/provisioning/datasources/influxdb.yml`, con el
lenguaje Flux y las variables `INFLUX_*` del `.env`. En la VM del laboratorio ese
aprovisionamiento no cargó la primera vez (permisos) y el datasource se creó a mano: nombre
`InfluxDB-Ambiental`, **Query language = Flux** (el formulario viene en InfluxQL), URL
`http://influxdb:8086`, y organización, bucket y token del `.env`.

## Alerta de umbral

La regla se creó a mano en Grafana (no se aprovisiona):

| Campo | Valor |
|---|---|
| Nombre / carpeta / grupo | `Temperatura alta en aula` / `UNAB-Ambiental` / `temperatura` (evaluación cada 1 m) |
| Consulta A | Flux sobre `temperature`, promedio por minuto, rango de los últimos 10 min (abajo) |
| Expresiones | B = Reduce (Last, sobre A) · C = Threshold (B **is above 30**, condición de la alerta) |
| Pending period | 2 m (la condición debe sostenerse 2 minutos) |
| Si no hay datos | Normal |
| Contact point | `webhook-prueba`, tipo Webhook (POST) hacia webhook.site |
| Resumen | Temperatura sobre 30 °C durante 2 minutos |

Consulta A:
```flux
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "ambiental" and r._field == "temperature")
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
  |> yield(name: "temperature")
```

La acción es un webhook de prueba (webhook.site) porque un correo exigiría configurar SMTP en
Grafana. La URL de webhook.site es temporal y no se incluye en el repositorio.

**Disparo evidenciado (11 oct, hora de Colombia):**

| Hora | Evento | Fuente |
|---|---|---|
| 11:00:53 | Empieza el forzado de 38 °C durante 600 s | log del publicador |
| 11:01:10 | La regla pasa a Pending | state history |
| 11:03:10 | La regla pasa a Firing (2 min después, por el pending period) | state history |
| 11:03:40 | Llega la notificación `firing` | webhook.site |
| 11:10:56 | Fin del forzado | log del publicador |
| 11:12:10 | La regla vuelve a Normal | state history |
| 11:13:40 | Llega la notificación `resolved` | webhook.site |

Evidencias en `evidencias/03_alerta/`. El forzado cae dentro del bloque 1 y se ve como un pico de
38 °C en el dashboard. El valor `B=32` de la fase Pending es el promedio de un minuto que mezcló una
muestra normal (~26 °C) con una forzada (38 °C).

### Forzar una alerta

El publicador escucha el topic de control y reemplaza los valores indicados durante N segundos:

```bash
./scripts/forzar_alerta.sh            # temperature = 38 °C durante 300 s
./scripts/forzar_alerta.sh 38 600     # temperature = 38 °C durante 600 s (el usado en el laboratorio)
```

Sin forzar, la temperatura sintética no supera ~29 °C (comprobado simulando 4 días antes de
arrancar), así que la alerta solo se dispara cuando se fuerza.

## Operar la VM entre bloques

Entre bloques la VM se **detiene desde el portal de Azure** (*Stopped (deallocated)*), lo que
evita gastar crédito. Al encenderla, los contenedores arrancan solos y los datos siguen intactos en
los volúmenes.

1. Portal de Azure → VM → **Start**. Revisar la IP pública nueva en *Overview*.
2. Por SSH: `cd ~/UNAB-Ambiental_lab5 && docker compose ps` y `./scripts/consulta.sh`.
3. Medir las 24 h desde el **primer dato guardado** (no desde el Start). `huecos` lo muestra: el
   `_time` de la fila nueva es el primer punto del bloque.
4. Pasadas las 24 h, guardar la evidencia y detener la VM. No usar `docker compose down -v`.

`./scripts/consulta.sh` imprime los últimos puntos, el inicio y fin reales de la toma, los puntos
por día y los huecos.

## Estructura del repositorio

```
.
├── README.md
├── docker-compose.yml
├── .env.example
├── mosquitto/mosquitto.conf
├── telegraf/telegraf.conf
├── grafana/
│   ├── provisioning/datasources/influxdb.yml
│   ├── provisioning/{dashboards,plugins,alerting}/   (vacías, silencian advertencias de Grafana)
│   └── dashboards/monitoreo-aula.json                (para importar a mano)
├── publisher/            (Dockerfile, requirements.txt, publisher.py)
├── queries/              (consultas Flux que usa scripts/consulta.sh)
├── scripts/              (consulta.sh, forzar_alerta.sh, preparar_permisos.sh)
└── evidencias/
    ├── 01_sesion1/              docker compose ps y primera consulta a la TSDB
    ├── 02_dashboard/            toma completa (10–18 oct), un dashboard por bloque y el pico forzado
    ├── 03_alerta/               regla, estado Firing, historial de estados, webhooks y log del forzado
    ├── 04_consultas/            salidas de consulta.sh de cada bloque
    ├── 05_arranque_automatico/  arranque de la VM y de los contenedores (bloques 2 y 3)
    ├── 06_incidencias/          error de permisos de Grafana y su corrección
    └── texto/                   consultas y logs guardados como texto
```

## Decisiones de diseño y seguridad

- **Mosquitto sin autenticación, pero no expuesto:** el puerto 1883 no se publica fuera de la red
  de Docker, por lo que solo el publicador y Telegraf llegan al broker. Si el broker se expone algún
  día, hay que activar `password_file` y TLS antes.
- **Grafana e InfluxDB solo en loopback** (`127.0.0.1`), accesibles por túnel SSH; no se abre
  ningún puerto de entrada en el NSG de Azure.
- **Marca de tiempo del dato:** la genera el publicador (`ts`) y Telegraf la respeta, de modo que
  un reinicio de Telegraf no apila puntos en la misma hora.
- **Telegraf con QoS 1 y sesión persistente:** si Telegraf se reinicia, el broker retiene los
  mensajes y se entregan al volver.
- **Publicador resistente:** reconexión automática al broker, sin que un mensaje de control
  inválido o un fallo puntual de publicación lo detenga; además `restart: always`.
- **Imágenes con versión fijada** para que el stack sea reproducible.

## Incidencias de instalación en la VM

| Qué falló | Causa | Cómo se resolvió | Evidencia |
|---|---|---|---|
| `scp` respondió `Permission denied (publickey)` | La llave `.pem` se escribió como un archivo más a copiar y no con la opción `-i` | Se usó `scp -i llave.pem -r ...` | — |
| El datasource aprovisionado no cargó | El `scp` desde Windows dejó `grafana/` con permisos `drwx------`; Grafana corre con otro usuario dentro del contenedor y no podía leerla (`permission denied` en su log) | Se creó el datasource a mano (eligiendo Flux, no InfluxQL). Después `chmod -R a+rX grafana` y `docker compose restart grafana`: el error de permisos desapareció del log | `evidencias/06_incidencias/` |

Sin incidencias en el resto: `docker compose up` levantó a la primera, Telegraf escribió en
InfluxDB con la hora del publicador desde el primer punto, y en los bloques 2 y 3 el stack arrancó
solo al encender la VM.

Tras la corrección quedan en el log de Grafana tres advertencias `no such file or directory`
(dashboards, plugins, alerting) porque no existían esas carpetas de aprovisionamiento; son
inofensivas y las carpetas vacías de este repositorio las evitan.

## Si algo falla

| Síntoma | Qué mirar |
|---|---|
| `scripts/*.sh: Permission denied` | `chmod +x scripts/*.sh` (Windows no conserva el permiso de ejecución). |
| `$'\r': command not found` | El script se guardó con finales de línea de Windows: `sed -i 's/\r$//' scripts/*.sh`. |
| `docker compose up` falla con `Falta INFLUX_...` | Falta una variable en `.env` o el archivo no se llama exactamente `.env`. |
| Telegraf sin datos o con errores de parseo | `docker compose logs telegraf`. Si el error es de `timestamp`, comentar las dos líneas `timestamp_*` de `telegraf.conf` y `docker compose restart telegraf`. |
| Grafana sin datasource | `docker compose logs grafana`: si dice `permission denied`, ejecutar `./scripts/preparar_permisos.sh` y `docker compose restart grafana`. |
| El `.env` cambió pero InfluxDB sigue con los valores viejos | Solo se aplica en el primer arranque; ver la advertencia de arriba. |

## Limitaciones y lo que no se verificó

- **Datos sintéticos:** no hay un sensor físico detrás de las series.
- **Aprovisionamiento del datasource en una instalación limpia:** tras corregir los permisos, el
  error desapareció del log, pero no se repitió una instalación desde cero para confirmar que el
  datasource aprovisionado carga solo.
- **Dashboard y alerta no se aprovisionan:** el dashboard se importa a mano y la regla se recrea
  con la tabla de arriba.
- **Arranque automático del bloque 1:** no se guardó la comprobación (ver más arriba).
- **Webhook de prueba:** webhook.site es un destino temporal; no se configuró correo (SMTP).
- **Mosquitto sin autenticación:** aceptable solo porque el puerto no se publica.
