#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
source deploy/common.sh
check_project
if [[ -f Dockerfile ]]; then docker compose build ui; fi
mkdir -p captures
docker compose up -d --pull never --no-build
if [[ -f .stopped-workers.json ]]; then
    owned=$(worker_ids -aq)
    while read -r id; do
        if [[ $id =~ ^[a-f0-9]{64}$ ]] && grep -Fxq "$id" <<< "$owned"; then docker start "$id"; fi
    done < <(saved_workers)
    rm -- .stopped-workers.json
fi
for ((attempt=0; attempt<60; attempt++)); do
    if curl -fsS --max-time 2 http://127.0.0.1:8765/topology 2>/dev/null | grep -q '"clients"'; then
        echo 'UI: http://127.0.0.1:8765'
        exit 0
    fi
    sleep .5
done
echo 'UI startup timed out. Inspect docker compose logs ui.' >&2
exit 1
