---
name: ascend-llm-deploy-eval
description: 以 job_spec 引导昇腾模型部署与性能测试，在有人值守阶段收集权重、镜像、case 和工具并初步验证，随后自动部署、冒烟、执行单 case 和按策略释放。适用于已有候选部署配方的性能验证；不包含精度测试、并行调度或复杂自动恢复。
---

## 工作方式

以 job_spec 为任务事实与执行约定的来源。先在有人值守阶段完成信息收集、任务合理性评估和初步验证，再自动上机执行最小 case。复用已确认事实，不重复询问。某次实验的镜像、模型、机器、拓扑或清理选择不能成为通用限制。

1. 按 [信息收集模板](references/intake-handoff.md) 补齐权重、镜像、case、测试工具及目标环境。能只读查询的事实自行核验，缺失项集中询问。
2. 按 [job_spec 说明](references/job-spec-review.md) 评估任务，选择并检查部署配方，再填写 [v2 单 case 示例](examples/job_spec.single-case.json)。候选配方不是兼容性保证；实际镜像身份与版本在执行时记录。
3. 执行五阶段。每阶段读取同一份冻结计划；未经确认不缩小测试目标。出错保留证据并落实任务清理。

## 五阶段入口

在目标 Linux 宿主机运行，使用绝对工作目录：

```sh
python3 scripts/plan_run.py --job-spec /path/job_spec.json --run-dir /path/YYYYMMDD-NNN
python3 scripts/preflight.py --run-dir /path/YYYYMMDD-NNN
python3 scripts/deploy.py --run-dir /path/YYYYMMDD-NNN
python3 scripts/evaluate.py --run-dir /path/YYYYMMDD-NNN
python3 scripts/finalize.py --run-dir /path/YYYYMMDD-NNN
```

- **plan_run**：校验单 case、填默认值、冻结计划并保存 Skill 快照。draft/未决项阻塞自动执行。
- **preflight**：核验镜像、挂载、权重、工具、设备、网络及端口。有效 READY 服务核验归属后复用，不因本任务自身占卡而阻塞。
- **deploy**：创建以 job_id 命名的容器，渲染并启动所选配方。默认 `default` 冒烟发送一次非流式 curl 真实推理，检查接口错误和生成内容，保存请求与响应。有效 READY 实例跳过 deploy/smoke；不强制 KV 传输或 DP 覆盖证明。
- **evaluate**：持有容器级锁，开始前检查服务身份与 READY 状态，执行单个性能 case、核验原始请求和输出长度、单独报告前缀目标与实测命中率。失败尝试使用独立目录，默认最多重试 3 次。
- **finalize**：按策略保留服务、停止服务或停止容器，记录并核验释放结果；可重复执行。无论测量通过与否都收尾，清理成功不代表测量成功。

状态与释放边界见 [生命周期说明](references/service-lifecycle.md)。每次重试前核验客户端已退出、临时链接已释放、服务身份仍有效；归属不明或残留状态未知时停止重试并上报。耗尽后报告该 case 失败；单 case 实现随即收尾，不包含下一 case 调度。实例变化使旧冒烟失效，不能仅凭 READY 字符串复用。

## 实现边界与产物

当前适配器为 `aisbench_prefix`，支持用户给定负载的前缀性能测试；预热和结果解析是该工具的约定。候选配方为 DSV4 P/D，配方负责模型相关启动参数，通用执行器负责容器、状态、锁、冒烟及清理。其他工具/模型先在值守阶段核验并适配，不能宣称未知组合已验证。

job_spec v2 每次只含一个 case、执行一轮。服务复用条件与清理策略已具备；跨 case 管理、精度评测、复杂故障分类、完整 Agent 与强弱模型复现留到后续。

自动执行保存计划、脚本快照、状态转换、各 attempt 原始结果、错误与释放记录。只操作核实归属的本任务资源，保留共享镜像、权重与证据；不把归档要求强加给手动操作。仓库 `docs/` 只放设计与工程计划，本地日志、报告与归档放在代码仓库之外（本机 `D:/autobenchmark-local/logs/`），不纳入 Git。目标服务器的任务工作目录及其内部 logs/ 布局保持独立。
