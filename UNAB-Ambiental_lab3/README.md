# UNAB-Ambiental — Laboratorio 3: MQTT hacia Azure IoT Central

Comparación de tres formas de publicar telemetría hacia la misma aplicación de Azure IoT
Central: el SDK oficial (`azure-iot-device`), un cliente MQTT explícito (`paho-mqtt`) y el
firmware ESP32 en Wokwi, ambos hablando directamente MQTT/TLS sin que el SDK esconda nada.

**Integrantes:**
- Andi Lin – U00180153
- Juan Sebastián Buitrago Caballero – U00179631
- Miguel Ángel Solano Díaz – U00177983

Ninguna credencial real está incluida en este repositorio. Todos los scripts leen
ID Scope / Device ID / Primary Key desde variables de entorno.

## Los tres caminos

| Carpeta | Camino | Qué esconde / qué expone |
|---|---|---|
| `sdk-python/` | SDK `azure-iot-device` (reutilizado del Lab 2) | Esconde topics, SAS y reconexión — es el "baseline" |
| `mqtt-explicito/` | Cliente MQTT explícito con `paho-mqtt` | Expone SAS, topic, QoS; sin reconexión automática |
| `wokwi/` | Firmware Arduino/ESP32 (mismo proyecto del Lab 2) | Igual que MQTT explícito, pero en C++ con `mbedtls` |

## Cómo se genera el token SAS a mano

Tanto `mqtt-explicito/mqtt_explicito.py` como `wokwi/sketch.ino` implementan el mismo
algoritmo, sin usar el SDK de Azure. El proceso es:

1. **Construir el string a firmar**: `urlEncode(resourceUri) + "\n" + expiry`, donde
   `resourceUri` es `{hub}/devices/{deviceId}` (para el hub) o
   `{idScope}/registrations/{deviceId}` (para DPS), y `expiry` es un timestamp Unix futuro.
2. **Firmar con HMAC-SHA256** usando la Primary Key del dispositivo (decodificada de
   Base64) como clave secreta.
3. **Codificar la firma en Base64** y armar el token final:
   ```
   SharedAccessSignature sr=<resourceUri>&sig=<firma>&se=<expiry>[&skn=registration]
   ```
   El parámetro `skn=registration` solo aplica al token usado contra DPS, no contra el hub.
4. Ese token se usa como **password** en la conexión MQTT (el username es
   `{hub}/{deviceId}/?api-version=2021-04-12`), o como header `Authorization` en las
   peticiones HTTPS contra DPS.

En Python esto se hace con `hmac`, `hashlib` y `base64` de la librería estándar (ver
`generate_sas_token()` en `mqtt_explicito.py`). En el ESP32 se usa `mbedtls_md_hmac_*` y
`mbedtls_base64_encode/decode`, que ya vienen incluidos en el core de Arduino para ESP32
(ver `generateSasToken()` en `sketch.ino`).

**Nunca** se guarda la Primary Key ni el token generado en un archivo de este repo — se
leen siempre de variables de entorno (Python) o se reemplazan por un placeholder antes de
hacer commit (Arduino, ver `wokwi/sketch.ino`).

## Cómo correr cada camino

### SDK Python (baseline, ya documentado en el Lab 2)
```bash
cd sdk-python
export ID_SCOPE="..."
export DEVICE_ID="Python-VM"
export PRIMARY_KEY="..."
python3 sensor_ambiental.py
```

### MQTT explícito
```bash
cd mqtt-explicito
pip install paho-mqtt requests
export ID_SCOPE="..."
export DEVICE_ID="Python-MQTT-Explicito"   # dispositivo NUEVO y distinto al de arriba
export PRIMARY_KEY="..."
python3 mqtt_explicito.py
```
> Se usa un dispositivo distinto al del SDK porque IoT Hub solo permite una sesión activa
> por dispositivo; con credenciales separadas se pueden correr ambos caminos al mismo
> tiempo para comparar en vivo.

### Wokwi
1. Crear un proyecto ESP32 en [wokwi.com](https://wokwi.com), pegar `sketch.ino`.
2. Instalar las librerías de `libraries.txt` desde el Library Manager de Wokwi.
3. Reemplazar `ID_SCOPE`, `DEVICE_ID` y `PRIMARY_KEY` con las credenciales de un tercer
   dispositivo.
4. Dar Play (▶) y revisar la consola serial.

## Mediciones obtenidas (resumen — detalle completo en el informe)

| Métrica | Resultado |
|---|---|
| Payload | 110 bytes constantes (JSON de 3 variables + timestamp) |
| QoS 0 | ACK ~1 ms (fire-and-forget) |
| QoS 1 | ACK ~185-200 ms (espera PUBACK real) |
| QoS 2 | ACK ~184-330 ms, sin cierre de conexión — comportamiento no estrictamente documentado (ver informe para el análisis completo) |
| Corte de red (MQTT explícito) | No se recupera solo: `RuntimeError` al perder la conexión, el programa termina |
| Corte de red (SDK) | Reconexión automática e implícita, nunca falló en el Lab 2 |

## Decisiones de modelado y limitaciones

- Se usó un **dispositivo nuevo** (`Python-MQTT-Explicito`) en vez de reutilizar
  `Python-VM`, para evitar que dos clientes con las mismas credenciales se desconecten
  mutuamente al intentar mantener sesiones simultáneas contra el mismo IoT Hub.
- El cliente MQTT explícito **no implementa reconexión automática** deliberadamente, para
  poder documentar honestamente la diferencia de resiliencia frente al SDK (ver Etapa 3 del
  informe). En un despliegue real, esto se resolvería envolviendo `publish()` en un
  try/except con backoff y `client.reconnect()`.
- **QoS 2 no está soportado oficialmente por IoT Hub** según la documentación de
  Microsoft (que indica que debería cerrar la conexión), pero en la prueba no se observó
  ese rechazo explícito — se documenta como hallazgo abierto, no como comportamiento
  garantizado, ya que no se instrumentó captura de tráfico (Wireshark) para confirmar si
  hubo degradación silenciosa a QoS 1.
- Pausar la simulación de Wokwi **no es equivalente** a un corte de red real (congela todo
  el dispositivo, no solo la conectividad), por lo que esa comparación específica quedó
  incompleta y se documenta como limitación de la prueba, no como resultado.

## Estructura del repositorio

```
.
├── README.md
├── sdk-python/
│   └── sensor_ambiental.py       # Lab 2, reutilizado como baseline
├── mqtt-explicito/
│   └── mqtt_explicito.py         # Nuevo: SAS + DPS + MQTT a mano con paho-mqtt
├── wokwi/
│   ├── sketch.ino                # Firmware Arduino, sin cambios respecto al Lab 2
│   ├── diagram.json
│   └── libraries.txt
└── evidencias/
    ├── lab3_diagrama_flujo.png   # Diagrama MQTT → DPS/Hub → IoT Central
    ├── e1_data_explorer.png      # Data Explorer: mismo hub para ambos nodos
    ├── e2_mqtt_connected.png     # Python-MQTT-Explicito: Connected
    └── e3_runtime_error.png      # Crash tras corte de red (sin reconexión automática)
```
