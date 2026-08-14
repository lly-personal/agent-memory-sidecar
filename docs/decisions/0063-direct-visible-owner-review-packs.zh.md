# ADR 0063：直接可见 Project Review Pack 与人工裁决闭环

- 状态：Accepted
- 日期：2026-08-07
- 取代：ADR 0062 的十二任务固定七槽目标状态
- 后续修订：Project Card 与 Markdown 呈现契约由 [ADR 0064](0064-chinese-contextual-dual-projection-review-packs.zh.md) 取代；本 ADR 的直接交付拓扑继续有效
- 保留：Project Scout 判断权、只读自动化、人工最终授权、Core v1 与现有单规则修订链

## 背景

首次十二任务运行证明，项目深挖能够形成高价值 Project Card，但 Scheduled Central Context 无法可靠读取其他
Scheduled Task 的完整结果。Sidecar 与 PDG 已产出的 10 张 E2 卡因此没有到达用户；七槽和 Manifest 的结构守恒
通过不了，也没有形成可判断的用户界面。内部 JSON、hash 和任务完成不能替代用户实际看见并能处理一张卡。

官方 Scheduled Tasks 能力保证独立运行产生任务并把结果放入 Scheduled 收件箱，但没有建立 Scheduled Task 间
结果读取契约。因此跨任务摄取不得再处于唯一用户出口之前。

## 决策

采用三个项目直接交付的拓扑：

```text
Project evidence and sessions
-> immutable project_v2 Project Cards
-> global-owner integration preview
-> validated human-readable Project Review Pack
-> user handles one card in the same task
-> fresh owner read and existing single-rule revision path
```

Project Scout 仍拥有项目事实、证据等级、因果、抽象和本地 owner 建议。Project Card hash 固定后，同一任务只读取
canonical global `AGENTS.md` source 与活动宿主本机 global `AGENTS.md` target 并生成独立 integration preview；项目根
`AGENTS.md` 不得替代后者。preview 可以增加 global relation、一手调研、
before/after、风险和动作资格，但不得改写 Project Card。

每个 Scheduled 结果直接渲染该项目全部 E2/E3 卡；E1 保持紧凑。Session 覆盖不足时醒目标记 `degraded`，但由
Owner、ADR、Git、测试或验收独立支持的卡继续显示。该降级运行不计入 14 次完整有效运行。隐私、只读、结构或
Owner parity 失败仍阻断相应卡片或确认动作。统一原则是对可见性 fail-open、对写入 fail-closed。

Sidecar 可以由用户显式请求 `central_review`，读取已经可见的 Review Pack 并追加跨项目关联；它不是 Scheduled
任务，不是确认前置条件，也不能隐藏或改写来源卡。

当前 Scheduled 宿主以更高层约定强制 automation 读取并更新自身 memory，并在最终答复末尾追加一个 Inbox
directive；Prompt 无法关闭。该 memory 被隔离为宿主控制面 wrapper，只允许保存运行时间、覆盖/终态、卡片数量
或 hash、只读/parity 结果，不得保存原始证据、卡片正文、候选语义或去重判断，也不得参与下一轮发现。Inbox
directive 只用于把已经完整渲染的 Review Pack 暴露在 Scheduled 中，不是候选 Inbox 或跨任务结果桥。

若更高层运行时要求后置 Agent Memory 审计，它必须静默复用 Review Pack 中已有的真实卡片与校验回执，不得再
追加 memory 状态或第二份治理产物；唯一可追加内容是宿主强制的单个 Inbox 控制 wrapper。

## 用户界面与动作

Scheduled 最终答复是确定性 Markdown Review Pack，而不是原始 JSON。每张卡按决策顺序显示痛点、证据与反证、
因果、抽象、删除细节、研究、Owner 关系、When/Do/Skip、未来行为变化、精确 before/after/unchanged、风险和未
证明事项。parity matched 时提供 `确认/修改/留在项目/改做 Skill/忽略`；否则移除确认。

用户每次只处理一张卡。确认前重新读取最新 owner；若快照或语义关系漂移，旧确认失效并显示刷新卡。确认写入
后，其余卡必须重新校验。文件写入只证明 `instruction_deployed/adoption_unproven`，采用与撤销继续由两个项目的
后续自然任务验证。

## 自动化与验收

先暂停十二个旧任务。三个 30 天手动盲测都产生直接可见、可理解、可操作的 Review Pack 后，删除九个中央链
任务，只重新启用三个工作日 Scout：09:10 Sidecar、09:25 PDG、09:40 Feishu。三者显式固定
`gpt-5.6-sol + medium`，Speed 继承本机配置，正常结果进入 Scheduled 收件箱。

项目独立累计 14 次 `complete/bounded` 有效运行；`degraded` 可见但不计数。同一项目连续三次仅因 Session 索引
不可用而降级时暂停该项目并向用户显示能力阻断。第 14 次后只提出是否调整周期的决策卡。

14 次试运行使用当前 Desktop 宿主已验证的原生任务索引上限 `50` 作为首次请求，不使用超大页面探测。若宿主
能力变化，先版本化更新 Skill 与契约，再调整正式自动任务。

宿主不提供实际 model/reasoning 或 token telemetry 时只记录 `request_only`/`usage_unavailable`；这项不可观测性
本身不把 Session 已 complete/bounded 的运行降级，否则固定请求已满足但所有日常运行都会永久失去计数资格。

## 非目标与回滚

不增加文件结果桥、数据库、候选 Inbox、transcript parser、自动跨任务摄取、中央槽、Manifest、自动 Owner
修改、自动 Git 发布、动态模型路由或第二行为 Owner。回滚只需暂停或删除三个任务、移除可选 Skill，并通过 Git
恢复两个 owner 仓库的文档；没有数据迁移。

## 平台依据

- [Scheduled tasks](https://learn.chatgpt.com/docs/automations)
- [Notifications](https://learn.chatgpt.com/docs/notifications)
- [Skills](https://developers.openai.com/plugins/concepts/skills)
