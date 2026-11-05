#!/usr/bin/env bash
# Deployment verified by job 20261103-003 on 2026-11-03; runtime bindings required.
: "${HCCL_BASE_PORT:?Set HCCL_BASE_PORT from current discovery/allocation}"
: "${HTTP_PORT:?Set HTTP_PORT from current discovery/allocation}"
: "${KV_PORT:?Set KV_PORT from current discovery/allocation}"
: "${LOCAL_IP:?Set LOCAL_IP from current discovery/allocation}"
: "${NIC_NAME:?Set NIC_NAME from current discovery/allocation}"
: "${RPC_PORT:?Set RPC_PORT from current discovery/allocation}"
: "${RUN_DIR:?Set RUN_DIR from current discovery/allocation}"

set -e
unset ftp_proxy
unset https_proxy
unset http_proxy
unset HCCL_INTRA_ROCE_ENABLE
source /root/.bashrc
source /usr/local/Ascend/ascend-toolkit/set_env.sh 2>/dev/null || true
source /usr/local/Ascend/nnal/atb/set_env.sh 2>/dev/null || true
export HCCL_ALGO=level0:fullmesh
export VLLM_RPC_TIMEOUT=3600000
export VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS=30000
export HCCL_EXEC_TIMEOUT=2040
export HCCL_CONNECT_TIMEOUT=1200
export HCCL_BUFFSIZE=2048
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
export ASCEND_LOCAL_COMM_RES='{"version":"1.3"}'
export ASCEND_LOCAL_COMM_RES_PATH=/etc/hixlep
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=10
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export TASK_QUEUE_ENABLE=1
export VLLM_USE_V2_MODEL_RUNNER=1
export VLLM_USE_FASTOKENS=1
unset ASCEND_RT_VISIBLE_DEVICES
unset ASCEND_VISIBLE_DEVICES
export VLLM_ASCEND_ENABLE_FLASHCOMM1=1
export LD_PRELOAD=/usr/local/Ascend/ascend-toolkit/latest/lib64/libopapi_nn.so
export VLLM_SERVER_DEV_MODE=1
export HCCL_IF_IP="$LOCAL_IP"
export VLLM_HOST_IP="$LOCAL_IP"
export GLOO_SOCKET_IFNAME="$NIC_NAME"
export TP_SOCKET_IFNAME="$NIC_NAME"
export HCCL_SOCKET_IFNAME="$NIC_NAME"
export HCCL_IF_BASE_PORT="$HCCL_BASE_PORT"
MODEL_PATH="${MODEL_PATH:-/mnt/weight/DeepSeek-V4-Flash-DSpark}"
mkdir -p "$RUN_DIR/logs/profiler"
cd "$RUN_DIR"

exec vllm serve ''"${MODEL_PATH}"'' \
  --data-parallel-size 4 \
  --tensor-parallel-size 1 \
  --max-model-len 1048576 \
  --max-num-batched-tokens 8192 \
  --gpu-memory-utilization 0.9 \
  --enable-expert-parallel \
  --async-scheduling \
  --max-num-seqs 64 \
  --block-size 32 \
  --api_server_count 1 \
  --tokenizer-mode deepseek_v4 \
  --tool-call-parser deepseek_v4 \
  --enable-auto-tool-choice \
  --reasoning-parser deepseek_v4 \
  --trust-remote-code \
  --profiler-config '{"profiler": "torch", "torch_profiler_dir": "./logs/profiler", "torch_profiler_with_stack": false}' \
  --enable-prefix-caching \
  --enforce-eager \
  --no-disable-hybrid-kv-cache-manager \
  --kv-cache-dtype fp8 \
  --attention_config.indexer_kv_dtype fp8 \
  --speculative-config '{"method": "dspark", "num_speculative_tokens": 7, "enforce_eager": true}' \
  --additional_config '{"enable_cpu_binding": "True", "multistream_overlap_shared_expert": true}' \
  --host ''"${LOCAL_IP}"'' \
  --port ''"${HTTP_PORT}"'' \
  --served-model-name dsv \
  --device-ids 0,1,2,3 \
  --data-parallel-rpc-port ''"${RPC_PORT}"'' \
  --data-parallel-address ''"${LOCAL_IP}"'' \
  --kv-transfer-config '{"kv_connector": "MooncakeHybridConnector", "kv_role": "kv_producer", "kv_port": "'"${KV_PORT}"'", "engine_id": "dsv-pd-p", "kv_connector_extra_config": {"ascend_local_comm_res_path": "/etc/hixlep", "prefill": {"dp_size": 4, "tp_size": 1}, "decode": {"dp_size": 4, "tp_size": 1}}}'
