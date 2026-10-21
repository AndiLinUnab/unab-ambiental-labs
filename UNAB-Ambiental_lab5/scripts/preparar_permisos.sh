#!/usr/bin/env bash
# Tras copiar el proyecto con scp desde Windows, las carpetas pueden quedar con permisos
# drwx------ y Grafana (que corre con otro usuario dentro del contenedor) no puede leer
# el aprovisionamiento ("permission denied" en su log). Este script lo corrige.
set -euo pipefail
cd "$(dirname "$0")/.."
chmod +x scripts/*.sh
chmod -R a+rX grafana mosquitto telegraf queries
echo "Permisos corregidos. Ahora: docker compose up -d --build"
