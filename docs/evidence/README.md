# Evidence Records

- Status: active index; contained dated records are historical
- Owner layer: project_docs
- Applies when: 查找早期 Agent Memory 调研、验收或回归证据的来源。
- Avoid when: 判断 Core v1 当前行为或发布状态；读取活动规范、源码和当前测试。
- Last verified: 2026-07-24
- Evidence: [Core v1 L1 evidence ladder](../specs/axioms.md)、[Core v1 L3 acceptance](../specs/interface.md)

## 当前边界

Core v1 尚未创建 tag、Release 或发布证据包。当前 checkout 的自动化结果只能证明其运行时、Store、授权、文件事务、
安装和迁移机制；真实 Codex Desktop 新任务才可证明 deploy 后采用与 revoke 后不采用。

Ambient discovery 继续是 experimental。旧 release harness、trace、action ledger、benchmark CLI 或 evidence matrix
不因历史记录存在而恢复。

## 历史记录

本目录中的 dated records 与旧 release 说明保留用于 provenance。它们只能描述当时的 commit、运行时和宿主环境，
不能满足 Core v1 gate，也不能证明当前 Desktop 行为。不可变 `v0.2.0` Release 仍是旧可执行系统的回滚证据。

## 记录原则

- 明确 commit、日期、宿主、输入边界和证据层级。
- 不保存 secrets、原始无界 prompt、完整 transcript 或可变 Store snapshot。
- 区分配置、传输、instruction deploy、模型采用、连续性和产品收益。
- 缺失或无法归因时标记 `未证明`，不把 plausible output 升级为事实。
