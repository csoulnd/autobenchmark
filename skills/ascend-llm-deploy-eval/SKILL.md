---
name: ascend-llm-deploy-eval
description: 为昇腾一体机上的 vLLM-Ascend 模型部署和 AISBench 精度、性能测评规划任务、选择验证配方并收集证据。
---

当前支持 Agent 驱动的信息收集、任务设计与迁移交接；五阶段执行脚本仍为工程骨架，不能用于真实部署或宣称测评完成。

## 新会话入口

先阅读 [会话信息收集与交接](references/intake-handoff.md)。先读取用户提供的交接文件和只读查询环境，再一次性询问无法推导的关键字段；已有明确授权和偏好直接复用。迁移机器时保留测试目标，重新核实主机、容器、卡号、网络、端点配置、权重、版本、端口和路径，不复用旧机器的资源就绪结论。

以 [候选交接示例](references/handoff.example.json) 为起点保存严格 JSON；未知值保持 null，并列入 unresolved，不使用貌似可执行的猜测值。该文件是会话交接契约，不是五阶段脚本的执行输入，不能通过仍拒绝所有输入的 job_spec.schema.json 校验。只有信息齐全、现场预检和真实 PD 冒烟都通过后，才可将对应阶段记录为通过。

本次 DSV4 的经验边界见 [DSV4 候选案例](references/dsv4-candidate.md)。用户要求落地时，Agent 可在已授权范围内使用现有工具逐步执行并留证；不要调用占位脚本冒充执行，也不要把交接文件状态当成验证结果。

脚本相对于本 Skill 根目录定位，运行产物使用显式绝对路径。
五个入口依次为 scripts/plan_run.py、preflight.py、deploy.py、evaluate.py、finalize.py。
计划前由 Agent 通过询问和环境查询补齐必要信息，已有信息直接复用。当前由 Agent 生成候选计划并核对字段；plan_run 尚未实现，不能承担计划校验。

保留五脚本职责：plan_run 生成计划；preflight 检查环境、资源和文件；deploy 拉起服务、等待就绪并执行单条真实推理冒烟；evaluate 执行性能测试并收集结果；finalize 汇总、归档并按约定清理。

按 plan - test 模式由 Agent 驱动执行，正常路径沿五入口顺序推进。脚本折叠阶段内的连续操作以减少工具调用和会话轮次；复杂异常返回状态、日志和证据，由 Agent 判断检查、调整或重试。记录关键变更，超出确认范围时询问用户。

正常完成或中止均进入 finalize，清理仅限本任务资源且应幂等。Agent 调用不具有语言级 finally 的同等保证，中断恢复机制尚待实现。记录阶段与总耗时、工具调用次数、会话轮次，区分流程时延和推理性能指标。

首版假设权重、镜像、工具已准备且部署无异常，聚焦固定场景性能测试。AISBench 运行位置沿用手工验证环境。先手工验证，再由 Agent 执行并提取轨迹，人工调整后以强弱 Agent / Model 组合复现，再组织 Reference。

规划时查阅 references/compatibility/ 和 references/deployment-recipes/；测评时查阅 references/aisbench-datasets/；诊断时查阅 references/troubleshooting/。
当前这些目录尚无已验证配方，不能将占位内容当作已支持能力。

执行以确认的结构化计划为依据，具体交接字段根据轨迹确定。开发验证可使用明确标记为候选的场景配置，不得宣称已验证；审批哈希与生产门禁机制留待后续设计。deploy 负责真实冒烟测试；evaluate 必须核验冒烟证据。性能结论需要 NPU 独占性和条件快照。仅清理本次运行登记的资源，禁止自动 docker pull、特权容器及任意生成的 Shell 命令。
