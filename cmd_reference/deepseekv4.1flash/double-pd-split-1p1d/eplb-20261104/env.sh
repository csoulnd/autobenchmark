#!/usr/bin/env bash
: "${ASCEND_ENV_SCRIPT:?Set CANN set_env.sh path}"
: "${ATB_ENV_SCRIPT:?Set ATB set_env.sh path}"
: "${PYTHON_BIN_DIR:?Set Python bin directory}"
: "${ASCEND_DEVLIB_DIR:?Set Ascend devlib directory}"
: "${SYSTEM_LIB_DIR:?Set system library directory}"
for required_file in "$ASCEND_ENV_SCRIPT" "$ATB_ENV_SCRIPT"; do
  [[ -f "$required_file" ]] || { echo "Missing $required_file" >&2; return 1; }
done
for required_dir in "$PYTHON_BIN_DIR" "$ASCEND_DEVLIB_DIR" "$SYSTEM_LIB_DIR"; do
  [[ -d "$required_dir" ]] || { echo "Missing $required_dir" >&2; return 1; }
done
source "$ASCEND_ENV_SCRIPT" || return $?
source "$ATB_ENV_SCRIPT" || return $?
export PATH="$PYTHON_BIN_DIR:$PATH"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$ASCEND_DEVLIB_DIR:$SYSTEM_LIB_DIR"
