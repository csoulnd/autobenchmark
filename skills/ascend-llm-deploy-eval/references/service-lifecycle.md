# 串行 case 与服务生命周期

## 准备与循环

plan_run 固定 sub_task 顺序并生成 run.sh；preflight 在有人值守时完成现场绑定。run.sh 开始后，每个 sub_task 调用 deploy → evaluate → finalize。deploy 每次检查服务状态；调用该阶段不代表必须重新部署。

协调端在 services/<deployment_id>/service-state.json 保存整套服务状态；节点各容器目录的 run_state.json 保存本地服务状态，执行入口节点在其中的 cases[sub_task_id] 单独记录 case 状态。整组任务状态在 task-state.json，日志与结果按部署、case 和 attempt 分开。

| 状态 | 行为 |
|---|---|
| ABSENT / RELEASED | 检查即时资源后建立服务 |
| DEPLOYING / DEPLOYED | 等待启动与默认冒烟，不重复启动 |
| READY | 核验容器/进程身份与健康检查，匹配则跳过部署和冒烟 |
| TESTING | 当前 case 执行中，不启动另一 case |
| FAILED / UNKNOWN | 保留失败原因，按已实现的有限重试或收尾处理，不盲目复用 |

实例部署摘要只包含部署与绑定内容，不包含并发、请求数等 case 负载。容器归属使用该部署摘要和实际身份核验；case 状态、结果和重试预算独立。服务重启后旧冒烟失效。

## 资源分层

| 资源 | 当前策略 |
|---|---|
| case 客户端与进程组 | 测试结束/异常时结束，核验无活动成员；清理不明阻止下一 case |
| case 临时配置和数据链接 | 只解除本 attempt 创建且归属明确的链接，结果与数据证据保留 |
| 前缀缓存 | 首次及每个要求隔离的 case 预热前实际重置并核验；case 收尾标记 NEEDS_RESET，避免重复清理 |
| 相同部署的服务 | 连续 case 默认保留有效 READY 实例 |
| 部署切换 | 当前串行实现停止旧部署容器，使用下一部署的独立容器；不做跨部署容器共享 |
| 任务结束 | 按 task_end 处理所有登记部署；一个释放失败不跳过其他部署，失败单独报告 |

每个部署的容器以任务 job_id 的数字子编号命名。进程组登记在 service-processes.json；客户端身份、释放证据保存在各 attempt 的 client.json / cleanup.json。已完成结果保留，重复任务入口不会重新发送成功/失败终态 case 的请求，仍执行任务收尾。

## 锁、重试和失败

整组循环持有任务锁，各部署操作另持有容器锁。前缀重置、工具配置与负载都在锁内执行。不是并行任务调度器，也不自动抢占其他用户资源。

部署和 case 运行异常默认最多额外重试3次。case 预算按 sub_task_id 分离；显式释放后重新建立服务时记录新的部署尝试批次。重试前核验服务身份、客户端清理及缓存隔离条件。耗尽后当前子任务失败保留；record_only 核验客户端清理和所有节点服务，健康时继续复用，确认退出时释放整套部署后置为 RELEASED，让下一子任务重建。失联、身份不明、健康检查不通过但未确认退出或释放未核验时置 UNKNOWN 并阻塞，不推断失联节点已退出。

遇到客户端清理不明或未知状态，停止相关循环并进入适用的任务收尾。中断后仍为 RUNNING 的 case 不自动恢复，避免重放未知请求。服务与容器停止不删除共享镜像、权重或历史证据。

## 配置存储埋点

logs/config-storage-events.jsonl 记录 task_normalized、bindings_resolved、deployment_verified、case_finished，附任务/部署/case 标识和必要摘要。storage 固定标为 not_implemented；没有配置库写入、版本管理或自动匹配。

## Prefix Cache 清理的执行边界

缓存属于 case 隔离资源，服务可以继续复用。case finalize 标记 NEEDS_RESET；下一次 evaluate 的 case_runner 在预热和正式客户端启动之前调用 cache_reset.reset_instances，首次 case 和每次重试同样执行。任务结束停止服务时不再重复请求重置接口。

- 收集启动配置时，为需要 reset 的每个 vLLM 模型进程设置 instances[].launch.env.VLLM_SERVER_DEV_MODE="1"，模板在 bootstrap 之后导出该环境变量。保留已审阅的 Prefix Caching 参数；不为实现清理而关闭缓存。当前部署示例已为 P/D 模型进程启用该变量。
- 拓扑编译器从模型实例 checks 生成 service.reset_urls，列出全部需清理的模型实例 IP 与动态端口。PD 场景包括 P 和 D，混部列出 mixed 实例。不要默认填 Proxy 端口，也不要套用固定端口号。
- 在本任务独占锁与服务身份核验下，先读取全部实例 /metrics，核验 running/waiting 请求数均为零（含各 DP 标签）。指标缺失、不合法或仍忙则本次尝试失败；空闲快照不等于异步 KV 传输已结束，仍以 reset 返回值为准。
- 逐实例 POST /reset_prefix_cache，不传强制终止运行请求参数。必须 HTTP 成功且 JSON success 严格为 true，才进入预热。false、非 JSON、HTTP 错误或超时均阻止本次测试；记录其余实例结果，复用 case 最多额外3次的重试预算，不新增嵌套重试。
- 每个 attempt 保存 cache-reset.json、空闲指标、原始响应或 HTTP 错误。失败记录不会被后续成功覆盖。404 需核对运行版本与 Dev Mode，不能当成已清理；接口返回空响应的版本需要单独核验适配，不能仅凭 HTTP 200 放行。

此动作只证明各实例本地 Prefix Cache 重置得到确认，不保证全程零命中率，也不声称清除了外部 connector 缓存。当前不自动添加 reset_external 或调整 Hybrid 模型兼容性配置。Dev Mode 只对已授权的本任务测试服务启用。

官方接口参考：[vLLM reset_prefix_cache](https://docs.vllm.ai/en/latest/api/vllm/entrypoints/serve/dev/cache/api_router/)。接口明确区分本地和可选外部缓存，并说明在运行请求或异步传输持有块时可能返回 false。

## 多节点协调

每个节点按 node/container_group 创建本任务容器，独立保存身份、脚本摘要、服务进程和释放证据。协调端通过固定 node_prepare.py / node_rpc.py 发起 JSON 数据请求；实际命令仍在节点本地执行。模型进程先启动并通过健康检查，再启动 proxy，最后从正式入口进行一次 curl 冒烟。全体节点身份在正式测试前后核验，任何节点不明均不能宣称整套服务 READY。

协调端任务锁覆盖串行循环，节点操作使用容器锁；不提供跨协调端分布式调度。节点通信失败或释放失败逐项记录，继续尝试其他登记节点的释放。仅确认全部登记节点完成指定策略后报告任务释放通过。节点日志保留在各自任务目录，协调端保存节点位置与汇总；任务包和节点包由 Agent 上传相同版本。

首次执行将 sub_task 标记 RUNNING 后才调用节点。已完成终态子任务不重放；中断留下 RUNNING 时要求先收尾、诊断后新建任务，不自动恢复。不同 deployment 的容器不共享，切换前停止旧部署全部节点。

预热当前走正常 API 路由，不指定 P 端 DP rank。多 API Server 下，发送 DP 数量的预热请求不保证覆盖每个 DP；校验器会拒绝覆盖不足的 attempt，并使用既定重试预算，不能把请求成功等同于预热完整。尚未实现确定性的逐 DP 预热。短前缀也可能小于模型缓存块粒度，构造比例不保证产生同等实测命中率。
