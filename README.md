# AutoBenchmark

当前模型拉起与评测的初版设计见 [设计报告](docs/deployment-evaluation-v1.md)：完整配置包绑定验证环境，common_reference 保存通用检查与排障，不做跨镜像自动匹配。

基于 Skill + Script + Reference 的昇腾模型部署与 AISBench 测评框架。

当前已实现 job_spec 结构化校验和 plan_run 计划生成；真实预检、部署、测评和清理尚未实现。未实现阶段返回 BLOCKED 和退出码 2。

## 目录
- `skills/ascend-llm-deploy-eval/`：可独立复制的 Skill、脚本、适配器和初始 Schema。
- `docs/design.md`：当前有效设计及原始方案历史参考。
- `docs/decisions.md`：实施边界与待确认事项。
- `tests/`：单元、集成、端到端测试。

## 开发
新机器接手或跨会话继续任务，从 `skills/ascend-llm-deploy-eval/SKILL.md` 的新会话入口开始。现已提供信息收集清单、候选交接 JSON 和 DSV4 迁移案例；这些支持 Agent 规划与交接，不代表五阶段执行器已实现，也不是已验证的性能结果。

Python 3.10+；规划校验依赖 Skill 内 requirements.txt 中的 jsonschema。

```sh
python -m pip install -r skills/ascend-llm-deploy-eval/requirements.txt
python -m unittest discover -s tests/unit -v
python skills/ascend-llm-deploy-eval/scripts/plan_run.py --help
```

所有入口要求显式绝对运行目录，例如 `--run-dir /var/lib/benchmark-agent/runs/demo`。plan_run 对完整 ready 配置生成 plan.json；其余阶段仅输出阻止信息。后续按照 docs/decisions.md 实现 Agent 驱动的 plan - test 流程、阶段检查、证据记录及任务收尾。

结构化规划：安装 Skill 内 requirements.txt；以 examples/job_spec.dsv4-migration.json 为起点填写 job_spec，再调用 plan_run.py --job-spec <绝对路径> --run-dir <绝对路径>。draft 返回 BLOCKED 且不生成产物；ready 通过结构及拓扑校验才生成 PLANNED。其余执行阶段仍为占位。
