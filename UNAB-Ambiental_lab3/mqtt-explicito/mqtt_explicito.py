"""
UNAB-Ambiental — Laboratorio 3, Cliente MQTT explícito (VM)
Publica temperature, humidity, illuminance hacia Azure IoT Central usando
paho-mqtt directamente: SIN el SDK azure-iot-device. El aprovisionamiento DPS
y la generación de tokens SAS se hacen a mano, exactamente lo que el SDK
normalmente esconde.

Requisitos:
    pip install paho-mqtt requests

Antes de correr, exporta:
    export ID_SCOPE="tu_id_scope"
    export DEVICE_ID="Python-MQTT-Explicito"   # dispositivo NUEVO, distinto a Python-VM
    export PRIMARY_KEY="tu_primary_key"
"""

import base64
import hashlib
import hmac
import json
import os
import random
import ssl
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

import requests
import paho.mqtt.client as mqtt

DPS_HOST = "global.azure-devices-provisioning.net"
DPS_API_VERSION = "2019-03-31"
HUB_API_VERSION = "2021-04-12"
SEND_INTERVAL_SECONDS = 10
QOS = 1  # cambiar a 0 para comparar; QoS 2 no está soportado por IoT Hub

TEMP_RANGE = (16.0, 32.0)
HUM_RANGE = (35.0, 70.0)
LUX_RANGE = (100.0, 800.0)


def read_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: falta la variable de entorno {name}.")
        sys.exit(1)
    return value


# ---------------- Generación manual del SAS token ----------------

def generate_sas_token(resource_uri: str, key: str, ttl_seconds: int = 3600, skn: Optional[str] = None) -> str:
    """Reimplementación manual del token SAS (esto es lo que azure-iot-device hace por debajo)."""
    encoded_uri = urllib.parse.quote(resource_uri, safe="")
    expiry = int(time.time()) + ttl_seconds
    to_sign = f"{encoded_uri}\n{expiry}"

    key_bytes = base64.b64decode(key)
    signature = base64.b64encode(
        hmac.new(key_bytes, to_sign.encode("utf-8"), hashlib.sha256).digest()
    )
    encoded_signature = urllib.parse.quote(signature, safe="")

    token = f"SharedAccessSignature sr={encoded_uri}&sig={encoded_signature}&se={expiry}"
    if skn:
        token += f"&skn={skn}"
    return token


# ---------------- DPS manual (PUT + polling GET) ----------------

def provision_device(id_scope: str, device_id: str, primary_key: str) -> str:
    resource_uri = f"{id_scope}/registrations/{device_id}"
    sas_token = generate_sas_token(resource_uri, primary_key, skn="registration")

    headers = {"Authorization": sas_token, "Content-Type": "application/json"}
    put_url = (
        f"https://{DPS_HOST}/{id_scope}/registrations/{device_id}/register"
        f"?api-version={DPS_API_VERSION}"
    )
    body = {"registrationId": device_id}

    t0 = time.time()
    resp = requests.put(put_url, headers=headers, json=body, timeout=15)
    data = resp.json()
    status = data.get("status")
    operation_id = data.get("operationId")
    print(f"[DPS] PUT status={status} operationId={operation_id}")

    get_url = (
        f"https://{DPS_HOST}/{id_scope}/registrations/{device_id}/operations/{operation_id}"
        f"?api-version={DPS_API_VERSION}"
    )
    attempts = 0
    while status == "assigning" and attempts < 10:
        attempts += 1
        time.sleep(3)
        resp = requests.get(get_url, headers=headers, timeout=15)
        data = resp.json()
        status = data.get("status")
        print(f"[DPS] Poll #{attempts} -> status={status}")

    if status != "assigned":
        print("ERROR: no se pudo aprovisionar el dispositivo.")
        print(data)
        sys.exit(1)

    elapsed = time.time() - t0
    assigned_hub = data["registrationState"]["assignedHub"]
    print(f"[DPS] Hub asignado: {assigned_hub} (tardó {elapsed:.1f}s)")
    return assigned_hub


# ---------------- MQTT explícito ----------------

def on_connect_v2(client, userdata, flags, reason_code, properties=None):
    _handle_connect(client, reason_code)


def on_connect_v1(client, userdata, flags, rc):
    _handle_connect(client, rc)


def _handle_connect(client, reason_code):
    if int(reason_code) == 0:
        print("[MQTT] Conectado a IoT Central.")
        client.subscribe("$iothub/twin/PATCH/properties/desired/#")
        client.subscribe("$iothub/methods/POST/#")
    else:
        print(f"[MQTT] Falló la conexión, reason_code={reason_code}")


def on_message(client, userdata, msg):
    print(f"[MQTT IN] {msg.topic} -> {msg.payload.decode(errors='replace')}")


def on_disconnect_v2(client, userdata, flags, reason_code, properties=None):
    print(f"[MQTT] Desconectado (reason_code={reason_code}). Se reintentará la conexión.")


def on_disconnect_v1(client, userdata, rc):
    print(f"[MQTT] Desconectado (rc={rc}). Se reintentará la conexión.")


def generate_reading():
    return {
        "temperature": round(random.uniform(*TEMP_RANGE), 1),
        "humidity": round(random.uniform(*HUM_RANGE), 1),
        "illuminance": round(random.uniform(*LUX_RANGE), 1),
    }


def main():
    id_scope = read_env("ID_SCOPE")
    device_id = read_env("DEVICE_ID")
    primary_key = read_env("PRIMARY_KEY")

    assigned_hub = provision_device(id_scope, device_id, primary_key)

    # SAS token para el HUB (distinto resource_uri al de DPS)
    hub_resource_uri = f"{assigned_hub}/devices/{device_id}"
    sas_token = generate_sas_token(hub_resource_uri, primary_key)

    username = f"{assigned_hub}/{device_id}/?api-version={HUB_API_VERSION}"
    telemetry_topic = f"devices/{device_id}/messages/events/"

    # Compatibilidad con paho-mqtt 1.x y 2.x (CallbackAPIVersion solo existe desde la 2.0)
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=device_id,
            protocol=mqtt.MQTTv311,
        )
        client.on_connect = on_connect_v2
        client.on_disconnect = on_disconnect_v2
    else:
        client = mqtt.Client(client_id=device_id, protocol=mqtt.MQTTv311)
        client.on_connect = on_connect_v1
        client.on_disconnect = on_disconnect_v1
    client.username_pw_set(username=username, password=sas_token)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.on_message = on_message

    print(f"[MQTT] Conectando a {assigned_hub}:8883 como {device_id} (QoS={QOS})...")
    client.connect(assigned_hub, port=8883, keepalive=60)
    client.loop_start()

    try:
        while True:
            reading = generate_reading()
            reading["timestamp"] = datetime.now(timezone.utc).isoformat()
            payload = json.dumps(reading)

            t_publish = time.time()
            result = client.publish(telemetry_topic, payload, qos=QOS)
            result.wait_for_publish(timeout=10)
            elapsed_ms = (time.time() - t_publish) * 1000

            print(f"[Telemetría enviada] {payload} "
                  f"({len(payload.encode('utf-8'))} bytes, ack en {elapsed_ms:.0f} ms, QoS={QOS})")

            time.sleep(SEND_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
