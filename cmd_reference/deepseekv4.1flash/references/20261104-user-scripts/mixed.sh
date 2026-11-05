#!/bin/bash
set -e

export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
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

aicpu_headers=/usr/local/Ascend/cann-9.2.0/tools/hcc/aarch64-target-linux-gnu/include/c++/14.3.0
export CPLUS_INCLUDE_PATH="$aicpu_headers:$aicpu_headers/aarch64-target-linux-gnu:$aicpu_headers/backward"
export VLLM_USE_V2_MODEL_RUNNER=1
export VLLM_HOST_IP=172.27.9.212
export HCCL_IF_IP=172.27.9.212
export HCCL_BUFFSIZE=1600

vllm serve /mnt/share/weight/DeepSeek-V4.1-Flash \
  --served-model-name deepseek-v41-a5-1005-real-1p1d \
  --host 0.0.0.0 \
  --port 8568 \
  --api-server-count 1 \
  --data-parallel-size 8 \
  --data-parallel-rpc-port 17972 \
  --tensor-parallel-size 1 \
  --enable-expert-parallel \
  --enable-ep-weight-filter \
  --seed 1024 \
  --max-model-len 1048576 \
  --max-num-batched-tokens 4096 \
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
  --gpu-memory-utilization 0.90 \
  --quantization deepseek_v4_fp8 \
  --async-scheduling \
  --speculative-config '{"method":"dspark","num_speculative_tokens":5,"enforce_eager":false}' \
  --compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY"}' \
  --additional-config '{"multistream_engram_overlap":true,"enable_cpu_binding":true,"multistream_overlap_shared_expert":true,"multistream_dsv4_dsa_overlap":true,"enable_fused_mc2":0,"enable_force_eplb":false}'
