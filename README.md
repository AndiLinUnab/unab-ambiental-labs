# UNAB-Ambiental — Proyecto completo (Laboratorios 1 a 4)

Sistema de Monitoreo Ambiental de Espacios Académicos construido sobre Azure IoT Central,
desarrollado a lo largo de 4 laboratorios del curso IoT + Cloud + Sistemas Distribuidos,
Universidad Autónoma de Bucaramanga, 2026.

**Integrantes:**
- Andi Lin – U00180153
- Juan Sebastián Buitrago Caballero – U00179631
- Miguel Ángel Solano Díaz – U00177983

## El escenario

La universidad no tenía visibilidad en tiempo real de las condiciones ambientales
(temperatura, humedad, iluminación) en aulas y laboratorios, lo que impedía detectar a
tiempo sobrecalentamiento de equipos, humedad excesiva o iluminación inadecuada. A lo
largo de los 4 laboratorios se diseñó, modeló, implementó y puso a prueba una solución
completa sobre Azure IoT Central, partiendo de una sola aplicación y un único Device
Template (`Nodo-Ambiental-ESP32`) que se reutiliza y amplía en cada entrega.

## Estructura del repositorio

```
.
├── README.md                     (este archivo)
├── UNAB-Ambiental_lab1/           Diseño conceptual + primera app en IoT Central
├── UNAB-Ambiental_lab2/           Flota de 8 dispositivos: simulados + Python-VM + ESP32-Wokwi
├── UNAB-Ambiental_lab3/           MQTT explícito (SDK vs paho-mqtt) + mediciones
└── UNAB-Ambiental_lab4/           AMQP + HTTP como transportes alternativos a MQTT
```

Cada carpeta conserva su propio `README.md` con el detalle completo de ese laboratorio
(decisiones de modelado, cómo reproducir, limitaciones encontradas). Este README principal
da el panorama general y la línea de tiempo del proyecto; para el detalle técnico de cada
etapa, entrar a la carpeta correspondiente.

## Qué cubre cada laboratorio

| Lab | Qué se hizo | Carpeta |
|---|---|---|
| **1** | Diseño conceptual del escenario (problemática, arquitectura de referencia, tabla de telemetría). Creación de la Application en IoT Central, el Device Template con 3 telemetrías + property + 2 comandos, Views y la primera Rule de alerta por umbral. | `UNAB-Ambiental_lab1/` |
| **2** | Ampliación a una flota de 8 dispositivos sobre el mismo template: 6 simulados nativos, 1 nodo Python corriendo en una VM (SDK `azure-iot-device`), y 1 ESP32 virtual en Wokwi con firmware Arduino (DPS + MQTT implementado a mano con `mbedtls`, ya que no hay SDK Arduino vigente para Azure). | `UNAB-Ambiental_lab2/` |
| **3** | Se "abrió la caja negra" del SDK: un cliente MQTT explícito con `paho-mqtt` (SAS y topics generados a mano) junto al SDK y Wokwi, los tres contra la misma aplicación. Mediciones de payload, latencia, QoS (0/1/2) y comportamiento ante corte de red. | `UNAB-Ambiental_lab3/` |
| **4** | AMQP 1.0 como transporte alternativo (`python-qpid-proton`, ya que `azure-iot-device` no soporta AMQP en Python) y HTTP/HTTPS como tercer protocolo. Tabla comparativa final MQTT · AMQP · HTTP con mediciones reales y recomendaciones de capa. | `UNAB-Ambiental_lab4/` |

## Evolución de la arquitectura a través de los laboratorios

```
Lab 1: Application + Device Template + 1 dispositivo simulado + 1 Rule
   │
   ▼
Lab 2: + 5 simulados más + Python-VM (SDK/MQTT) + ESP32-Wokwi (MQTT a mano)
   │        = 8 dispositivos sobre el mismo template
   ▼
Lab 3: Mismo Python-VM, pero se agrega un cliente MQTT explícito (paho-mqtt)
   │    para comparar contra el SDK, sin agregar dispositivos a la flota base
   ▼
Lab 4: Se agregan 2 dispositivos de comparación de protocolo: Python-AMQP
        (python-qpid-proton) y Python-HTTP (requests), ambos sobre el
        mismo Device Template
```

A lo largo de todo el proyecto solo existió **una aplicación** y **un Device Template**;
lo que cambió entre laboratorios fue qué y cuántos dispositivos se conectan, y por qué
protocolo/librería lo hacen.

## Credenciales y seguridad

Ningún archivo de este repositorio contiene una credencial real (Primary Key, SAS token,
connection string). Todos los scripts leen `ID_SCOPE`, `DEVICE_ID` y `PRIMARY_KEY` desde
variables de entorno; el firmware de Wokwi usa placeholders que se reemplazan localmente
antes de ejecutar en el simulador, nunca antes de hacer commit.

## Hallazgos técnicos más relevantes (resumen transversal)

Estos problemas aparecieron en labs específicos, pero son relevantes para todo el
proyecto porque afectan decisiones de arquitectura futuras (ver `Labs 5-8` planeados):

- **Cuotas de Azure for Students**: la suscripción trae cuota 0 por defecto en casi todas
  las familias de VM; migrar a la región **Chile Central** resolvió el problema al tener
  cuota disponible donde regiones tradicionales estaban saturadas para cuentas de
  estudiante (Lab 2 → Lab 4).
- **Sin SDK Arduino oficial vigente para Azure** (`azure-sdk-for-c-arduino` archivado):
  obligó a reimplementar DPS y tokens SAS a mano con `mbedtls` en el firmware ESP32
  (Lab 2).
- **`azure-iot-device` (Python) no soporta AMQP**, solo MQTT: obligó a usar
  `python-qpid-proton` en vez del SDK para el Lab 4, y a resolver un bug de codificación
  de payload (`message.inferred = True`) que no existe en el mundo MQTT.
- **HTTP pierde el estado de conexión en tiempo real**: un dispositivo que publica por
  HTTP puede aparecer "Disconnected" en IoT Central aunque los datos lleguen
  perfectamente, por no mantener una conexión persistente (Lab 4).
- **El SDK da resiliencia gratis; un cliente explícito (MQTT/AMQP a mano) no**: se
  demostró con un crash real (`RuntimeError`) al cortar la red con el cliente MQTT
  explícito del Lab 3, mientras el SDK nunca mostró ese problema.

## Recomendación final de protocolo (acumulada, Labs 3-4)

| Capa | Protocolo recomendado | Por qué |
|---|---|---|
| Dispositivo (ESP32/Wokwi) | **MQTT** | Más liviano, mejor soporte en microcontroladores con RAM limitada |
| Entre servicios Azure / plataforma propia | **AMQP** | Garantías de entrega más ricas (sesiones, créditos de flujo) para Service Bus/Event Hubs |
| Protocolo descartado para el resto del curso | HTTP | Latencia ~4x mayor que MQTT y pérdida del estado de conexión en tiempo real |

## Cómo navegar este repositorio

1. Empezar por `UNAB-Ambiental_lab1/README.md` para entender el escenario y el modelo
   base.
2. Cada carpeta siguiente asume que la aplicación y el Device Template del Lab 1 ya
   existen y fueron ampliados, no recreados desde cero.
3. Los informes técnicos (`.docx`) de cada laboratorio, con las tablas de mediciones y
   capturas completas, se entregan por separado del repositorio (según lo pedido en cada
   enunciado: "Informe" y "Repo" son entregables distintos).
