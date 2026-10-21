#!/usr/bin/env bash
# Resumen de la TSDB para el informe: datos recientes, inicio/fin de la toma,
# puntos por día y huecos. Se ejecuta en la VM, desde cualquier carpeta.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then echo "Falta el archivo .env (copiar de .env.example)"; exit 1; fi
set -a; . ./.env; set +a

for nombre in ultimos_puntos rango_total cobertura_por_dia huecos; do
  echo
  echo "================ ${nombre} ================"
  consulta="$(sed "s/__BUCKET__/${INFLUX_BUCKET}/g" "queries/${nombre}.flux")"
  docker compose exec -T influxdb influx query "${consulta}" \
    --org "${INFLUX_ORG}" --token "${INFLUX_TOKEN}"
done
