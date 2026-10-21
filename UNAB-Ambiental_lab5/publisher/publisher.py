"""
UNAB-Ambiental — Laboratorio 5: publicador MQTT.

Publica temperature, humidity e illuminance cada INTERVAL_SECONDS hacia el broker
Mosquitto de la plataforma. Los valores son sintéticos pero coherentes: siguen un ciclo
día/noche (pico a las 15:00 hora local) con algo de ruido, siempre dentro de los rangos
operativos del escenario (16-32 °C, 35-70 % RH, 100-800 lux). Sin intervención, la
temperatura nunca llega a 30 °C, de modo que la alerta solo se dispara cuando se fuerza.

Topics
    unab/ambiental/<sala>/telemetria   (publica)  {"temperature":..,"humidity":..,"illuminance":..,"ts":<ms>}
    unab/ambiental/<sala>/control      (escucha)  {"temperature": 38, "seconds": 300}

El mensaje de control reemplaza los valores indicados durante "seconds" segundos y sirve
para forzar la alerta de umbral (ver scripts/forzar_alerta.sh).

Configuración por variables de entorno (ver docker-compose.yml):
    MQTT_HOST, MQTT_PORT, SALA, INTERVAL_SECONDS, TZ_OFFSET_HOURS, QOS
"""

import json
import logging
import math
import os
import random
import signal
import threading
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
SALA = os.environ.get("SALA", "aula-101")
INTERVAL_SECONDS = float(os.environ.get("INTERVAL_SECONDS", "30"))
TZ_OFFSET_HOURS = float(os.environ.get("TZ_OFFSET_HOURS", "-5"))
QOS = int(os.environ.get("QOS", "1"))

TOPIC_TELEMETRIA = f"unab/ambiental/{SALA}/telemetria"
TOPIC_CONTROL = f"unab/ambiental/{SALA}/control"

# Rangos operativos del escenario (Taller Teórico 1)
LIMITES = {
    "temperature": (16.0, 32.0),
    "humidity": (35.0, 70.0),
    "illuminance": (100.0, 800.0),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("publisher")

stop_event = threading.Event()
override_lock = threading.Lock()
override = {"valores": {}, "hasta": 0.0}  # "hasta" en tiempo monotónico


def acotar(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))


def valores_normales(ahora_utc):
    """Ciclo día/noche: pico a las 15:00 locales, mínimo a las 03:00 locales."""
    local = ahora_utc + timedelta(hours=TZ_OFFSET_HOURS)
    hora = local.hour + local.minute / 60 + local.second / 3600
    fase = math.sin(2 * math.pi * (hora - 9) / 24)

    temperature = 23.5 + 4.5 * fase + random.gauss(0, 0.3)   # ~19 a ~28 °C
    humidity = 52.0 - 12.0 * fase + random.gauss(0, 1.0)     # ~40 a ~64 %
    illuminance = 450.0 + 300.0 * fase + random.gauss(0, 15)  # ~150 a ~750 lux

    return {
        "temperature": round(acotar(temperature, *LIMITES["temperature"]), 1),
        "humidity": round(acotar(humidity, *LIMITES["humidity"]), 1),
        "illuminance": round(acotar(illuminance, *LIMITES["illuminance"]), 1),
    }


def valores_actuales(ahora_utc):
    valores = valores_normales(ahora_utc)
    with override_lock:
        if time.monotonic() < override["hasta"]:
            valores.update(override["valores"])  # el forzado puede salirse de los rangos
        elif override["valores"]:
            log.info("Fin del forzado de valores, vuelve a la señal normal.")
            override["valores"] = {}
    return valores


# ---------------- MQTT ----------------

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code.is_failure:
        log.error("Conexión rechazada por el broker: %s", reason_code)
        return
    log.info("Conectado a %s:%s. Publicando en %s", MQTT_HOST, MQTT_PORT, TOPIC_TELEMETRIA)
    client.subscribe(TOPIC_CONTROL, qos=1)  # se re-suscribe tras cada reconexión


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    log.warning("Desconectado del broker (%s). paho-mqtt reintentará solo.", reason_code)


def on_message(client, userdata, msg):
    """Mensaje de control: {"temperature": 38, "seconds": 300}."""
    try:
        orden = json.loads(msg.payload.decode("utf-8"))
        segundos = float(orden.pop("seconds", 300))
        valores = {k: float(v) for k, v in orden.items() if k in LIMITES}
        if not valores:
            log.warning("Control ignorado (sin variables válidas): %s", msg.payload)
            return
        with override_lock:
            override["valores"] = valores
            override["hasta"] = time.monotonic() + segundos
        log.warning("FORZADO por %.0f s: %s", segundos, valores)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        log.error("Mensaje de control inválido (%s): %s", exc, msg.payload)


def crear_cliente():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"publisher-{SALA}",
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client


def main():
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())

    client = crear_cliente()
    # connect_async + loop_start: si el broker aún no está listo, reintenta en segundo plano.
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    log.info("Publicador iniciado: sala=%s intervalo=%ss zona UTC%+.0f", SALA, INTERVAL_SECONDS, TZ_OFFSET_HOURS)

    siguiente = time.monotonic()
    while not stop_event.is_set():
        ahora = datetime.now(timezone.utc)
        valores = valores_actuales(ahora)
        valores["ts"] = int(ahora.timestamp() * 1000)  # milisegundos Unix (hora real del dato)
        payload = json.dumps(valores)

        try:
            info = client.publish(TOPIC_TELEMETRIA, payload, qos=QOS)
            log.info("publish rc=%s %s", info.rc, payload)
        except Exception:  # un fallo puntual nunca debe tumbar la toma de 4 días
            log.exception("Error publicando")

        siguiente += INTERVAL_SECONDS
        stop_event.wait(timeout=max(0.0, siguiente - time.monotonic()))

    log.info("Deteniendo publicador...")
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
