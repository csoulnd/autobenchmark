# 任务配置与现场绑定

当前主格式是 [job_spec v3](../schemas/job_spec.schema.json)，参考 [串行任务示例](../examples/job_spec.serial.json)。只接受 v3；旧格式会被拒绝，不自动迁移。

## 两种记录的职责

- job_spec：标准部署意图、命令及环境、模型标识、case 关联与顺序、执行策略。用户脚本来源路径不进入执行依赖；机器绑定值使用占位符。case 的顺序就是执行顺序，不自动重排或扩展组合。
- bindings / resolved：Agent 在有人值守阶段取得的实际位置与环境。bindings 是探测前所需的已知位置和网络选择，resolved 是预检后冻结的实际值，不属于配置库。模型实际路径、网卡/IP、分配端口、工具位置、任务目录与生成脚本路径在此绑定。

配置存储本轮只做事件埋点，不引入部署配置库、版本体系或自动检索。当前任务 JSON、执行代码快照和运行证据是完成任务所必需的产物，仍然保存。

## job_spec 字段

| 字段 | 用途 |
|---|---|
| job_id / target.host | 整组任务标识、目标 SSH 主机；实际任务目录由命令行指定 |
| deployments[].id | 部署配置标识，供 case 引用 |
| deployments[].image / model | 镜像引用、模型逻辑标识、服务名和上下文上限；实际镜像 ID 在预检解析 |
| deployments[].npu_ids / container | 设备分配及容器共享内存、特权要求 |
| deployments[].commands | 审阅后的 argv、env 和 bootstrap 环境初始化内容；可以包含多个服务入口 |
| deployments[].ports | 端口逻辑名称及所需连续范围宽度，不存固定端口号 |
| deployments[].service | 健康检查、服务入口、缓存重置及前缀指标端口的模板 |
| deployments[].prefill_dp | 当前前缀工具的预热并行参数，从部署内容提取 |
| cases[] | 每个 case 的 id、deployment_id、输入/输出长度、并发和前缀比例，以及可选覆盖值 |
| execution / cleanup | 冒烟、重试与超时；case 与任务的释放策略 |
| state / unresolved | draft 供信息整理；ready 且无未决任务目标才生成执行计划 |

plan_run 补齐请求数=并发×4、prefix_num=1、seed=1、request_rate=0、warmup/reset_cache=true，保留用户明确覆盖值。单轮执行；需要重复测量时显式组织不同 case ID，不暗中重复。

## 从用户脚本到命令

Agent 读取本地/远程脚本或粘贴内容，识别真正的启动参数、环境设置和旧机器绑定值。保留已经确认的部署调优参数，将旧权重位置、IP、NIC、端口、输出目录改成明确占位符。不要对任意脚本做全局字符串替换，也不要保留与启动无关的破坏性操作。

argv 是参数数组，结构化 JSON 参数用 `{"json": {...}}` 表达，由生成器序列化。bootstrap 只用于已审阅的环境初始化，动态占位符由生成器按 shell 参数转义；不要在占位符外再手工加引号。未知占位符会阻塞生成。

常用绑定：`{{model.path}}`、`{{model.served_name}}`、`{{network.ip}}`、`{{network.interface}}`、`{{ports.NAME}}`、`{{paths.NAME}}`、`{{run_dir}}`、`{{task_dir}}`。env 中普通 shell `$VAR` 不自动展开；需要环境继承/展开的表达式放在已审阅 bootstrap 中。

## bindings 与动态发现

参考 [bindings 示例](../examples/bindings.example.json)，由 Agent 收集并填写，不作为首次对话用户必填清单：

- model_paths：模型逻辑标识到现场权重目录的映射。
- network_interface：有多个网络候选时填写已经核验的通信网卡；IP 仍从当前主机查询。
- mounts：本任务需要的驱动、通信配置等挂载。生成器补齐任务目录和模型挂载。
- paths：初始化脚本、通信配置等已核验位置。框架代理程序的路径由生成器补齐。

AISBench 位置通过选定镜像内的无设备、无网络临时探测容器动态获取；探测容器退出或异常后核验清理。工具布局不兼容时明确阻塞。端口按逻辑名称与范围动态分配，真正启动前再次检查占用；预检不是资源永久预留。

生成后的 resolved-task.json 关联每个部署的 resolved.json、部署摘要与启动脚本哈希。改变绑定需要新任务目录，不覆盖已冻结的执行内容。job_spec 不承担配置检索或存储服务职责。
