#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit $?
mkdir -p "$SCRIPT_DIR/logs" || exit $?
exec > >(tee -a "$SCRIPT_DIR/logs/d.log") 2>&1
source "$SCRIPT_DIR/env.sh" || exit $?
export VLLM_RPC_TIMEOUT=3600000
export GLOO_SOCKET_IFNAME=data0.3001
export TP_SOCKET_IFNAME=data0.3001
export HCCL_SOCKET_IFNAME=data0.3001
export HCCL_CONNECT_TIMEOUT=1200
export HCCL_DETERMINISTIC=true
export HCCL_OP_EXPANSION_MODE=CCU_SCHED
export ASCEND_LOCAL_COMM_RES='{"version":"1.3"}'
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=10
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export VLLM_VERSION=0.30.0
export HCCL_ALGO=level0:fullmesh
aicpu_headers=/usr/local/Ascend/cann-9.2.0/tools/hcc/aarch64-target-linux-gnu/include/c++/14.3.0
export CPLUS_INCLUDE_PATH="$aicpu_headers:$aicpu_headers/aarch64-target-linux-gnu:$aicpu_headers/backward"
export VLLM_USE_V2_MODEL_RUNNER=1
export VLLM_HOST_IP=172.27.8.20
export HCCL_IF_IP=172.27.8.20
export HCCL_BUFFSIZE=1600
export VLLM_USE_FASTOKENS=0
vllm serve /mnt/share/weight/DeepSeek-V4.1-Flash-1017 \
  --served-model-name deepseek-v41-a5-1005-real-1p1d \
  --host 0.0.0.0 \
  --port 8467 \
  --api-server-count 8 \
  --renderer-num-workers 8 \
  --data-parallel-size 8 \
  --data-parallel-rpc-port 16972 \
  --tensor-parallel-size 1 \
  --enable-expert-parallel \
  --enable-ep-weight-filter \
  --max-model-len 1048576 \
  --max-num-batched-tokens 1024 \
  --max-num-seqs 64 \
  --block-size 128 \
  --enable-prefix-caching \
  --model-loader-extra-config '{"enable_multithread_load":true,"num_threads":128}' \
  --trust-remote-code \
  --engram-config '{"cpu_offload":true,"dp_shared_memory":true}' \
  --tokenizer-mode deepseek_v41 \
  --reasoning-parser deepseek_v41 \
  --tool-call-parser deepseek_v41 \
  --enable-auto-tool-choice \
  --gpu-memory-utilization 0.93 \
  --quantization deepseek_v4_fp8 \
  --async-scheduling \
  --speculative-config '{"method":"dspark","num_speculative_tokens":5,"enforce_eager":false}' \
  --compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY"}' \
  --kv-transfer-config '{"kv_connector":"MooncakeHybridConnector","kv_role":"kv_consumer","kv_port":21870,"engine_id":"dsv41-20-d","kv_connector_extra_config":{"prefill":{"dp_size":8,"tp_size":1},"decode":{"dp_size":8,"tp_size":1}}}' \
  --additional-config '{"multistream_engram_overlap":true,"enable_cpu_binding":true,"multistream_overlap_shared_expert":true,"multistream_dsv4_dsa_overlap":true,"enable_fused_mc2":0,"enable_force_eplb":false,"scheduler_config":{"recompute_scheduler_enable":true},"combine_quant_mode":4}' \
  --profiler-config '{"profiler":"torch","torch_profiler_dir":"./dsv4_profile","torch_profiler_with_stack":false}'
