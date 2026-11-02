---
name: ascend-llm-deploy-eval
description: 以 job_spec 引导昇腾模型部署与性能测试，将自然语言需求规范化并完成现场预检，再执行部署、冒烟、测试和分级收尾。支持多模型及跨服务器整组任务，每个执行器内部串行；不包含精度、多P/D拓扑或复杂自动恢复。
---

## 工作流程

用户描述服务器、部署和测试需求，Agent负责整理为job_spec v3，不要求用户理解Schema或先拆分case。只询问实际缺项；具体歧义或能力缺口在承诺执行前说明。用户指定值优先，不擅自降低负载或改变部署参数。预检、清理及实际提交后的监控按本Skill执行，无需用户重复授权。

按当前阶段读取对应文档：

| 阶段 | 指引 | 完成条件 |
|---|---|---|
| 收集需求 | [信息收集](references/intake-handoff.md) | 服务器、部署来源及测试目标明确 |
| 多模型/部署/case规划（按需） | [多任务规划](references/multi-task-planning.md) | 对应关系、资源分组及依赖明确 |
| 规范化与现场预检 | [配置与绑定](references/job-spec-review.md)、[容器基线](references/container-baseline.md) | 完成命令审阅、现场绑定与检查，冻结可执行计划 |
| 部署、测试、释放 | [生命周期](references/service-lifecycle.md) | 每个subtask执行deploy → evaluate → finalize，核验结果与资源释放 |
| 多任务自动衔接（按需） | [整组执行](references/group-execution.md) | 独立服务器任务并行，后继仅在前置释放核验后启动 |
| Agent实际提交与跟踪 | [任务监控](references/task-monitoring.md) | 核验脱离SSH运行，建立监控或明确说明不可用 |

本地或远程脚本仅作为输入来源；提取并审阅命令，不把源脚本路径当执行依赖，不照搬旧IP、网卡、端口和权重位置。未知启动配置需有人值守审阅，不自动完整转译任意shell脚本。

## 执行入口

参考[任务示例](examples/job_spec.serial.json)及[现场绑定示例](examples/bindings.example.json)填写实际需求；示例负载不构成执行授权。规划可在本地完成，完整任务目录上传到Linux协调端，同版本Skill包上传各执行节点，现场绑定在对应节点完成。

```sh
python3 scripts/plan_run.py --job-spec /input/job_spec.json --run-dir /work/JOB_ID
python3 /work/JOB_ID/skill-snapshot/scripts/preflight.py --run-dir /work/JOB_ID --bindings /input/bindings.json
bash /work/JOB_ID/run.sh
# 独立收尾入口，仅在身份及执行状态已核验时使用：
python3 /work/JOB_ID/skill-snapshot/scripts/finalize.py --run-dir /work/JOB_ID
```

plan_run冻结需求、默认值、顺序及代码快照；draft或未决目标不能执行。preflight完成绑定并生成resolved及启动脚本，绑定完成前run.sh拒绝启动。新默认不修改已冻结快照。后台提交方式见任务监控；整组提交见整组执行，不提前启动其子任务。

## 必须保持的约束

- 只操作已核验归属的本任务资源，保留共享镜像、权重和历史证据；未知身份或清理未核验时不得盲目复用或重放请求。
- 服务身份与case负载分离；全部节点健康且正式入口冒烟通过，才可认定整套服务READY。
- 测量结果和释放结果分别核验；测量通过不能覆盖清理失败，缺少证据不能报告成功。
- 监控只读，不代替执行器推进任务或自动修复。设计讨论、审阅及用户手动执行不自动创建监控。

## 当前能力与产物

支持vllm serve混部、一个P/一个D/一个proxy的单机或双机PD；job_spec内sub_tasks串行，跨任务整组编排按服务器资源隔离。不支持精度、多P/D、phase并行屏障、复杂中断恢复或旧recipe。

性能适配器及必要数据在assets/aisbench-prefix，PD代理及许可证在assets/pd-proxy。配置存储仅有事件埋点，无配置库、版本检索或自动选配；事件定义见生命周期。

保留计划、现场绑定、代码与启动脚本快照、阶段/状态日志、原始结果及释放记录。本地产物使用D:/autobenchmark-local/，真实连接信息与任务产物均在仓库外；仓库示例只用占位资源，docs只放设计与工程计划。自动流程的归档要求不强加给手动操作。
