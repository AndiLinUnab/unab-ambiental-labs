"""
UNAB-Ambiental — Laboratorio 4, Cliente AMQP (VM)
Publica temperature, humidity, illuminance hacia Azure IoT Central usando AMQP 1.0,
vía la librería python-qpid-proton.

IMPORTANTE: el SDK azure-iot-device de Python NO soporta AMQP (solo MQTT). Microsoft
documenta el patrón AMQP para dispositivos usando la librería 'uamqp', pero esa librería
está archivada/deprecada y falla al compilar en Python moderno (3.12+). Por eso este
script usa 'python-qpid-proton' (Apache Qpid Proton), que es la alternativa activamente
mantenida y mencionada en el propio enunciado del laboratorio ("uamqp / proton, o
equivalente vigente").

Requisitos:
    pip install python-qpid-proton requests

Antes de correr, exporta:
    export ID_SCOPE="tu_id_scope"
    export DEVICE_ID="Python-AMQP"      # dispositivo NUEVO, distinto a los anteriores
    export PRIMARY_KEY="tu_primary_key"
"""

import base64
import hashlib
import hmac
import json
import os
import random
import sys
import time
import urllib.parse
from datetime import datetime, timezone

import requests
from proton import Message
from proton.utils import BlockingConnection

DPS_HOST = "global.azure-devices-provisioning.net"
DPS_API_VERSION = "2019-03-31"
AMQP_PORT = 5671  # AMQP sobre TLS nativo. Alternativa: 443 para AMQP sobre WebSockets.
SEND_INTERVAL_SECONDS = 10
N_MESSAGES = 10  # cuántos mensajes enviar antes de terminar (para las mediciones)

TEMP_RANGE = (16.0, 32.0)
HUM_RANGE = (35.0, 70.0)
LUX_RANGE = (100.0, 800.0)


def read_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: falta la variable de entorno {name}.")
        sys.exit(1)
    return value


# ---------------- SAS token (igual que en los Labs 2 y 3) ----------------

def generate_sas_token(resource_uri: str, key: str, ttl_seconds: int = 3600, skn=None) -> str:
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


# ---------------- DPS manual (idéntico al Lab 3) ----------------

def provision_device(id_scope: str, device_id: str, primary_key: str) -> str:
    resource_uri = f"{id_scope}/registrations/{device_id}"
    sas_token = generate_sas_token(resource_uri, primary_key, skn="registration")
    headers = {"Authorization": sas_token, "Content-Type": "application/json"}

    put_url = (
        f"https://{DPS_HOST}/{id_scope}/registrations/{device_id}/register"
        f"?api-version={DPS_API_VERSION}"
    )
    resp = requests.put(put_url, headers=headers, json={"registrationId": device_id}, timeout=15)
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

    assigned_hub = data["registrationState"]["assignedHub"]
    print(f"[DPS] Hub asignado: {assigned_hub}")
    return assigned_hub


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

    # Para el device client AMQP, el username tiene un formato distinto al de MQTT:
    #   {device_id}@sas.{iot_hub_name_sin_sufijo}
    hub_short_name = assigned_hub.split(".")[0]
    username = f"{device_id}@sas.{hub_short_name}"

    hub_resource_uri = f"{assigned_hub}/devices/{device_id}"
    sas_token = generate_sas_token(hub_resource_uri, primary_key)

    telemetry_address = f"/devices/{device_id}/messages/events"
    amqp_url = f"amqps://{assigned_hub}:{AMQP_PORT}"

    print(f"[AMQP] Conectando a {amqp_url} como {username} (puerto {AMQP_PORT}, TLS nativo)...")
    t0 = time.time()
    connection = BlockingConnection(
        amqp_url,
        sasl_enabled=True,
        allowed_mechs="PLAIN",
        user=username,
        password=sas_token,
        timeout=15,
    )
    sender = connection.create_sender(telemetry_address)
    connect_elapsed_ms = (time.time() - t0) * 1000
    print(f"[AMQP] Conexión y enlace (link) establecidos en {connect_elapsed_ms:.0f} ms.")

    try:
        for i in range(N_MESSAGES):
            reading = generate_reading()
            reading["timestamp"] = datetime.now(timezone.utc).isoformat()
            payload = json.dumps(reading)

            message = Message(
                body=payload.encode("utf-8"),
                content_type="application/json;charset=utf-8",
            )
            # IMPORTANTE: por defecto proton codifica el body como sección AMQP-VALUE,
            # que IoT Hub no reconoce como payload de telemetría. 'inferred=True' con
            # un body en bytes fuerza una sección AMQP-DATA (binaria), que es lo que
            # IoT Hub espera (equivalente al payload crudo que manda MQTT).
            message.inferred = True

            t_publish = time.time()
            sender.send(message)
            elapsed_ms = (time.time() - t_publish) * 1000

            print(f"[Telemetría AMQP enviada] {payload} "
                  f"({len(payload.encode('utf-8'))} bytes, entregada en {elapsed_ms:.0f} ms)")

            time.sleep(SEND_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        connection.close()
        print("[AMQP] Conexión cerrada.")


if __name__ == "__main__":
    main()
