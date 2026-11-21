#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f images.json ]; then docker compose build ui; fi
exec python3 deploy/lab.py start
