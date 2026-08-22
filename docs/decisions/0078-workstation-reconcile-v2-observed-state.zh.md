# ADR 0078：工作站调和以统一期望身份和真实读回取代手工完成声明

- 状态：Accepted
- 日期：2026-08-21
- 关联：[L1](../specs/axioms.md)、[L2](../specs/topology.md)、[L3](../specs/interface.md)、[Workstation Reconcile v2](../../specs/workstation-reconcile-v2.md)、[ADR 0075](0075-unified-workstation-reconcile.zh.md)

## 背景

ADR 0075 已把用户入口收敛为一次部署请求，但 v1 实现只统一了受管 source、Core、Owner、Skill 与 Doctor。
Deployment Pack 的 Plugin/Marketplace 字段仍由调用方填写粗粒度状态，生产式 fixture 可以在不读取 CLI、Marketplace
ref、Plugin version/hash/enabled 的情况下构造 `ready`。因此真实主机可能同时存在新 Core/Skill 和旧 Plugin/Marketplace，
用户却收到完成声明，并被迫理解 Anchor、Plugin、Bootstrap、Scout、source-cutover 与刷新边界。

## 决策

1. 引入唯一 `DesiredBundleIdentity`，由已验证 Release manifest、source manifest 与 portable 内容共同生成；Core、Plugin、
   Bootstrap、Scout、source ref/commit 和组件 hash 不再分别猜测。
2. `ObservedHostState` 必须通过 Codex JSON CLI、clean tracked Marketplace checkout、tracked manifest、可选 legacy install
   metadata、Plugin cache、source live runtime identity、Skill hash 与 Doctor 真实读回构造。当前 Codex CLI 未生成 legacy
   metadata 时仍以 tracked manifest 解析 ref；metadata 存在时继续严格校验。历史 source-cutover receipt 只能证明当时事务，
   不能替代当前主机观察。删除 `valid_pack()` 生产式 fixture。
3. Plugin/Marketplace 更新加入 Source Authority Cutover 的同一补偿事务；最终 exact readback 与 Deployment Pack v2 校验
   在 rollback 状态释放前完成。
   原子 source receipt 替换是 commit point；其后的快照清理失败只报告 post-commit cleanup，不得在部分 recovery copy
   已删除后再次反向回滚。
4. 显式禁用 Plugin 是用户选择，不自动启用。缺失、不可读、禁用与版本漂移采用不同阻断语义。
5. apply 最多证明主机物化，只返回 `reload_required`。一次 Desktop 刷新后的新任务加载 v2 Bootstrap，再执行只读
   consumer verification，才能把当前主机交互入口提升为 `ready`。
6. 已发布 Anchor 1.x 的 `source-cutover` 调用在完整 Resolver 输出布局下兼容路由到 v2；否则首轮升级仍会保留旧
   Plugin/Marketplace，并把用户推入第二轮部署和刷新。

## 结果

用户心智保持“一个入口、必要时一次确认、一份分层结果、一次平台刷新”。实现增加一个严格 distribution observer 和
事务参与者，但不增加 daemon、数据库、UI scraper、第二 Owner 或后台升级器。真实第二台设备、Scheduled、连续性与
产品收益继续是独立证据，不能由本机 Pack 升级。

## 回滚

通过 Git 恢复 v1 contract、Skill 与测试。运行时事务失败自动恢复本轮触碰的 Agent Memory Marketplace、Plugin、受管
source 与 Skill target；用户项目 checkout、Owner 正文、Host Profile 和 Scheduled Task 不在本次变更范围。
