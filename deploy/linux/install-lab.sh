#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -f compose.yaml ]]; then cd ../..; fi
exec 3<images.manifest
read -r key checksum <&3
[[ $key == sha256 ]]
printf '%s  images.tar.gz\n' "$checksum" | sha256sum --check -
read -r key expected <&3
[[ $key == platform ]]
platform=$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')
[[ $platform == "$expected" ]] || { echo "Archive requires $expected; engine is $platform" >&2; exit 1; }
docker compose version
docker load --input images.tar.gz
while read -r tag expected; do
    actual=$(docker image inspect --format '{{.Id}}' "$tag")
    [[ $expected == "$actual" ]] || { echo "Image ID mismatch: $tag" >&2; exit 1; }
done <&3
mkdir -p captures
