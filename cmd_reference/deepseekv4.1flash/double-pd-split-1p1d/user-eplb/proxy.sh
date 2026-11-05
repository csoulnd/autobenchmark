#!/usr/bin/env bash
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit $?
PROXY_SCRIPT="${PROXY_SCRIPT:-$SCRIPT_DIR/proxy.py}"
: "${PROXY_HOST:?Set PROXY_HOST}"
: "${PROXY_PORT:?Set PROXY_PORT}"
: "${P_IP:?Set P_IP}"
: "${P_HTTP_PORT:?Set P_HTTP_PORT}"
: "${D_IP:?Set D_IP}"
: "${D_HTTP_PORT:?Set D_HTTP_PORT}"
[[ -f "$PROXY_SCRIPT" ]] || { echo "Missing proxy script" >&2; exit 1; }
exec python "$PROXY_SCRIPT" \
  --port "$PROXY_PORT" \
  --host "$PROXY_HOST" \
  --prefiller-hosts "$P_IP" \
  --prefiller-ports "$P_HTTP_PORT" \
  --decoder-hosts "$D_IP" \
  --decoder-ports "$D_HTTP_PORT"
