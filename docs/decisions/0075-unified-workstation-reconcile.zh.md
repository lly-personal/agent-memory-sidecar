# ADR 0075：公开工作站采用单入口调和并保留健康私有 Owner

- 状态：Accepted
- 日期：2026-08-14
- 关联：[L1](../specs/axioms.md)、[L2](../specs/topology.md)、[L3](../specs/interface.md)、[Source Authority Cutover](../../specs/source-authority-cutover-v2.md)、[公开运维闭环 ADR](0074-public-operations-closure.zh.md)

## 背景

公开仓库已经是唯一工程权威，但部署路径仍把一个用户目标拆成“解析 Release、安装 Skill、开启下一任务、再同步来源、
再物化主机”。这个额外任务跳转不是安全边界：Resolver 已经验证 portable bundle，Bootstrap 代码已经可执行；真正需要
保留的平台边界只是 Codex 对新安装 Skill 的发现刷新。另一方面，公开 source manifest 合理地不携带私有 Owner，不能
因此把存量主机上已经健康绑定的 Owner 当成待删除状态。

## 决策

1. 用户只需要从公开仓库或 Plugin 表达一次“同步并部署本机 Agent Memory”。Anchor 验证不可变 Release 后，从已验证
   portable bundle 直接执行正式 Bootstrap 的工作站调和；不复制 Bootstrap 实现，也不等待第二任务才开始部署。
2. fresh install、同 identity 更新和存量换源共享一个内部调和模型。只有检测到任一现有 source identity 将改变时，才展示
   一份不含路径和 URL 的人类计划并要求一次确认；apply 必须 fresh 重算并原子回滚。
3. `canonical_owner=null` 表示公开发行物不分发 Owner，不表示解绑。仅当受管 Owner checkout 干净，且 Core binding 的
   `source_root`、`source_commit` 与它精确一致时，调和可以原样保留该 Owner。单边存在、dirty 或 identity 不一致均
   `source_cutover_owner_state_ambiguous` 失败关闭。
4. 普通 `sync-sources` 和普通 public-Core `materialize-host` 不获得隐式 Owner 搜索权；保留行为只属于已绑定 fresh plan
   的调和/换源事务。Owner 删除继续要求独立决策。
5. 成功只生成一份分层 receipt：Release 已验证、source 已同步、host 已物化、Doctor 已通过、Skill 下一任务可发现。
   它不证明当前任务采用新 Skill、项目激活、后续行为变化或真实第二台机器通过。

## 结果与代价

用户心智收敛为“一个入口、必要时一次确认、一份结果、一次平台刷新”，同时保留来源身份、Owner 权威与原子回滚边界。
实现需要安全展开 portable bundle，并精确读取现有 Core binding；这比复制第二套 Bootstrap 或增加后台更新器更小。真实
远端机器验收仍是独立证据，不能由本机测试替代。
