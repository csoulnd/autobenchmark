#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/env.sh"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

exec "$PYTHON" "$(dirname "$(readlink -f "$0")")/load_balance_proxy_server_example.py" \
    --host 0.0.0.0 \
    --port 9005 \
    --prefiller-hosts 127.0.0.1 \
    --prefiller-ports 9000 \
    --decoder-hosts 127.0.0.1 \
    --decoder-ports 9001
