# UNAB-Ambiental — Laboratorio 2: Flota IoT Central + generación de datos

Ampliación de la flota del Laboratorio 1 a 8 dispositivos sobre el mismo Device Template
(`Nodo-Ambiental-ESP32`), con dos nodos de código: un script Python en una VM y un ESP32
virtual en Wokwi.

**Integrantes:**
- Andi Lin – U00180153
- Juan Sebastián Buitrago Caballero – U00179631
- Miguel Ángel Solano Díaz – U00177983

No se entrega código de producción, solo los dos nodos pedidos por el enunciado (Python y
Arduino/ESP32) más su documentación. Ninguna credencial real está incluida en este
repositorio: todos los scripts usan placeholders o variables de entorno.

## Inventario de la flota (8 dispositivos)

| N | Tipo | Generación de datos | Vars |
|---|---|---|---|
| 6 | Simulados IoT Central (`29kjfsmio2`, `Simulado-Aula-101` a `105`) | Simulador nativo de la aplicación | temperature, humidity, illuminance |
| 1 | Python en VM (`Python-VM`) | Script `sensor_ambiental.py`, valores sintéticos aleatorios cada 10s | temperature, humidity, illuminance + comando/property |
| 1 | ESP32 Arduino en Wokwi (`ESP32-Wokwi`) | `sketch.ino`, lectura de DHT22 + potenciómetro | temperature, humidity, illuminance + LED (`setAlertLed`) |

## Nodo 1 — Python en una VM

### Qué hace
`python-vm/sensor_ambiental.py` se aprovisiona contra Azure IoT Central vía Device
Provisioning Service (DPS) usando autenticación por Symmetric Key (SAS), y luego:
- Publica `temperature`, `humidity`, `illuminance` cada 10 segundos (valores sintéticos
  dentro de los rangos operativos del escenario: 16–32 °C, 35–70 % RH, 100–800 lux).
- Escucha los comandos remotos `reiniciar` y `lecturaForzada` (direct methods).
- Escucha la property writable `modoAlerta` y confirma el nuevo valor como reported
  property.

### Provisionamiento mínimo de la VM
1. VM con Ubuntu 24.04+ (VirtualBox, VMware, Hyper-V, UTM o VM en la nube), con salida a
   Internet (puertos 8883/443 abiertos hacia afuera, que es el comportamiento por defecto).
2. Instalar dependencias:
   ```bash
   sudo apt update && sudo apt install -y python3 python3-venv python3-pip
   python3 -m venv venv && source venv/bin/activate
   pip install azure-iot-device
   ```
3. Crear un dispositivo nuevo (no simulado) en IoT Central sobre el template
   `Nodo-Ambiental-ESP32`, y obtener su **ID Scope**, **Device ID** y **Primary Key** desde
   el botón "Connect" del dispositivo.
4. Exportar esas credenciales como variables de entorno (nunca hardcodearlas):
   ```bash
   export ID_SCOPE="tu_id_scope"
   export DEVICE_ID="tu_device_id"
   export PRIMARY_KEY="tu_primary_key"
   ```
5. Ejecutar: `python3 sensor_ambiental.py`

## Nodo 2 — ESP32 Arduino en Wokwi

### Qué hace
`wokwi/sketch.ino` conecta un ESP32 virtual a la red `Wokwi-GUEST`, se aprovisiona vía DPS
(implementado manualmente con `mbedtls`, ya que no hay un SDK oficial de Azure vigente para
Arduino) y luego:
- Lee temperatura y humedad de un sensor **DHT22** virtual.
- Lee iluminancia de un **potenciómetro** virtual (sustituto de un sensor de luz real, ya
  que Wokwi no trae un BH1750 nativo).
- Publica las 3 variables por MQTT sobre TLS cada 10 segundos.
- Enciende/apaga un **LED** al recibir el comando remoto `setAlertLed`.

### Componentes y conexiones (`wokwi/diagram.json`)

| Componente | Pin ESP32 |
|---|---|
| DHT22 — VCC | 3V3 |
| DHT22 — GND | GND |
| DHT22 — Data | GPIO 15 |
| Potenciómetro — VCC | 3V3 |
| Potenciómetro — GND | GND |
| Potenciómetro — Wiper (SIG) | GPIO 34 |
| LED — Ánodo (vía resistencia 220Ω) | GPIO 2 |
| LED — Cátodo | GND |

> El `diagram.json` incluido es una reconstrucción fiel de las conexiones usadas
> durante el desarrollo. Si al importar el proyecto a Wokwi el layout visual no coincide
> exactamente con la sesión original, las conexiones lógicas (pines) sí son las correctas
> y el circuito funciona igual.

### Cómo correrlo
1. Crear un proyecto ESP32 en [wokwi.com](https://wokwi.com), pegar el contenido de
   `sketch.ino`.
2. Instalar las librerías de `wokwi/libraries.txt` desde el Library Manager de Wokwi
   (PubSubClient, DHT sensor library, Adafruit Unified Sensor, ArduinoJson).
3. Reemplazar `ID_SCOPE`, `DEVICE_ID` y `PRIMARY_KEY` en el código con las credenciales de
   un dispositivo nuevo creado en IoT Central (mismo procedimiento que el nodo Python).
4. Agregar el comando `setAlertLed` al Device Template en IoT Central si aún no existe, y
   volver a publicarlo.
5. Dar Play (▶) en Wokwi y revisar la consola serial.

## Decisiones de modelado

- **Potenciómetro en vez de sensor de luz real**: Wokwi no ofrece un BH1750 nativo, así que
  se usó un potenciómetro como sustituto interactivo, mapeando su lectura analógica
  (0–4095) al rango operativo de iluminancia (100–800 lux).
- **DPS y SAS implementados a mano en el ESP32**: el repositorio `azure-sdk-for-c-arduino`
  está archivado; se optó por reconstruir el flujo de aprovisionamiento (PUT + polling GET)
  y la generación de tokens SAS con las funciones criptográficas nativas de `mbedtls` que
  ya trae el core de ESP32 para Arduino, en vez de depender de una librería de terceros sin
  mantenimiento activo.
- **`keepalive` de MQTT subido de 15s a 60s**: el valor por defecto de `PubSubClient`
  causaba desconexiones intermitentes en la red simulada de Wokwi; se amplió el margen
  para estabilizar la conexión.
- **VM local en vez de VM en la nube**: se intentó primero crear la VM en Azure
  (aprovechando el crédito de Azure for Students), pero la cuenta trae cuota 0 por defecto
  en casi todas las familias de VM. Ante la demora de aprobación del aumento de cuota, se
  optó por VirtualBox local, que el enunciado acepta igual.

## Limitaciones observadas de IoT Central / servicio gestionado

1. **Sin SDK Arduino oficial vigente**: obliga a reimplementar DPS y SAS a mano, lo cual es
   propenso a errores (ej. el bug inicial de reintentar el registro completo en vez de
   consultar el `operationId` ya emitido).
2. **Sin historial nativo de disparo de Rules**: la evidencia de que una regla se disparó
   hay que obtenerla indirectamente (correo recibido, `Raw data` del dispositivo).
3. **Cuotas de proveedor cloud (Azure) ajenas a IoT Central pero bloqueantes**: una cuenta
   Azure for Students con cuota 0 impide crear cualquier VM hasta que se aprueba un
   aumento, lo que retrasa el desarrollo aunque el problema no sea de IoT Central en sí.

## Estructura del repositorio

```
.
├── README.md
├── python-vm/
│   └── sensor_ambiental.py
├── wokwi/
│   ├── sketch.ino
│   ├── diagram.json
│   └── libraries.txt
└── evidencias/
    ├── e1_dashboard.png       # Dashboard de flota (6 simulados, LKV)
    ├── e1_disc.png            # Simulado Disconnected
    ├── e1_conn.png            # Simulado Connected (tras reactivar)
    ├── e2_pyvm_connected.png  # Python-VM: Connected + gráficas
    ├── e2_pyvm_graph.png      # Python-VM: gráficas ampliadas
    ├── e2_terminal_cmd.png    # Python-VM: terminal con telemetría y comandos
    ├── e3_diagram_off.png     # Wokwi: circuito con LED apagado
    ├── e3_diagram_on.png      # Wokwi: circuito con LED encendido (setAlertLed)
    ├── e3_esp32_connected.png # ESP32-Wokwi: Connected en IoT Central
    ├── e3_terminal_cmd.png    # Wokwi: consola serial con comando recibido
    ├── e4_rule.png            # Rule Alerta_Sobrecalentamiento_Aula
    └── e4_email.png           # Evidencia de la Rule disparada (correo)
```
