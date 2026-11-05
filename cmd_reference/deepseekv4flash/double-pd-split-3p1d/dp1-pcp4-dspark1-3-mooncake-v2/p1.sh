#!/usr/bin/env bash
: "${SHELL_RC:?Set SHELL_RC for this instance}"
: "${LOCAL_IP:?Set LOCAL_IP for this instance}"
: "${NIC_NAME:?Set NIC_NAME for this instance}"
: "${MODEL_PATH:?Set MODEL_PATH for this instance}"
: "${RUN_DIR:?Set RUN_DIR for this instance}"
: "${HTTP_PORT:?Set HTTP_PORT for this instance}"
: "${RPC_PORT:?Set RPC_PORT for this instance}"
: "${KV_PORT:?Set KV_PORT for this instance}"
: "${LIB_DIR:?Set LIB_DIR for this instance}"
[[ "$KV_PORT" =~ ^[0-9]+$ ]] || { echo "KV_PORT must be numeric" >&2; exit 1; }
source "$SHELL_RC"

unset ftp_proxy
unset https_proxy
unset http_proxy
unset HCCL_INTRA_ROCE_ENABLE

nic_name="$NIC_NAME"
local_ip="$LOCAL_IP"

export HCCL_IF_IP=$local_ip
export GLOO_SOCKET_IFNAME=$nic_name
export TP_SOCKET_IFNAME=$nic_name
export HCCL_SOCKET_IFNAME=$nic_name

export HCCL_ALGO=level0:fullmesh

export VLLM_RPC_TIMEOUT=3600000
export VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS=3000
export HCCL_EXEC_TIMEOUT=204
export HCCL_CONNECT_TIMEOUT=120
export HCCL_BUFFSIZE=1024
export LD_LIBRARY_PATH="${LIB_DIR}:${LD_LIBRARY_PATH:-}"

export OMP_PROC_BIND=false
export OMP_NUM_THREADS=10
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True

export TASK_QUEUE_ENABLE=1

export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3
export VLLM_USE_V2_MODEL_RUNNER=1
export VLLM_PREFIX_CACHE_RETENTION_INTERVAL=4096
export VLLM_USE_FASTOKENS=1
export ASCEND_LOCAL_COMM_RES='{"version":"1.3"}'

mkdir -p "$RUN_DIR"
cd "$RUN_DIR" || exit 1

vllm serve "$MODEL_PATH" \
  --host $local_ip \
  --port "$HTTP_PORT" \
  --api-server-count 4 \
  --data-parallel-size 1 \
  --data-parallel-address $local_ip \
  --data-parallel-rpc-port "$RPC_PORT" \
  --tensor-parallel-size 1 \
  --prefill-context-parallel-size 4 \
  --max_model_len 1048576 \
  --max-num-batched-tokens 10240 \
  --served-model-name dsv \
  --gpu-memory-utilization 0.92 \
  --enable-expert-parallel \
  --async-scheduling \
  --max-num-seqs 128 \
  --block-size 32 \
  --enable-prefix-caching \
  --tokenizer-mode deepseek_v4 \
  --tool-call-parser deepseek_v4 \
  --enable-auto-tool-choice \
  --reasoning-parser deepseek_v4 \
  --trust-remote-code \
  --kv-cache-dtype fp8 \
  --attention_config.indexer_kv_dtype fp8 \
  --enforce-eager \
  --no-disable-hybrid-kv-cache-manager \
  --speculative-config '{"num_speculative_tokens":1,"method":"dspark","enforce_eager":true}' \
  --kv-transfer-config '{"kv_connector":"MooncakeConnectorV2","kv_role":"kv_producer","kv_port":"'"${KV_PORT}"'","engine_id":"0","kv_connector_extra_config":{"prefill":{"dp_size":1,"tp_size":1},"decode":{"dp_size":4,"tp_size":1}}}' \
  --additional_config '{"enable_cpu_binding":"True","enable_fused_mc2":0,"multistream_overlap_shared_expert":true,"enable_shared_expert_dp":true}'

