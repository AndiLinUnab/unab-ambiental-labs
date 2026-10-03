# UNAB-Ambiental — Laboratorio 4: AMQP + tercer protocolo

Comparación de AMQP 1.0 y HTTP/HTTPS como transportes alternativos a MQTT (Lab 3) hacia
la misma aplicación de Azure IoT Central.

**Integrantes:**
- Andi Lin – U00180153
- Juan Sebastián Buitrago Caballero – U00179631
- Miguel Ángel Solano Díaz – U00177983

Ninguna credencial real está incluida en este repositorio. Todos los scripts leen
ID Scope / Device ID / Primary Key desde variables de entorno.

## Los dos clientes nuevos

| Carpeta | Protocolo | Puerto | Librería |
|---|---|---|---|
| `amqp-client/` | AMQP 1.0 sobre TLS | 5671 | `python-qpid-proton` |
| `http-client/` | HTTP/HTTPS | 443 | `requests` |

## Por qué `python-qpid-proton` y no `uamqp`

El SDK `azure-iot-device` de Python **no soporta AMQP** como transporte de dispositivo
(solo MQTT). La documentación oficial de Microsoft muestra el patrón con la librería
`uamqp`, pero ese repositorio está **archivado y deprecado**, y falla al compilar en
Python 3.12+ por depender de APIs internas de CPython que ya cambiaron. Se usó en su
lugar `python-qpid-proton` (Apache Qpid Proton), la alternativa activamente mantenida
que el propio enunciado habilita explícitamente ("uamqp / proton, o equivalente vigente").

### Instalación correcta (evita el error de SSL)

Instalar `python-qpid-proton` con `pip` normalmente compila la extensión en C **sin
soporte TLS** si el sistema no tiene las librerías de desarrollo de OpenSSL al momento de
compilar, lo que produce el error `proton._exceptions.SSLException: SSL failure.` al
intentar conectar. La solución robusta es usar el paquete ya compilado por Ubuntu:

```bash
sudo apt update
sudo apt install -y python3-qpid-proton python3-requests

# Recrear el entorno virtual con acceso a los paquetes del sistema:
python3 -m venv venv --system-site-packages
source venv/bin/activate

# Verificar que SÍ tiene soporte SSL:
python3 -c "from proton import SSL; print('SSL disponible:', SSL.present())"
# Debe imprimir: SSL disponible: True
```

## El bug de codificación AMQP (y por qué importa)

Por defecto, `python-qpid-proton` codifica el cuerpo del mensaje (`Message(body=...)`)
como una sección **AMQP-VALUE**, sin importar si el valor es `str` o `bytes`. Azure IoT
Hub **no interpreta esa sección como payload de telemetría JSON**: el dispositivo
aparece `Connected` en IoT Central, pero sin ningún dato llegando (`Last data received:
N/A`, "No data found" en las gráficas).

La solución es forzar una sección **AMQP-DATA** (binaria), equivalente al payload crudo
que MQTT transmite por diseño:

```python
message = Message(body=payload.encode("utf-8"), content_type="application/json;charset=utf-8")
message.inferred = True  # fuerza sección Data en vez de AMQP-VALUE
```

Esto no es un detalle menor: ilustra justamente una de las diferencias reales entre AMQP
y MQTT que pide comparar el laboratorio — AMQP, al ser un protocolo con tipos de datos
más ricos, exige decisiones explícitas de tipificación del payload que MQTT, con su único
tipo de payload (bytes opacos), no exige nunca.

## Cómo correr cada cliente

### AMQP
```bash
cd amqp-client
export ID_SCOPE="..."
export DEVICE_ID="Python-AMQP"      # dispositivo NUEVO
export PRIMARY_KEY="..."
python3 amqp_client.py
```

### HTTP
```bash
cd http-client
export ID_SCOPE="..."
export DEVICE_ID="Python-HTTP"      # otro dispositivo NUEVO
export PRIMARY_KEY="..."
python3 http_client.py
```

> Cada cliente usa un dispositivo distinto (igual que en el Lab 3), para poder correr
> los tres protocolos (MQTT, AMQP, HTTP) simultáneamente sin que compitan por la misma
> sesión de IoT Hub.

## Hallazgo: HTTP aparece "Disconnected" aunque funcione

Con el cliente HTTP, IoT Central muestra el dispositivo como **Disconnected** incluso
mientras los datos llegan correctamente y las gráficas se pueblan en tiempo real. No es
un error: HTTP no mantiene una conexión persistente (cada mensaje es un POST
independiente), así que IoT Central no tiene forma de inferir que el dispositivo sigue
"en línea" entre una petición y la siguiente, a diferencia de MQTT/AMQP donde el socket
persistente permite un estado de conexión confiable.

## Mediciones obtenidas (resumen — detalle completo en el informe)

| Protocolo | Latencia medida |
|---|---|
| MQTT (Lab 3, QoS 1) | ~185-200 ms |
| AMQP | ~238-262 ms |
| HTTP | ~778-888 ms |

La latencia escala con la "pesadez" del protocolo: MQTT (pub/sub ligero) < AMQP
(sesiones y enlaces) < HTTP (handshake TLS completo en cada mensaje).

## Recomendaciones de capa

- **Dispositivo (Wokwi/ESP32 futuro):** MQTT — el más liviano para RAM limitada.
- **Entre servicios Azure / plataforma propia:** AMQP — garantías de entrega más ricas
  para Service Bus/Event Hubs.
- **Protocolos descartados para el resto del curso:** HTTP, por su latencia ~4x mayor y
  la pérdida del estado de conexión en tiempo real.

## Estructura del repositorio

```
.
├── README.md
├── amqp-client/
│   └── amqp_client.py
├── http-client/
│   └── http_client.py
└── evidencias/
    ├── e1_amqp_connected.png   # Python-AMQP: Connected, 3 variables llegando
    ├── e1_amqp_terminal.png    # Terminal: mensajes AMQP entregados (~238-262 ms)
    ├── e2_http_disconnected.png # Python-HTTP: Disconnected pero con datos llegando
    └── e2_http_terminal.png    # Terminal: mensajes HTTP entregados (~778-888 ms)
```
