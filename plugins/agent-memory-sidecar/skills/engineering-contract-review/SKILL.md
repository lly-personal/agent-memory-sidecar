---
name: engineering-contract-review
description: Review engineering contracts in state ownership, real-consumer verification, recovery or performance. Use relevant methods for design or defect analysis; skip mechanical edits and routine commands.
metadata:
  owner: agent-memory-sidecar
  source: https://github.com/lly-personal/agent-memory-sidecar/tree/main/plugins/agent-memory-sidecar/skills/engineering-contract-review
---

# Engineering Contract Review

这是 Agent Memory Plugin 的可选工程方法。源码由 Agent Memory Sidecar 工程统一维护，版本、分发和更新随所属 Plugin；安装副本不是第二份源码。它不修改 Global Owner，也不要求先运行 Scout。

从当前用户结果、已批准效果和实际项目契约开始。沿用当前任务或已有审查、调试入口，只有相关方法能帮助判断时才读取；不要求安装其他 Skill，不增加第二个控制器、审核关卡或登记库。

| 当前问题 | 按需参考 | 所需事实与输出 |
|---|---|---|
| 参数归属、合法意图、配置激活、派生状态 | [设计与状态](references/design.md) | 读写归属、实际消费者和活动契约 → 必要差量与合法例外 |
| API/事件、测试替身、失败出口、交付声明 | [真实入口验证](references/verify.md) | 被声明的结果、实际入口与已有证据 → 最小验证及准确未证层 |
| 续接、重试、外部效果、资源与终态 | [执行与恢复](references/recover.md) | 当前授权、依赖身份与提交状态 → 安全恢复或准确停止边界 |
| 热路径、共享资源拥塞、用户等待 | [性能与资源](references/performance.md) | 实际负载、具名预算或无预算事实 → 有条件的实测归因与最小变更 |

先定位参考中的相关标题，只读取需要的适用、执行和例外，不穷举全部条目。复用身份匹配的有效证据；实现手段可等价替换时保留原结果与效果边界。只在已有实现授权内修改，研究请求交付分析。方法使用不产生外部操作授权，文件加载不证明自然采用或用户体验通过。
