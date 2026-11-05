#!/usr/bin/env bash
# Deployment parameters matched to successful smoke 20261101-512; runtime bindings required.
: "${D_HTTP_PORT:?Set D_HTTP_PORT from current discovery/allocation}"
: "${D_IP:?Set D_IP from current discovery/allocation}"
: "${HTTP_PORT:?Set HTTP_PORT from current discovery/allocation}"
: "${LOCAL_IP:?Set LOCAL_IP from current discovery/allocation}"
: "${P_HTTP_PORT:?Set P_HTTP_PORT from current discovery/allocation}"
: "${P_IP:?Set P_IP from current discovery/allocation}"
set -e
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROXY_SCRIPT="${PROXY_SCRIPT:-$SCRIPT_DIR/load_balance_proxy_server_example.py}"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
exec python3 ''"${PROXY_SCRIPT}"'' \
  --host ''"${LOCAL_IP}"'' \
  --port ''"${HTTP_PORT}"'' \
  --prefiller-hosts ''"${P_IP}"'' \
  --prefiller-ports ''"${P_HTTP_PORT}"'' \
  --decoder-hosts ''"${D_IP}"'' \
  --decoder-ports ''"${D_HTTP_PORT}"''
