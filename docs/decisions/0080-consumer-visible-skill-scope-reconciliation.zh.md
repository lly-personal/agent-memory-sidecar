# ADR 0080：工作站调和必须观察 Desktop 可见的项目级同名 Skill

- 状态：Accepted
- 日期：2026-09-01
- 关联：[L1](../specs/axioms.md)、[L2](../specs/topology.md)、[L3](../specs/interface.md)、[Workstation Reconcile v2](../../specs/workstation-reconcile-v2.md)、[ADR 0078](0078-workstation-reconcile-v2-observed-state.zh.md)

## 背景

Workstation Reconcile v2 已能精确读取 Marketplace、Plugin、受管 source、Core、Doctor 与用户级安装的 Bootstrap/Scout，
但 `ObservedHostState` 没有覆盖 Codex Desktop 会枚举的项目级 `.agents/skills`。Codex 会同时发现用户级和项目级同名
Skill，且不会把同名 Skill 合并。因此，一个活跃项目 checkout 可以继续携带旧 Bootstrap/Scout；主机托管层仍会
产生 `ready`，Desktop Skills 页面却如实显示旧版本。该结果不是缓存错误，而是完成声明的消费者范围小于真实发现范围。

项目 checkout 是用户拥有的工程事实，也可能是正在开发的下一版本。工作站部署不能通过 pull、reset、clean、删除或覆盖
项目内 Skill 来消除差异；但如果不观察该差异，也不能声称 Desktop 可见消费者已全部对齐。

## 决策

1. Deployment Pack 升级为 `agent_memory_workstation_deployment_pack_v3`，新增 `consumer_scope`。托管分发/物化与
   Desktop 可见项目范围保持两个独立证据层。
2. `verify_consumer` 必须接收本轮 Codex Desktop project API 的完整、临时项目清单。确定性 observer 按原生
   `isGitRepository` 从 primary folder 向 Git repo root 逐级检查两个产品同名 Skill：
   `agent-memory-workstation-bootstrap` 与 `global-owner-scout`；非 Git 项目只检查 primary folder，不枚举历史任务、
   自动化或固定仓库名单。无本机路径的项目保留计数并返回 bounded。
3. 输入中的绝对路径只用于本轮只读解析，不进入输出、日志、Pack hash、Git 或持久状态。输出只保留显示名、确定性
   `project_ref`、Skill 名、无路径层级、声明版本、物理内容 hash 与相对期望发行的 `exact` / `drifted` 关系。
4. 项目清单不完整、目录不可访问、Skill 物理树不安全、超出读取预算、读取中并发变化或版本不可解析时，消费者范围为 `bounded`；发现任一同名 Skill
   与期望版本/hash 不同则为 `drifted`；完整枚举且所有发现项精确匹配才为 `exact`。没有项目级同名 Skill 也属于 `exact`。
5. Pack 状态新增 `consumer_scope_drift` 与 `consumer_scope_bounded`。`ready` 现在同时要求：主机 exact、新任务采用已证明、
   Desktop 项目枚举完整且消费者范围 exact。apply 仍返回 `reload_required`，不会提前扫描或宣称采用。
6. 漂移和有界状态不自动修改项目。renderer 点名受影响的项目/Skill，并把下一动作路由到第一处消费者来源；开发中的
   有意差异可以继续存在，但完成声明必须保持限定。

## 结果

“托管部署已同步”不再被扩写成“Desktop 所有可见 Skill 均已同步”。用户能看到是哪一层精确、哪一个项目同名 Skill
造成差异，以及为何系统没有擅自修改该 checkout。代价是新任务验收需要一次原生项目枚举和只读文件检查；不新增数据库、
后台扫描器、UI scraper、项目 allowlist 或第二行为 Owner。

## 回滚

通过 Git 恢复 Deployment Pack v2、移除 `consumer_scope` observer 与对应测试。回滚不会改动任何项目 checkout；已经生成的
v3 Pack 是不可变回执，不作为当前状态来源。
