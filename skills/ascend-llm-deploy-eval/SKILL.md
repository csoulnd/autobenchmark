---
name: ascend-llm-deploy-eval
description: 为昇腾一体机上的 vLLM-Ascend 模型部署和 AISBench 精度、性能测评规划任务、选择验证配方并收集证据。
---

当前为工程骨架，不能用于真实部署或宣称测评完成。

脚本相对于本 Skill 根目录定位，运行产物使用显式绝对路径。
五个入口依次为 scripts/plan_run.py、preflight.py、deploy.py、evaluate.py、finalize.py。
计划前由 Agent 通过多轮询问和环境查询补齐必要信息，已有信息直接复用。信息齐备后调用 plan_run 校验并生成结构化计划。

保留五脚本职责：plan_run 生成计划；preflight 检查环境、资源和文件；deploy 拉起服务、等待就绪并执行单条真实推理冒烟；evaluate 执行性能测试并收集结果；finalize 汇总、归档并按约定清理。

按 plan - test 模式由 Agent 驱动执行，正常路径沿五入口顺序推进。脚本折叠阶段内的连续操作以减少工具调用和会话轮次；复杂异常返回状态、日志和证据，由 Agent 判断检查、调整或重试。记录关键变更，超出确认范围时询问用户。

正常完成或中止均进入 finalize，清理仅限本任务资源且应幂等。Agent 调用不具有语言级 finally 的同等保证，中断恢复机制尚待实现。记录阶段与总耗时、工具调用次数、会话轮次，区分流程时延和推理性能指标。

首版假设权重、镜像、工具已准备且部署无异常，聚焦固定场景性能测试。AISBench 运行位置沿用手工验证环境。先手工验证，再由 Agent 执行并提取轨迹，人工调整后以强弱 Agent / Model 组合复现，再组织 Reference。

规划时查阅 references/compatibility/ 和 references/deployment-recipes/；测评时查阅 references/aisbench-datasets/；诊断时查阅 references/troubleshooting/。
当前这些目录尚无已验证配方，不能将占位内容当作已支持能力。

执行以确认的结构化计划为依据，具体交接字段根据轨迹确定。开发验证可使用明确标记为候选的场景配置，不得宣称已验证；审批哈希与生产门禁机制留待后续设计。deploy 负责真实冒烟测试；evaluate 必须核验冒烟证据。性能结论需要 NPU 独占性和条件快照。仅清理本次运行登记的资源，禁止自动 docker pull、特权容器及任意生成的 Shell 命令。
