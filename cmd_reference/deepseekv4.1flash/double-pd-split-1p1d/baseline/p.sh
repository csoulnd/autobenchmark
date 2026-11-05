#!/usr/bin/env bash
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit $?
ENV_SCRIPT="${ENV_SCRIPT:-$SCRIPT_DIR/env.sh}"
[[ -f "$ENV_SCRIPT" ]] || { echo "Missing ENV_SCRIPT" >&2; exit 1; }
source "$ENV_SCRIPT" || exit $?
: "${RUN_DIR:?Set RUN_DIR for this instance}"
: "${NIC_NAME:?Set NIC_NAME for this instance}"
: "${LOCAL_IP:?Set LOCAL_IP for this instance}"
: "${AICPU_HEADERS:?Set AICPU_HEADERS for this instance}"
: "${MODEL_PATH:?Set MODEL_PATH for this instance}"
: "${BIND_HOST:?Set BIND_HOST for this instance}"
: "${HTTP_PORT:?Set HTTP_PORT for this instance}"
: "${RPC_PORT:?Set RPC_PORT for this instance}"
: "${KV_PORT:?Set KV_PORT for this instance}"
: "${ENGINE_ID:?Set ENGINE_ID for this instance}"
[[ "$RUN_DIR" = /* && "$MODEL_PATH" = /* && "$AICPU_HEADERS" = /* ]] || { echo "Use absolute runtime paths" >&2; exit 1; }
[[ -d "$MODEL_PATH" && -d "$AICPU_HEADERS" ]] || { echo "Missing model or headers" >&2; exit 1; }
mkdir -p "$RUN_DIR/logs" || exit $?
cd "$RUN_DIR" || exit $?
export VLLM_RPC_TIMEOUT=3600000
export GLOO_SOCKET_IFNAME="$NIC_NAME"
export TP_SOCKET_IFNAME="$NIC_NAME"
export HCCL_SOCKET_IFNAME="$NIC_NAME"
export HCCL_CONNECT_TIMEOUT=1200
export HCCL_DETERMINISTIC=true
export HCCL_OP_EXPANSION_MODE=CCU_SCHED
export ASCEND_LOCAL_COMM_RES='{"version":"1.3"}'
export HCCL_ALGO=level0:fullmesh
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=10
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export CPLUS_INCLUDE_PATH="$AICPU_HEADERS:$AICPU_HEADERS/aarch64-target-linux-gnu:$AICPU_HEADERS/backward"
export VLLM_USE_V2_MODEL_RUNNER=1
export VLLM_HOST_IP="$LOCAL_IP"
export HCCL_IF_IP="$LOCAL_IP"
export VLLM_USE_FASTOKENS=0
exec > >(tee -a "$RUN_DIR/logs/p.log") 2>&1
KV_CONFIG="$(python3 -c 'import json,sys; p=int(sys.argv[1]); assert 1<=p<=65535; print(json.dumps({"kv_connector":"MooncakeHybridConnector","kv_role":sys.argv[2],"kv_port":p,"engine_id":sys.argv[3],"kv_connector_extra_config":{"prefill":{"dp_size":8,"tp_size":1},"decode":{"dp_size":8,"tp_size":1}}}))' "$KV_PORT" kv_producer "$ENGINE_ID")" || exit $?
export HCCL_BUFFSIZE=1024
export VLLM_ENGINE_READY_TIMEOUT_S=3600

vllm serve "$MODEL_PATH" \
  --served-model-name deepseek-v41-a5-1005-real-1p1d \
  --host "$BIND_HOST" \
  --port "$HTTP_PORT" \
  --api-server-count 8 \
  --renderer-num-workers 8 \
  --data-parallel-size 8 \
  --data-parallel-rpc-port "$RPC_PORT" \
  --tensor-parallel-size 1 \
  --enable-expert-parallel \
  --enable-ep-weight-filter \
  --max-model-len 1048576 \
  --block-size 128 \
  --enable-prefix-caching \
  --model-loader-extra-config '{"enable_multithread_load":true,"num_threads":128}' \
  --trust-remote-code \
  --engram-config '{"cpu_offload":true,"dp_shared_memory":true}' \
  --tokenizer-mode deepseek_v41 \
  --reasoning-parser deepseek_v41 \
  --tool-call-parser deepseek_v41 \
  --enable-auto-tool-choice \
  --quantization deepseek_v4_fp8 \
  --async-scheduling \
  --kv-transfer-config "$KV_CONFIG" \
  --profiler-config '{"profiler":"torch","torch_profiler_dir":"./dsv4_profile","torch_profiler_with_stack":false}' \
  --seed 1024 \
  --max-num-batched-tokens 32768 \
  --max-num-seqs 32 \
  --gpu-memory-utilization 0.85 \
  --speculative-config '{"method":"dspark","num_speculative_tokens":5,"enforce_eager":true}' \
  --enforce-eager \
  --additional-config '{"multistream_engram_overlap":true,"enable_cpu_binding":true,"multistream_overlap_shared_expert":true,"multistream_dsv4_dsa_overlap":true,"enable_fused_mc2":0,"enable_force_eplb":false}'
