# Job 包与存储

本机使用 submit_job.py prepare 校验 JSON、在 --local-jobs-dir 原子分配编号并冻结任务，再生成 job_id.tar.gz。统一使用同一本地 jobs 目录；远端编号冲突时拒绝覆盖，保留证据，重新分配新任务。任务包以文件清单和 SHA256 校验完整性。协调端与节点的 host/work_dir 相同时只上传一次；主机别名应在 bindings 中统一，脚本不推断不同别名是否属于同一机器。

每台服务器只有 work_dir/job_id 一个任务目录：

- common/inputs/：原始需求与现场 bindings；common/plan.json、common/job_spec.json：规范化冻结计划。
- common/skill-snapshot/：唯一运行包，含执行代码、Schema、测试原始数据和代理。同一节点内直接复用，节点部署不再复制包。排除测试代码、MD指引、示例及字节码。
- .internal/：现场绑定、生成脚本、服务身份和协调器诊断；deployments/ 保存服务日志，cases/ 保存负载定义，sub_tasks/ 保存测试结果。公共模块直接从 common 导入，仅会改写的适配脚本与配置保留独立文件。
- dataset-cache/：按参数及内容摘要复用的生成数据。
- tmp/、cache/：容器通用临时文件和缓存。
- 状态、summary.json、release-results.json、storage-state.json：执行及占用证据。

上传时先独占创建 job 目录，压缩包也落在目录内。压缩包和解压文件校验成功后删除远端压缩包；失败保留目录，不自动覆盖或重试未知任务。现场预检在该目录执行，prepare 不启动测试。全部归档均由单个 job 目录覆盖，没有 inputs-*、packages-* 旁路暂存目录。

disk_guard 按整个 job 目录统计常规文件的逻辑字节数，不跟随软链接；storage-state.json 保存统计及限额。每节点分别监控，按现有 admission/attempt/客户端运行中周期检查执行。此值不是文件系统块占用，也不包含共享镜像、权重、驱动日志和 Docker 元数据。容器关闭 Docker 日志驱动，服务日志仍写入任务目录；TMPDIR/XDG_CACHE_HOME 指向任务目录，但第三方程序硬编码的外部输出不保证纳入统计。容器可写层随任务容器释放，不声称目录大小等于主机全部增量。

## 主要产物：deployment 与 sub_task

新任务主要产物结构：

```text
deployments/<服务配置摘要前16位>-<运行编号>/
  deployment.json
  <服务名>.log
sub_tasks/<sub_task_id>/attempt-01/
  sub_task.json
  tool/  # 原工具产物及 aisbench.log 打屏日志
```

摘要由实际service定义计算（含命令、地址及端口），完整SHA256存于deployment.json，不作为跨机器模型配置标识。每次模型启动分配新编号；proxy加入同次运行。服务日志从启动持续记录至服务停止，多个sub_task复用服务时不切断、不复制日志。sub_task.json保存case参数、attempt、部署运行编号和路径、UTC起止时间、状态与错误。通过部署编号和时间定位服务日志。

重试独立保存，失败结果不覆盖。tool保留原工具结果结构；aisbench.log 保存表格和日志，子进程结束后仅去除 ANSI 控制符、修复表格底边粘行，不改变数值。不以自制汇总替代原工具产物。

新任务的 attempt 直接保存于 sub_tasks，不生成旧 results/tool/console.log 兼容软链接。工具日志以 aisbench.log 为唯一完整记录，不再写 aisbench_all.log 或向 outputs 复制日志。runner-diagnostics.log 仅失败时保留。脚本、探测记录、进程登记、数据集缓存均为辅助材料，执行和资源释放核验完成前不得删除。当前脚本不自动删除辅助目录或远端工作区；Agent归档以主要产物为准，校验归档完整性与资源释放后按用户授权清理。数据集缓存策略不变。


## 公共内容与结果入口

新任务上传的代码快照、原始公共输入、冻结计划及上传清单统一保存在 common/。模型进程管理、case runner、PD proxy 直接执行公共快照；测试工具公共模块通过模块路径复用，不为每个 attempt 创建模块和 GSM8K 软链接。每个 attempt 只保留需要修改的包装脚本与配置，以及工具原始结果。

cases/<case_id>/case.json 保存负载定义；deployments/ 保存连续服务日志；sub_tasks/ 保存各次测试结果。节点运行目录及协调服务状态放在 .internal/；内部提交日志放在 .internal/logs/。根目录保留运行入口与汇总状态，便于查询。旧冻结任务继续使用自身快照，不自动迁移历史绝对路径。
