# 分层部署、可复用 case 与现场绑定

当前只接受 job_spec v3 的拓扑结构，不兼容开发阶段旧平铺字段。参考 examples/job_spec.serial.json 和 examples/bindings.example.json；示例不包含真实服务器、私有路径或镜像摘要。

## 三类定义

- deployments：每项为完整服务拓扑，包含 id、topology、model、runtime、instances、connections、endpoint。
- cases：仅描述负载：输入/输出 token、并发、请求数、前缀目标等，不引用部署。默认请求数并发×4，显式值优先。
- sub_tasks：显式串行执行清单，id、phase_id、deployment_id、case_id、after_case、on_failure。phase_id 默认 pp1，仅为分组标识，执行仍按清单顺序；on_failure 当前仅支持 record_only。一个 case 可以被多个子任务引用；结果用 sub_task ID 隔离。当前不支持 phase 并行屏障。

## deployment

model 存逻辑模型 id 与 served_name。runtime 存共用镜像和容器要求。instances 中每个进程有角色 mixed/prefill/decode/proxy，以及 placement（逻辑 node、devices）、launch（模型 args/env/bootstrap 或内置 proxy adapter）、ports、checks。

同一部署同一节点的实例共用容器。容器按任务和现场配置管理，不以 deployment ID 分配：相同主机、镜像及容器配置复用，预检汇总各部署的设备与模型挂载；不兼容配置另建子编号容器。单机 PD 的 P/D 设备互不重叠，双机 PD 的 P/D 分别放到不同 node。当前 PD 路径只实现一个 P、一个 D 和一个 proxy；混部只有一个 mixed。DP/TP 必须匹配实例设备数。模型参数以实例 launch.args 为唯一来源，max-model-len 在每个模型实例定义，测试必须满足所有相关实例的上限。

connections.kv_transfer 关联 producer/consumer 和 connector；connections.routing 关联 proxy、prefillers、decoders。KV 配置中的 P/D DP/TP 与角色由实例关系生成。endpoint 引用对外服务实例和逻辑端口。禁止在 launch.args 重复填写由编译器管理的 host、port、served-model-name、device-ids、kv-transfer-config。

launch.args 中 true/false 渲染为开关及 no- 开关，数值/字符串为参数值，对象/数组编码为单个 JSON 参数；配置必须经过 Agent 审阅，不能把字符串 shell 当任意可执行命令。bootstrap 保留已审阅的环境加载步骤。当前以 vllm serve 和内置 PD proxy 为执行适配器，不承诺任意服务框架。

## bindings

bindings.nodes 按逻辑 node 记录 host、work_dir、package、model_paths、paths、mounts，可选 network_interface。真实现场信息仅放仓库外。

容器按 [默认容器基线](container-baseline.md) 补齐参数和挂载；bindings.mounts 是按目标路径覆盖/追加的现场配置，省略不代表无挂载。runtime.container 的显式参数覆盖默认值，完整结果写入 resolved 并参与容器复用指纹。源路径不存在时阻塞，不能让 Docker 自动创建空目录代替通信配置文件。

Agent 先将相同版本 Skill 包上传到各节点 package 路径，协调端需要能免密 SSH 到全部节点（包含自身作为节点的情形）。preflight 通过固定节点脚本和 JSON 请求发现环境并生成脚本，不远程执行输入中的 Python 代码。各节点权重、镜像解析、设备、端口与工具均分别检查。

默认不填写 network_interface：从 UP 且有 IPv4 的接口按当前协商速率选唯一最高者，保留 VLAN，排除 bridge/veth 等虚拟接口。通过 ip JSON 与 sysfs/ethtool 获取信息，不按 data0 名称选择。速率未知、并列或多地址需有人核验；网卡速率不代表跨机可达性。ip 命令损坏时尝试系统路径，不修改服务器 PATH 或网络。端口从系统临时客户端端口区间之外动态选择，启动前再检查；这不是永久端口租约。

## 执行产物

plan.json 固定需求和 sub_task 顺序；resolved-cluster.json 保存拓扑编译结果及节点注册信息。节点保存 discovery.json、各容器的 resolved.json、启动脚本和脚本摘要。resolved-1 是内部节点执行产物，不是另一种用户输入格式。归属摘要与实际容器/进程身份一并核验。配置库尚未实现，仅保留事件埋点。

容器归属摘要与服务摘要分离：前者包含任务计划、镜像与容器配置，后者包含各部署命令和绑定。节点任务目录的 container-pools/<容器名>.json 登记实际容器 ID、当前服务目录及删除状态。旧服务释放核验后才能切换登记；协调器锁与容器锁使用不同名称。
