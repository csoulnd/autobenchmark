# AutoBenchmark

以 job_spec 引导有人值守的信息收集和现场预检，再自动串行执行部署、性能测试与收尾。用户自然语言描述服务器、部署和测试要求，由 Agent 转换成标准 case。

- [Skill 入口](skills/ascend-llm-deploy-eval/SKILL.md)：信息收集、五阶段执行方式和边界。
- [任务示例](skills/ascend-llm-deploy-eval/examples/job_spec.serial.json)：v3 部署与 case 关联、启动命令模板；示例不是执行授权。
- [现场绑定示例](skills/ascend-llm-deploy-eval/examples/bindings.example.json)：模型位置、挂载及环境路径。
- [生命周期](skills/ascend-llm-deploy-eval/references/service-lifecycle.md)：服务状态、独占锁、按 case 重试和分级释放。
- `docs/` 只存设计与整体工程计划；`tests/` 存可复用检查。本地产物保存在仓库外，本机为 `D:/autobenchmark-local/`。

Python 3.10+；规划依赖 jsonschema。现场执行需要 Linux、Docker、curl 和 npu-smi；AISBench 从镜像动态发现，前缀工具随 Skill 分发。

```sh
python -m pip install -r skills/ascend-llm-deploy-eval/requirements.txt
python -m unittest discover -s tests/unit -v
python skills/ascend-llm-deploy-eval/scripts/plan_run.py --job-spec /input/job_spec.json --run-dir /work/JOB_ID
# Agent 将完整任务目录上传到目标机后，在目标机执行：
python3 /work/JOB_ID/skill-snapshot/scripts/preflight.py --run-dir /work/JOB_ID --bindings /input/bindings.json
bash /work/JOB_ID/run.sh
```

plan_run 生成串行入口；preflight 动态绑定 IP、网卡、端口、路径并生成启动脚本。随后每个 case 经过 deploy → evaluate → finalize：同部署的有效服务默认复用，切换部署停止旧容器，任务结束默认停止本任务服务和容器。默认一次 curl 冒烟，异常最多额外重试3次；安全条件不满足时停止继续测试并收尾。

配置存储暂只有标准化、现场绑定、部署验证和 case 结束事件，不实现配置库或检索。任意脚本转为规范命令仍需 Agent 审阅；没有自动 SSH 上传、精度、并行调度或复杂中断恢复。仅接受 job_spec v3，不提供旧格式兼容。

当前串行流程通过 Linux 40 项检查，含模拟服务的生成入口集成测试；真实镜像工具探测和启动脚本语法验证通过。现场 NPU 占用使新流程的真实推理压测尚未执行，不能用历史单 case 成功代替新流程验证。完整 Agent 与强弱模型复现仍在后续阶段。
