#!/usr/bin/env bash
: "${HOST_IP:?Set HOST_IP for the new host}"
: "${NIC:?Set NIC for the new host}"
: "${MODEL_PATH:?Set MODEL_PATH inside the container}"
: "${WORK_DIR:?Set an absolute writable WORK_DIR}"
export LOG_DIR="$WORK_DIR/logs"
export PYTHON="${PYTHON:-python3}"
mkdir -p "$LOG_DIR"
