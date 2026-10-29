# AutoBenchmark

基于 Skill + Script + Reference 的昇腾模型部署与 AISBench 测评框架。

当前为基础骨架：五个脚本提供统一 JSON 返回和帮助信息，尚未实现真实部署、审批、测评或资源清理。未实现阶段返回 BLOCKED 和退出码 2，不会产生虚假的成功结果。

## 目录
- `skills/ascend-llm-deploy-eval/`：可独立复制的 Skill、脚本、适配器和初始 Schema。
- `docs/design.md`：当前有效设计及原始方案历史参考。
- `docs/decisions.md`：实施边界与待确认事项。
- `tests/`：单元、集成、端到端测试。

## 开发
Python 3.10+，骨架仅依赖标准库。

```sh
python -m unittest discover -s tests/unit -v
python skills/ascend-llm-deploy-eval/scripts/plan_run.py --help
```

所有入口要求显式绝对运行目录，例如 `--run-dir /var/lib/benchmark-agent/runs/demo`。当前仅输出结构化阻止信息，不创建运行产物。后续按照 docs/decisions.md 实现 Agent 驱动的 plan - test 流程、阶段检查、证据记录及任务收尾。
