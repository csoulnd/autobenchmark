# deepseekv4flash / double-pd-split-3p1d / dp1-pcp4-dspark1-3-mooncake-v2

## 1. 配置概况

- 模型：deepseekv4flash
- 部署方案：double-pd-split-3p1d（single/double 指物理机器数量，不是硬件分类）
- 配置标识：dp1-pcp4-dspark1-3-mooncake-v2
- 来源：用户提供或既有参考脚本；原始来源说明见文末。
- 镜像：执行前指定并核验；目录名不代表镜像版本。

## 2. 服务实例与参数

| 脚本 | DP | TP | PCP | Connector | EPLB 显式开启 |
|---|---|---|---|---|---|
| [d.sh](d.sh) | 4 | 1 | 未显式指定 | MooncakeConnectorV2 | 未检测到有效开关 |
| [p1.sh](p1.sh) | 1 | 1 | 4 | MooncakeConnectorV2 | 未检测到有效开关 |
| [p2.sh](p2.sh) | 1 | 1 | 4 | MooncakeConnectorV2 | 未检测到有效开关 |
| [p3.sh](p3.sh) | 1 | 1 | 4 | MooncakeConnectorV2 | 未检测到有效开关 |

数字来自脚本文本静态提取；“未显式指定”不推断为默认值。完整环境、DSpark、eager/graph、batch 等以脚本为准。

## 3. 现场绑定与依赖

IP、网卡、权重、HTTP/RPC/KV 端口、工作目录和挂载均须重新绑定。已有固定值只是参考现场。

检测到的变量：`HTTP_PORT`、`KV_PORT`、`LD_LIBRARY_PATH`、`LIB_DIR`、`LOCAL_IP`、`MODEL_PATH`、`NIC_NAME`、`RPC_PORT`、`RUN_DIR`、`SHELL_RC`

配套文件：无本地配套 Python/env 文件。

## 4. Proxy

待绑定公共 proxy；启动参数待补齐。

镜像是否内置公共代理未在本次核验。未对现有 proxy.py 做版本替换或去重迁移。

## 5. 执行顺序

现场绑定与容器准备 → 启动模型实例 → 核验服务健康 → PD 场景启动代理 → 入口冒烟 → 评测 → 释放并核验。本目录脚本不等于整组协调器。

## 6. 检查与验证状态

- 本次：布局调整、Bash 语法检查；没有部署或性能测试。
- 社区参数/版本强校验：待检查 Agent 执行，不因入库自动标记通过。
- 运行结论：整套 A/B 评测未通过；不得沿用单请求冒烟结论。

## 7. 原始记录与差异

本次仅移动配置目录，服务脚本和配套源码未改写。原始 NOTES 中的旧路径/旧状态仅供追溯，以本索引和实际任务证据为准。

[原始 NOTES.txt](NOTES.txt)
