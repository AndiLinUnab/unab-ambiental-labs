"""
UNAB-Ambiental — Laboratorio 4, Tercer protocolo: HTTP/HTTPS (VM)
Publica temperature, humidity, illuminance hacia Azure IoT Central vía un POST HTTPS
directo al endpoint nativo de telemetría de IoT Hub, sin MQTT ni AMQP.

Justificación de negocio: HTTP es el protocolo más simple de depurar (funciona con curl,
Postman, cualquier navegador) y el único que sobrevive sin cambios en redes corporativas
que bloquean todo menos el puerto 443 saliente con inspección de contenido HTTPS estándar.
A cambio, cada mensaje abre y cierra una conexión nueva (sin sesión persistente como
MQTT/AMQP), lo que implica más overhead por mensaje.

Requisitos:
    pip install requests   (o python3-requests del sistema, como ya usamos para DPS)

Antes de correr, exporta:
    export ID_SCOPE="tu_id_scope"
    export DEVICE_ID="Python-HTTP"      # dispositivo NUEVO, distinto a los anteriores
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

DPS_HOST = "global.azure-devices-provisioning.net"
DPS_API_VERSION = "2019-03-31"
HUB_API_VERSION = "2021-04-12"
SEND_INTERVAL_SECONDS = 10
N_MESSAGES = 10

TEMP_RANGE = (16.0, 32.0)
HUM_RANGE = (35.0, 70.0)
LUX_RANGE = (100.0, 800.0)


def read_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: falta la variable de entorno {name}.")
        sys.exit(1)
    return value


# ---------------- SAS token (idéntico a los Labs 2, 3 y 4-AMQP) ----------------

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


# ---------------- DPS manual (idéntico a los labs anteriores) ----------------

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

    # El endpoint HTTPS nativo de IoT Hub para telemetría device-to-cloud:
    #   POST https://{hub}/devices/{deviceId}/messages/events?api-version=2021-04-12
    hub_resource_uri = f"{assigned_hub}/devices/{device_id}"
    sas_token = generate_sas_token(hub_resource_uri, primary_key)

    telemetry_url = (
        f"https://{assigned_hub}/devices/{device_id}/messages/events"
        f"?api-version={HUB_API_VERSION}"
    )
    headers = {
        "Authorization": sas_token,
        "Content-Type": "application/json",
    }

    print(f"[HTTP] Enviando a {telemetry_url} (puerto 443, TLS, sin conexión persistente)...")

    for i in range(N_MESSAGES):
        reading = generate_reading()
        reading["timestamp"] = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(reading)

        t_publish = time.time()
        resp = requests.post(telemetry_url, headers=headers, data=payload, timeout=15)
        elapsed_ms = (time.time() - t_publish) * 1000

        status_txt = "OK" if resp.status_code in (200, 204) else f"FALLO ({resp.status_code})"
        print(f"[Telemetría HTTP enviada] {payload} "
              f"({len(payload.encode('utf-8'))} bytes, {status_txt}, "
              f"respuesta en {elapsed_ms:.0f} ms)")

        time.sleep(SEND_INTERVAL_SECONDS)

    print("[HTTP] Listo. A diferencia de MQTT/AMQP, aquí no hay conexión que cerrar: "
          "cada mensaje fue una petición HTTPS independiente.")


if __name__ == "__main__":
    main()
