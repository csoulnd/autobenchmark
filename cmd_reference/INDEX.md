# 部署配置矩阵

更新时间：2026-11-05。以用户脚本为输入；官方规范用于检查，不自动改成官方示例。硬件形态当前单一，不设置硬件、证书字段。

目录：`模型/部署方案/配置/`。一个部署方案可有多个独立配置；点击配置查看统一 NOTES。

[新增配置规则与模板](CONTRIBUTING.md) · [旧路径映射](layout-migration-20261105.json)

| 模型 | 部署方案 | 配置 | 实例 DP/TP/PCP | Proxy | 验证范围 |
|---|---|---|---|---|---|
| deepseekv4.1flash | double-pd-split-1p1d | [baseline](deepseekv4.1flash/double-pd-split-1p1d/baseline/NOTES.md) | d.sh: 8/1/未显式指定；p.sh: 8/1/未显式指定 | 本地源码 0a8d83dee090 | 有静态检查记录，当前配置未完成端到端验证 |
| deepseekv4.1flash | double-pd-split-1p1d | [eplb-20261104](deepseekv4.1flash/double-pd-split-1p1d/eplb-20261104/NOTES.md) | d.sh: 8/1/未显式指定；p.sh: 8/1/未显式指定 | 本地源码 0a8d83dee090 | 有静态检查记录，当前配置未完成端到端验证 |
| deepseekv4.1flash | double-pd-split-1p1d | [user-eplb](deepseekv4.1flash/double-pd-split-1p1d/user-eplb/NOTES.md) | d.sh: 8/1/未显式指定；p.sh: 8/1/未显式指定 | 本地源码 0a8d83dee090 | 有静态检查记录，当前配置未完成端到端验证 |
| deepseekv4.1flash | single-pd-mix | [dp8-tp1](deepseekv4.1flash/single-pd-mix/dp8-tp1/NOTES.md) | mixed.sh: 8/1/未显式指定 | 不适用 | 有静态检查记录，当前配置未完成端到端验证 |
| deepseekv4flash | double-pd-split-3p1d | [dp1-pcp4-dspark1-3-mooncake-v2](deepseekv4flash/double-pd-split-3p1d/dp1-pcp4-dspark1-3-mooncake-v2/NOTES.md) | d.sh: 4/1/未显式指定；p1.sh: 1/1/4；p2.sh: 1/1/4；p3.sh: 1/1/4 | 待绑定公共 proxy；启动参数待补齐 | 整套 A/B 评测未通过；不得沿用单请求冒烟结论 |
| deepseekv4flash | double-pd-split-3p1d | [dp4-pcp1-dspark1-3-pr18549](deepseekv4flash/double-pd-split-3p1d/dp4-pcp1-dspark1-3-pr18549/NOTES.md) | d.sh: 4/1/未显式指定；p1.sh: 4/1/1；p2.sh: 4/1/1；p3.sh: 4/1/1 | 待绑定公共 proxy；启动参数待补齐 | 整套 A/B 评测未通过；不得沿用单请求冒烟结论 |
| deepseekv4flash | single-pd-split-1p1d | [p-dp2-tp2_d-dp4-tp1_mooncake-hybrid](deepseekv4flash/single-pd-split-1p1d/p-dp2-tp2_d-dp4-tp1_mooncake-hybrid/NOTES.md) | d.sh: 4/1/未显式指定；p.sh: 2/2/未显式指定 | 本地源码 48e2b7091a85 | 未重新运行；历史范围见原始记录 |
| deepseekv4flash | single-pd-split-1p1d | [p-dp4-tp1_d-dp4-tp1_mooncake-hybrid](deepseekv4flash/single-pd-split-1p1d/p-dp4-tp1_d-dp4-tp1_mooncake-hybrid/NOTES.md) | d.sh: 4/1/未显式指定；p.sh: 4/1/未显式指定 | 本地源码 48e2b7091a85 | 未重新运行；历史范围见原始记录 |
| glm5.3flash | double-pd-split-1p1d | [baseline](glm5.3flash/double-pd-split-1p1d/baseline/NOTES.md) | d.sh: 8/1/未显式指定；p.sh: 4/2/未显式指定 | 本地源码 48e2b7091a85 | 未重新运行；历史范围见原始记录 |
| glm5.3flash | single-pd-mix | [baseline](glm5.3flash/single-pd-mix/baseline/NOTES.md) | start.sh: 4/2/未显式指定 | 不适用 | 未重新运行；历史范围见原始记录 |

## 公共组件与历史材料

- [Memcache 元数据服务](common/memcache/start-meta.sh)：仅需要时使用，不自动加入部署。
- `_retired/`、`_ascend_runs/`、模型下 `references/`：历史材料，不纳入可执行配置矩阵。
- `deepseekv4flash/single/pd-mix/` 仅有停用说明，无启动脚本，不计作配置。
- 原有 LICENSE 文件保留第三方源码授权说明；不是证书配置。
