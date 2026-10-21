#!/usr/bin/env bash
# Fuerza un valor alto de temperatura en el publicador para disparar la alerta de Grafana.
# Uso:  ./scripts/forzar_alerta.sh [temperatura] [segundos]     (por defecto 38 °C durante 300 s)
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then set -a; . ./.env; set +a; fi
TEMP="${1:-38}"
SEGUNDOS="${2:-300}"
SALA="${SALA:-aula-101}"

docker compose exec -T mosquitto mosquitto_pub \
  -t "unab/ambiental/${SALA}/control" \
  -m "{\"temperature\": ${TEMP}, \"seconds\": ${SEGUNDOS}}"

echo "Forzando temperature=${TEMP} durante ${SEGUNDOS} s en la sala ${SALA}."
echo "Ver el efecto:  docker compose logs -f publisher"
