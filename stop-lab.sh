#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
source deploy/common.sh
check_project
running=$(worker_ids -q)
if [[ -n $running ]]; then
    { saved_workers; printf '%s\n' "$running"; } | sort -u |
        awk '/^[0-9a-f]+$/ {printf "%s\"%s\"", sep, $0; sep=","}' > .stopped-workers.ids.tmp
    { printf '['; cat .stopped-workers.ids.tmp; printf ']\n'; } > .stopped-workers.tmp
    mv -- .stopped-workers.tmp .stopped-workers.json
    rm -- .stopped-workers.ids.tmp
fi
docker compose stop
if [[ -n $running ]]; then
    mapfile -t ids <<< "$running"
    docker stop "${ids[@]}"
fi
