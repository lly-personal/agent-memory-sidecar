# Documentation Read Order

- Status: active
- Owner layer: project_docs
- Applies when: 定位 Agent Memory Core v1 的当前规范、操作文档、实现契约或历史理由。
- Avoid when: 小范围源码查找即可回答。
- Last verified: 2026-08-13
- Evidence: [L1](specs/axioms.md)、[L2](specs/topology.md)、[L3](specs/interface.md)、[ADR 0057](decisions/0057-agent-memory-core-v1.zh.md)、[ADR 0059](decisions/0059-bounded-behavior-set-evolution.zh.md)、[ADR 0070](decisions/0070-atomic-review-pack-rule-bundles.zh.md)、[ADR 0072](decisions/0072-allowlisted-public-distribution-lane.zh.md)、[ADR 0073](decisions/0073-public-engineering-authority-cutover.zh.md)

## 当前 Core v1 权威路径

按以下顺序阅读：

1. [`AGENTS.md`](../AGENTS.md)：仓库内 Agent 的高影响设计与实现边界。
2. [`specs/axioms.md`](specs/axioms.md)：L1 产品目标、公理、证据与非目标。
3. [`specs/topology.md`](specs/topology.md)：L2 owner、数据流、Store、scope 与 Desktop 边界。
4. [`specs/interface.md`](specs/interface.md)：L3 七字段、CLI、状态、失败与迁移契约。
5. [`domain.md`](../domain.md)：当前统一语言。
6. [`agent-memory-core-v1.md`](../specs/agent-memory-core-v1.md)：细粒度可执行契约与 AC。
7. [`0057-agent-memory-core-v1.zh.md`](decisions/0057-agent-memory-core-v1.zh.md)：Core v1 架构决策和回滚边界。
8. [`0059-bounded-behavior-set-evolution.zh.md`](decisions/0059-bounded-behavior-set-evolution.zh.md)：当前规则集演化、容量与 authority 去重决策。
9. [`user-guide.zh.md`](user-guide.zh.md)：用户可见操作。
10. [`operator-reference.zh.md`](operator-reference.zh.md) 与 [`codex-desktop-setup.md`](codex-desktop-setup.md)：安装、Doctor 与维护操作。
11. [`knowledge/README.md`](knowledge/README.md)：当前知识路由与平台事实边界。
12. [`src/agent_memory_sidecar`](../src/agent_memory_sidecar)：规范投影后的可执行实现。
13. [`public-distribution-v1.md`](../specs/public-distribution-v1.md) 与
    [`ADR 0072`](decisions/0072-allowlisted-public-distribution-lane.zh.md)：公开导出、可选私有 Owner 与发布证据门。
14. [`public-authority-cutover-v1.md`](../specs/public-authority-cutover-v1.md) 与
    [`ADR 0073`](decisions/0073-public-engineering-authority-cutover.zh.md)：首发候选、公开工程权威切换与私有工程源归档。

Global Owner Scout 的确认交接还必须读取 [`ADR 0070`](decisions/0070-atomic-review-pack-rule-bundles.zh.md)：用户可以
精确多选，同一 target 以一个原子规则包提交；逐卡只是批次大小为一的兼容形式。

若上述活动来源冲突，L1 决定原则，L2 决定 owner，L3 和细粒度契约决定接口；停止完成态声明并先修正规范，
不得从历史文档静默选择实现。

## 历史来源

- ADR 0001–0056、旧 SOP、旧 evidence 与根目录 legacy specs 保留为历史理由或回滚证据。
- 根目录 legacy specs 已显式标记为被 Core v1 supersede；它们不定义当前 CLI、Store、状态或发布门槛。
- `docs/evidence/` 中的 dated records 只证明当时 checkout，不自动证明当前实现。
- `v0.2.0` tag 是旧可执行系统的回滚来源，不能作为 Core v1 的兼容要求。

不得因为历史文档仍描述 `status/remember/forget`、clean-store、release harness、editable Hook 或治理控制面而恢复这些入口。

## Owner directories

- `docs/specs/`：L1/L2/L3 当前设计入口。
- `specs/`：细粒度接口、Schema 与 AC。
- `docs/decisions/`：为什么做出决策；历史记录不批量改写。
- `docs/context/`：平台边界。
- `docs/sops/`：操作程序；必须由当前索引显式路由才算 active。
- `docs/evidence/`：按日期保留的证据，不创造行为事实。
- `docs/qdr/`：当前已知设计债、保留理由与明确删除条件。

历史文档仍应保持链接可读，但只有本页“当前 Core v1 权威路径”中的文档定义当前行为。
