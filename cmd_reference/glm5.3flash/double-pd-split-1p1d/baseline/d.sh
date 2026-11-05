#!/usr/bin/env bash
# Deployment parameters matched to successful smoke 20261101-512; runtime bindings required.
: "${HCCL_BASE_PORT:?Set HCCL_BASE_PORT from current discovery/allocation}"
: "${HTTP_PORT:?Set HTTP_PORT from current discovery/allocation}"
: "${KV_PORT:?Set KV_PORT from current discovery/allocation}"
: "${LOCAL_IP:?Set LOCAL_IP from current discovery/allocation}"
: "${NIC_NAME:?Set NIC_NAME from current discovery/allocation}"
: "${RPC_PORT:?Set RPC_PORT from current discovery/allocation}"
: "${RUN_DIR:?Set RUN_DIR from current discovery/allocation}"
set -e
unset CPLUS_INCLUDE_PATH CPATH C_INCLUDE_PATH
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export HCCL_OP_EXPANSION_MODE=AIV
export HCCL_BUFFSIZE=1024
export VLLM_USE_V2_MODEL_RUNNER=0
export ASCEND_LOCAL_COMM_RES='{"version":"1.3"}'
export HCCL_ALGO=level0:fullmesh
export VLLM_USE_FASTOKENS=1
export VLLM_USE_RUST_FRONTEND=1
export VLLM_SERVER_DEV_MODE=1
export HCCL_IF_IP="$LOCAL_IP"
export VLLM_HOST_IP="$LOCAL_IP"
export GLOO_SOCKET_IFNAME="$NIC_NAME"
export TP_SOCKET_IFNAME="$NIC_NAME"
export HCCL_SOCKET_IFNAME="$NIC_NAME"
export HCCL_IF_BASE_PORT="$HCCL_BASE_PORT"
MODEL_PATH="${MODEL_PATH:-/mnt/share/w00936111/GLM-5.3-Flash-W8A8-MXFP8-0918}"
mkdir -p "$RUN_DIR/logs/profiler"
cd "$RUN_DIR"
exec vllm serve ''"${MODEL_PATH}"'' \
  --api-server-count 1 \
  --data-parallel-size 8 \
  --tensor-parallel-size 1 \
  --enable-expert-parallel \
  --seed 1024 \
  --safetensors-load-strategy prefetch \
  --kv-cache-dtype fp8 \
  --attention_config.indexer_kv_dtype fp8 \
  --max-num-seqs 30 \
  --enable-prefix-caching \
  --max-model-len 529408 \
  --max-num-batched-tokens 180 \
  --trust-remote-code \
  --quantization ascend \
  --tool-call-parser glm47 \
  --enable-auto-tool-choice \
  --reasoning-parser glm47 \
  --limit-mm-per-prompt '{"image": 1, "video": 0}' \
  --gpu-memory-utilization 0.92 \
  --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY"}' \
  --speculative-config '{"num_speculative_tokens": 5, "method": "deepseek_mtp", "enforce_eager": false}' \
  --additional-config '{"multistream_overlap_shared_expert": false, "recompute_scheduler_enable": true, "enable_fused_mc2": 1}' \
  --profiler-config '{"profiler": "torch", "torch_profiler_dir": "./logs/profiler", "torch_profiler_with_stack": false, "torch_profiler_record_shapes": false}' \
  --host ''"${LOCAL_IP}"'' \
  --port ''"${HTTP_PORT}"'' \
  --served-model-name glm \
  --device-ids 0,1,2,3,4,5,6,7 \
  --data-parallel-rpc-port ''"${RPC_PORT}"'' \
  --data-parallel-address ''"${LOCAL_IP}"'' \
  --kv-transfer-config '{"kv_connector": "MooncakeConnectorV1", "kv_role": "kv_consumer", "kv_port": "'"${KV_PORT}"'", "engine_id": "glm-double-d", "kv_connector_extra_config": {"ascend_local_comm_res_path": "/etc/hixlep", "prefill": {"dp_size": 4, "tp_size": 2}, "decode": {"dp_size": 8, "tp_size": 1}}}'
