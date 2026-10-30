#!/bin/bash
# Prefill-0 @ 25  cards 0,1,2,3  HTTP:9000
unset ftp_proxy
unset https_proxy
unset http_proxy
unset HCCL_INTRA_ROCE_ENABLE
source /root/.bashrc
source "$(dirname "$(readlink -f "$0")")/env.sh"
source /usr/local/Ascend/ascend-toolkit/set_env.sh 2>/dev/null || true
source /usr/local/Ascend/nnal/atb/set_env.sh 2>/dev/null || true

nic_name=$NIC
local_ip=$HOST_IP
export HCCL_IF_IP=$local_ip
export GLOO_SOCKET_IFNAME=$nic_name
export TP_SOCKET_IFNAME=$nic_name
export HCCL_SOCKET_IFNAME=$nic_name

export HCCL_ALGO=level0:fullmesh
export VLLM_RPC_TIMEOUT=3600000
export VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS=30000
export HCCL_EXEC_TIMEOUT=2040
export HCCL_CONNECT_TIMEOUT=1200
export HCCL_BUFFSIZE=2048
export HCCL_IF_BASE_PORT=60000
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
export ASCEND_LOCAL_COMM_RES='{"version":"1.3"}'
export ASCEND_LOCAL_COMM_RES_PATH=/etc/hixlep/

export OMP_PROC_BIND=false
export OMP_NUM_THREADS=10
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export TASK_QUEUE_ENABLE=1
export VLLM_USE_V2_MODEL_RUNNER=1
export VLLM_USE_FASTOKENS=1
unset ASCEND_RT_VISIBLE_DEVICES ASCEND_VISIBLE_DEVICES
export VLLM_ASCEND_ENABLE_FLASHCOMM1=1
export LD_PRELOAD=/usr/local/Ascend/ascend-toolkit/latest/lib64/libopapi_nn.so

vllm serve "$MODEL_PATH" \
  --device-ids 0,1,2,3 \
  --host 0.0.0.0 \
  --port 9000 \
  --data-parallel-size 2 \
  --data-parallel-address $HOST_IP \
  --data-parallel-rpc-port 12321 \
  --tensor-parallel-size 2 \
  --max_model_len 1048576 \
  --max-num-batched-tokens 8192 \
  --served-model-name dsv \
  --gpu-memory-utilization 0.90 \
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
  --profiler-config '{"profiler":"torch","torch_profiler_dir":"/tmp/dsv4-profiler", "torch_profiler_with_stack": false}' \
  --enable-prefix-caching \
  --enforce-eager \
  --no-disable-hybrid-kv-cache-manager \
  --kv-cache-dtype fp8 \
  --attention_config.indexer_kv_dtype fp8 \
  --speculative-config '{"method":"dspark","num_speculative_tokens":7,"enforce_eager":true}' \
  --kv-transfer-config \
  '{"kv_connector": "MooncakeHybridConnector",
  "kv_role": "kv_producer",
  "kv_port": "36010",
  "engine_id": "p0",
  "kv_connector_extra_config": {
            "ascend_local_comm_res_path": "/etc/hixlep",
            "prefill": {
                    "dp_size": 2,
                    "tp_size": 2
             },
             "decode": {
                    "dp_size": 4,
                    "tp_size": 1
             }
      }
  }' \
  --additional_config '{"enable_cpu_binding": "True","multistream_overlap_shared_expert": true}' \
  2>&1 | tee "$LOG_DIR/p0_25_9000.log"


