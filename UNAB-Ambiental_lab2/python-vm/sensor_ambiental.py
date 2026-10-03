"""
UNAB-Ambiental — Laboratorio 2, Nodo Python (VM)
Publica temperature, humidity, illuminance cada N segundos hacia Azure IoT Central,
usando Device Provisioning Service (DPS) con autenticación por Symmetric Key (SAS).
También recibe:
  - Comando 'reiniciar' y 'lecturaForzada' (direct methods)
  - Property writable 'modoAlerta' (desired property del twin)

Credenciales: se leen SIEMPRE de variables de entorno, nunca hardcodeadas aquí.
Antes de correr, exporta:
    export ID_SCOPE="0ne0109B679"
    export DEVICE_ID="x4zp9klrr7"
    export PRIMARY_KEY="TU_PRIMARY_KEY_AQUI"
"""

import asyncio
import json
import os
import random
import sys
from datetime import datetime, timezone

from azure.iot.device.aio import ProvisioningDeviceClient, IoTHubDeviceClient
from azure.iot.device import Message, MethodResponse

PROVISIONING_HOST = "global.azure-devices-provisioning.net"
SEND_INTERVAL_SECONDS = 10  # cada cuánto se publica telemetría

# Rangos de simulación (coherentes con el escenario del Taller Teórico 1)
TEMP_RANGE = (16.0, 32.0)
HUM_RANGE = (35.0, 70.0)
LUX_RANGE = (100.0, 800.0)


def read_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: falta la variable de entorno {name}. Expórtala antes de correr el script.")
        sys.exit(1)
    return value


async def provision_device(id_scope: str, device_id: str, primary_key: str):
    """Registra el dispositivo contra DPS y obtiene el hub asignado."""
    provisioning_client = ProvisioningDeviceClient.create_from_symmetric_key(
        provisioning_host=PROVISIONING_HOST,
        registration_id=device_id,
        id_scope=id_scope,
        symmetric_key=primary_key,
    )
    result = await provisioning_client.register()
    if result.status != "assigned":
        print(f"ERROR: el aprovisionamiento falló con estado: {result.status}")
        sys.exit(1)

    print(f"Dispositivo aprovisionado. Hub asignado: {result.registration_state.assigned_hub}")
    return result.registration_state.assigned_hub


def generate_reading():
    return {
        "temperature": round(random.uniform(*TEMP_RANGE), 1),
        "humidity": round(random.uniform(*HUM_RANGE), 1),
        "illuminance": round(random.uniform(*LUX_RANGE), 1),
    }


async def method_handler(client: IoTHubDeviceClient):
    """Escucha comandos remotos (reiniciar, lecturaForzada)."""
    while True:
        method_request = await client.receive_method_request()
        print(f"[Comando recibido] {method_request.name} — payload: {method_request.payload}")

        if method_request.name == "reiniciar":
            print("Simulando reinicio del nodo...")
            response_payload = {"result": True, "detail": "Reinicio simulado ejecutado"}
        elif method_request.name == "lecturaForzada":
            reading = generate_reading()
            print(f"Lectura forzada: {reading}")
            response_payload = {"result": True, "detail": reading}
        else:
            response_payload = {"result": False, "detail": "Comando no reconocido"}

        method_response = MethodResponse.create_from_method_request(
            method_request, status=200, payload=response_payload
        )
        await client.send_method_response(method_response)


async def twin_patch_handler(client: IoTHubDeviceClient):
    """Escucha cambios en la property writable modoAlerta y confirma el nuevo valor (reported)."""
    while True:
        patch = await client.receive_twin_desired_properties_patch()
        print(f"[Property actualizada] desired patch recibido: {patch}")
        if "modoAlerta" in patch:
            nuevo_valor = patch["modoAlerta"]
            reported = {"modoAlerta": nuevo_valor}
            await client.patch_twin_reported_properties(reported)
            print(f"modoAlerta actualizado y confirmado como reported property: {nuevo_valor}")


async def telemetry_loop(client: IoTHubDeviceClient):
    """Publica temperature, humidity, illuminance cada SEND_INTERVAL_SECONDS."""
    while True:
        reading = generate_reading()
        reading["timestamp"] = datetime.now(timezone.utc).isoformat()
        msg = Message(json.dumps(reading))
        msg.content_encoding = "utf-8"
        msg.content_type = "application/json"

        await client.send_message(msg)
        print(f"[Telemetría enviada] {reading}")

        await asyncio.sleep(SEND_INTERVAL_SECONDS)


async def main():
    id_scope = read_env("ID_SCOPE")
    device_id = read_env("DEVICE_ID")
    primary_key = read_env("PRIMARY_KEY")

    assigned_hub = await provision_device(id_scope, device_id, primary_key)

    client = IoTHubDeviceClient.create_from_symmetric_key(
        symmetric_key=primary_key,
        hostname=assigned_hub,
        device_id=device_id,
    )
    await client.connect()
    print("Conectado a IoT Central. Publicando telemetría cada "
          f"{SEND_INTERVAL_SECONDS} segundos. Ctrl+C para detener.")

    try:
        await asyncio.gather(
            telemetry_loop(client),
            method_handler(client),
            twin_patch_handler(client),
        )
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        await client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
