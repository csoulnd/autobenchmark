# job_spec v2：先按实际任务评估

以 [单 case 示例](../examples/job_spec.single-case.json) 为填写起点，以 [Schema](../schemas/job_spec.schema.json) 校验。示例中的地址和路径仅属于本次实验，不是平台默认值。

当前真实任务是一次前缀性能测量：65536 输入 tokens、1024 输出 tokens、并发 32、64 条正式请求、目标前缀 0.5、一轮。用户提供的请求数独立于并发；1K=1024。沿用已核验工具的 prefix_num=1、seed=1、request_rate=0、prefill_dp=2。工具预热与正式数据分开核验，实测输入可包含模板开销，前缀命中率单独报告。

| 字段 | 来源与职责 |
|---|---|
| job_id / target | 任务编号、SSH 目标、绝对工作目录、容器名、用户选定镜像名称或 ID；新容器与 job_id 同名 |
| model | 用户权重路径、服务名、上下文上限 |
| container | 本任务所需设备和挂载、共享内存、特权要求；从已有启动方式核验，不内置个人路径 |
| deployment.recipe | 值守阶段选择的包内候选目录，含 render.py；按模型与实际软件版本审查 |
| deployment.parameters | 配方特有参数；DSV4 P/D 的网络、拓扑、端口、连接器等，配方负责校验与渲染 |
| benchmark | 用户工具位置、明确的适配器、工具工作路径、预热 DP 和单个 case |
| benchmark.case | 负载、正式请求数、前缀目标、预热、是否 reset_cache、超时；不包含隐式倍数或多轮循环 |
| execution | smoke 默认 default、max_retries 默认 3（首次外）、启动及冒烟超时；plan_run 写入实际默认值 |
| cleanup | after_case 与 task_end 分别选择 keep_service / stop_service / stop_container |
| state / unresolved | draft 供值守收集，ready 且无未决项才进入执行 |

当前 `aisbench_prefix` 适配器要求工具预热并提供前缀指标。其他测试工具需要先适配命令和结果解析，不让用户填写一个当前执行器不支持的类型。其他配方不必采用 P/D；通用脚本只消费配方渲染的命令、健康地址、设备与端口清单。

配置与事实分开：`plan.json` 冻结规格和摘要；`preflight-evidence.json` 记录实际环境；`run_state.json` 记录服务、case 尝试与释放；`results/<case>/attempt-NN/` 保存独立原始证据。改规格使用新 job_id，不覆盖旧计划。首版单 case 不做跨任务服务迁移，也不自动接管现有其他容器。
