# AutoBenchmark

以 job_spec 引导有人值守的信息收集与初步验证，再自动执行单个性能 case。

- [Skill 入口](skills/ascend-llm-deploy-eval/SKILL.md)：工作流程、执行边界和参考资料。
- `skills/ascend-llm-deploy-eval/scripts/`：五阶段入口及共用执行代码。
- `skills/ascend-llm-deploy-eval/assets/`：候选部署配方；通用执行器不绑定镜像、模型或服务器。
- `skills/ascend-llm-deploy-eval/schemas/`、`examples/`：单 case job_spec v2、状态与结果格式、实际参数示例。
- `docs/`：设计、决策与整体工程计划。
- `tests/`：可复用验证。
- 仓库外本地产物目录：本机为 `D:/autobenchmark-local/logs/`，存放日志、报告、证据与旧实现存档，不提交或推送。其他机器选择各自的仓库外目录。

Python 3.10+；规划依赖 jsonschema，运行阶段在目标 Linux 宿主机执行，需要 Docker、curl、npu-smi。测试客户端在本任务容器中执行。

```sh
python -m pip install -r skills/ascend-llm-deploy-eval/requirements.txt
python -m unittest discover -s tests/unit -v
python skills/ascend-llm-deploy-eval/scripts/plan_run.py --job-spec /path/job_spec.json --run-dir /path/YYYYMMDD-NNN
```

后续四阶段同样使用 `--run-dir`。先填写并核对 [单 case 示例](skills/ascend-llm-deploy-eval/examples/job_spec.single-case.json)，不能把示例路径当成其他环境的事实。正式请求数独立配置；默认一次 curl 冒烟，最大重试次数默认 3。服务 READY 时核验身份后跳过 deploy/smoke。性能 case 使用容器级独占锁，结束按明确策略释放。

本轮验证目标为 64K 输入 / 1K 输出、并发 32、64 条正式请求、50% 目标前缀、1 轮。历史六组手工基线与本轮执行器验证分开记录；完整 Agent 与强弱模型复现留待下一阶段。
