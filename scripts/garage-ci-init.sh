#!/usr/bin/env bash
# Starts a throwaway Garage for CI, as the api's compose.dev.yml and garage-dev-init.sh do. Locally, use the api's stack.
set -euo pipefail

name=${GARAGE_CONTAINER:-garage}
port=${GARAGE_PORT:-3900}

docker run -d --name "$name" -p "127.0.0.1:$port:3900" \
    -e "GARAGE_RPC_SECRET=$(openssl rand -hex 32)" \
    -v "$PWD/dev/garage.toml:/etc/garage.toml:ro" \
    dxflrs/garage:v2.4.1

s3() { docker exec "$name" /garage "$@"; }

for _ in $(seq 30); do
    s3 status >/dev/null 2>&1 && break
    sleep 1
done

node_id=$(s3 node id -q)
s3 layout assign -z dc1 -c 1G "${node_id%%@*}"
s3 layout apply --version 1

s3 key import --yes "$S3__ACCESS_KEY_ID" "$S3__SECRET_ACCESS_KEY" -n ci
s3 bucket create "$S3__BUCKET"
s3 bucket allow --read --write "$S3__BUCKET" --key "$S3__ACCESS_KEY_ID"
