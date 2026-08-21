# Documentation Read Order

- Status: active
- Owner layer: project_docs
- Applies when: 定位 Agent Memory Core v1 的当前规范、操作文档、实现契约或历史理由。
- Avoid when: 小范围源码查找即可回答。
- Last verified: 2026-08-21
- Evidence: [L1](specs/axioms.md)、[L2](specs/topology.md)、[L3](specs/interface.md)、[ADR 0057](decisions/0057-agent-memory-core-v1.zh.md)、[ADR 0058](decisions/0058-persistent-runtime-journal.zh.md)、[ADR 0059](decisions/0059-bounded-behavior-set-evolution.zh.md)、[ADR 0070](decisions/0070-atomic-review-pack-rule-bundles.zh.md)、[ADR 0072](decisions/0072-allowlisted-public-distribution-lane.zh.md)、[ADR 0073](decisions/0073-public-engineering-authority-cutover.zh.md)、[ADR 0074](decisions/0074-public-operations-closure.zh.md)、[ADR 0075](decisions/0075-unified-workstation-reconcile.zh.md)、[ADR 0076](decisions/0076-task-scoped-review-pack-delivery.zh.md)、[ADR 0077](decisions/0077-deterministic-release-promotion.zh.md)、[ADR 0078](decisions/0078-workstation-reconcile-v2-observed-state.zh.md)

## 当前 Core v1 权威路径

按以下顺序阅读：

1. [`AGENTS.md`](../AGENTS.md)：仓库内 Agent 的高影响设计与实现边界。
2. [`specs/axioms.md`](specs/axioms.md)：L1 产品目标、公理、证据与非目标。
3. [`specs/topology.md`](specs/topology.md)：L2 owner、数据流、Store、scope 与 Desktop 边界。
4. [`specs/interface.md`](specs/interface.md)：L3 七字段、CLI、状态、失败与迁移契约。
5. [`domain.md`](../domain.md)：当前统一语言。
6. [`agent-memory-core-v1.md`](../specs/agent-memory-core-v1.md)：细粒度可执行契约与 AC。
7. [`0057-agent-memory-core-v1.zh.md`](decisions/0057-agent-memory-core-v1.zh.md)：Core v1 架构决策和回滚边界。
8. [`0058-persistent-runtime-journal.zh.md`](decisions/0058-persistent-runtime-journal.zh.md)：短生命周期 Runtime 的 SQLite policy、性能依据与回滚条件。
9. [`0059-bounded-behavior-set-evolution.zh.md`](decisions/0059-bounded-behavior-set-evolution.zh.md)：当前规则集演化、容量与 authority 去重决策。
10. [`user-guide.zh.md`](user-guide.zh.md)：用户可见操作。
11. [`operator-reference.zh.md`](operator-reference.zh.md) 与 [`codex-desktop-setup.md`](codex-desktop-setup.md)：安装、Doctor 与维护操作。
12. [`knowledge/README.md`](knowledge/README.md)：当前知识路由与平台事实边界。
13. [`src/agent_memory_sidecar`](../src/agent_memory_sidecar)：规范投影后的可执行实现。
14. [`public-distribution-v1.md`](../specs/public-distribution-v1.md) 与
    [`ADR 0072`](decisions/0072-allowlisted-public-distribution-lane.zh.md)：公开导出、可选私有 Owner 与发布证据门。
15. [`public-authority-cutover-v1.md`](../specs/public-authority-cutover-v1.md) 与
    [`ADR 0073`](decisions/0073-public-engineering-authority-cutover.zh.md)：首发候选、公开工程权威切换与私有工程源归档。
16. [`source-authority-cutover-v2.md`](../specs/source-authority-cutover-v2.md) 与
    [`ADR 0074`](decisions/0074-public-operations-closure.zh.md)、[`ADR 0075`](decisions/0075-unified-workstation-reconcile.zh.md)：
    公开 Release 解析、统一工作站调和与存量主机显式换源。
17. [`global-owner-scout-delivery-v1.md`](../specs/global-owner-scout-delivery-v1.md) 与
    [`ADR 0076`](decisions/0076-task-scoped-review-pack-delivery.zh.md)：任务级 Review Pack artifact、compact receipt 与
    实际任务表面资格。
18. [`release-promotion-v1.md`](../specs/release-promotion-v1.md) 与
    [`ADR 0077`](decisions/0077-deterministic-release-promotion.zh.md)：verified draft 到 attested immutable Release 的
    确定性 inspect/apply 与终态回读。
19. [`workstation-reconcile-v2.md`](../specs/workstation-reconcile-v2.md)、
    [`ADR 0078`](decisions/0078-workstation-reconcile-v2-observed-state.zh.md) 与
    [`工作站调和 SOP`](sops/workstation-reconcile.zh.md)：统一期望身份、真实分发读回、补偿事务与新任务采用门。

Global Owner Scout 的确认交接还必须读取 [`ADR 0070`](decisions/0070-atomic-review-pack-rule-bundles.zh.md)：用户可以
精确多选，同一 target 以一个原子规则包提交；逐卡只是批次大小为一的兼容形式。
其用户可见交付必须再读取 [`ADR 0076`](decisions/0076-task-scoped-review-pack-delivery.zh.md)：完整 Review Pack 位于
当前任务的 host artifact，聊天只返回 compact receipt；真实任务表面未回读前不得声明 Production Proven。

若上述活动来源冲突，L1 决定原则，L2 决定 owner，L3 和细粒度契约决定接口；停止完成态声明并先修正规范，
不得从历史文档静默选择实现。

## 历史与归档边界

- 当前公开树只携带本页路由的现行规范、仍需解释当前行为的 ADR，以及公开安全的证据索引。ADR 0001–0056 中
  未被本页列出的正文、旧 SOP、旧 evidence 与 legacy specs 只保留在冻结的私有工程归档，不存在于公开树，
  也不是公开构建、测试或未来 Agent 判断的隐式输入。
- ADR 0052 的 trusted-device bootstrap 前提已被 ADR 0069 的自包含、commit-bound 冷启动入口取代。
- ADR 0061 的来源分片和 ADR 0062 的固定七槽只记录未激活或失败的 Scheduled 中央传输尝试；ADR 0063 已将
  当前路径收敛为每个项目直接呈现完整 Review Pack，因此公开树只保留这条 supersession 结论。
- `docs/evidence/` 中公开的 dated records 只证明当时 checkout，不自动证明当前实现；私有 evidence 不进入公开事实面。
- `v0.2.0` tag 是旧可执行系统的回滚来源，不能作为 Core v1 的兼容要求。

需要考古冻结归档时只能只读使用。任何仍影响当前行为的理由必须先脱敏，并通过公开 Issue/PR 写入本页路由的
规范或 ADR；不得从归档历史静默恢复旧入口或改变公开 `main`。

不得因为历史文档仍描述 `status/remember/forget`、clean-store、release harness、editable Hook 或治理控制面而恢复这些入口。

## Owner directories

- `docs/specs/`：L1/L2/L3 当前设计入口。
- `specs/`：细粒度接口、Schema 与 AC。
- `docs/decisions/`：为什么做出决策；历史记录不批量改写。
- `docs/context/`：平台边界。
- `docs/sops/`：操作程序；必须由当前索引显式路由才算 active。
- `docs/evidence/`：按日期保留的证据，不创造行为事实。
- `docs/qdr/`：当前已知设计债、保留理由与明确删除条件。

公开树内保留的历史文档仍应保持链接可读，但只有本页“当前 Core v1 权威路径”中的文档定义当前行为。
