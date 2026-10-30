# DSV4 单机 PD 候选案例（2026-10-30 交接）

状态：旧机器已完成脚本修改和源码语法检查；本会话未完成修复后 PD 冒烟或四组正式压测。因资源被其他任务占用，用户计划迁移新机器并先值守运行。不得写成已验证性能配方。

保留目标：DeepSeek-V4-Flash-0731、Dspark 7，P 使用4卡 DP2/TP2，D 使用4卡 DP4/TP1；代理统一入口。四组为128K/1K与256K/1K，各50%/90%目标前缀比例，总并发64、每组64正式请求。新机镜像和模型必须重新核验。

旧现场改动：运行时全部卡可见，以 --device-ids 指定 P/D；GroupCoordinator 的 out-of-tree 分支使用 logical_device_id_to_visible_device_id 后再构造设备；MooncakeHybridConnector 增加 ascend_local_comm_res_path；修复超时值和重复 JSON key。补丁与选择设备方式配套，不能跨版本盲目应用。已有同事报告支持该设备映射绕过方案，但其原模型/MTP/并行配置与本任务不同，不能继承性能结论。

待处理：prefix caching 原先关闭；AISBench config 为占位值；旧容器缺 route.conf/hccn.conf，需按目标通信栈核对本机配置；工具管道可能掩盖失败；全链路和长上下文64并发尚未验证。保持KV与indexer fp8、模型和并发目标，发生OOM应记录失败，不能静默改配置。

旧定时任务创建为暂停，窗口已绑定旧日期，不应作为新机调度。新会话先使用 intake-handoff.md 完成采集，再明确值守轮数、每轮case顺序和新的无人值守窗口。
