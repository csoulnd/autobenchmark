# 新服务器迁移包

文件位于 `assets/dsv4-migration/`。这是旧现场源码的可迁移快照，未在新机验证，不是镜像或模型分发包。

包含 P/D、代理启动脚本、代理 Python 源码、显式选择源码/备份路径的设备映射修复程序、容器创建脚本，以及 aisbench_auto_tools_prefix 源码和 GSM8K.jsonl 输入。压测工具来源 https://github.com/rayn-zzz/aisbench_auto_tools_prefix ，保留 MIT LICENSE；代理文件保留 Apache-2.0 标记及原始来源注释。工具为现场快照，不声称与当前上游最新提交一致。

新机器仍需准备：昇腾驱动、兼容 CANN/vLLM-Ascend 镜像、Docker、0731 权重及 tokenizer、AISBench 和代理依赖；物理卡 endpoint/rootinfo/route 配置来自新机自身。不要复制旧机器通信配置。容器创建脚本要求显式镜像和容器名，涉及 privileged/host PID，先按 intake 确认其适用性和授权，不自动执行。

复制迁移包到新服务器后，在容器内设置：

```bash
export HOST_IP=<新机通信IP>
export NIC=<对应网卡>
export MODEL_PATH=<容器内权重绝对路径>
export WORK_DIR=<你的工作目录绝对路径>
export PYTHON=python3
```

这些值缺失时 P/D 与代理启动脚本会停止。候选 API 端口仍为9000/9001/9005，卡组0–3/4–7；先与 job_spec 和现场核对。P/D 已启用 prefix caching。profiler 目录暂为容器内 /tmp/dsv4-profiler，正式运行前按任务隔离。

补丁需在目标容器中显式指定实际源码文件及备份目录：

```bash
python3 scripts/apply_npu_mapping_fix.py --source <parallel_state.py绝对路径> --backup-dir <备份目录> --check
# 确认源码兼容且需要修复后，去掉 --check 应用
```

修改压测 config.py 的 DATASET_PATH、WORK_PATH（AISBench项目根）、MODEL_NAME、MODEL_PATH、HOST_IP/HOST_PORT、OUTPUT_DIR、POD_INFO；在压测工具目录内运行。默认配置是占位值，不可直接用于正式测试。执行前验证 shell 管道失败传播与 SSE 错误识别，不能仅凭脚本退出码判断成功；这些工具兼容性修复尚未在本快照完成。

先通过真实 PD 冒烟，再根据 job_spec cases 逐组测试。迁移包没有自动安装依赖、下载权重、创建容器或启动服务的隐式动作；五阶段执行器状态以主 SKILL.md 为准。
