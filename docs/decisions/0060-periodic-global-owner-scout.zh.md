# ADR 0060：周期性 Global Owner Scout 与人工确认闭环

> 状态：Accepted；Project Scout、判断权分层、只读与人工授权原则继续有效。自动中央传输拓扑先后由 ADR 0061、
> ADR 0062 尝试，并由 [ADR 0063](0063-direct-visible-owner-review-packs.zh.md) 取代；当前目标是三个直接可见审阅包。

- Status: accepted
- Date: 2026-08-06
- Owners: Agent Memory L1/L2/L3 与 canonical global instruction owner
- Decision scope: 用户显式启用的跨项目只读复盘实验

## 背景

高频项目的持续任务会产生真实有效的行为经验、设计原则和失败教训。这些事实通常只留在项目任务与局部
owner 中，无法稳定进入跨项目判断；反过来，直接把项目经验追加到 global `AGENTS.md` 又会造成重复、错误
全局化、结构失控和第二治理系统。

月度复盘无法在早期快速证明机制是否有效。实验期需要工作日每日运行，在三个高频项目中产生独立任务，
同时把自动化的权限严格限制为发现与呈现，而不是治理或发布。

## 决策

采用一个位于 Agent Memory Core 之外的两阶段工作流：

```text
三个项目的独立只读 project_scout
-> 任务结果中的 project_v2 与不可改写 Project Cards
-> 当前项目的 standalone Central Integrator
-> 全部合格 Project Cards 与独立中央注释
-> 用户逐张选择
-> 确认后复用既有单规则修订链
```

三个 Scout 在隔离 worktree 中运行，首轮手动回放读取用户当前 working-tree 快照并覆盖最近 30 天；自动运行
使用滚动 72 小时窗口。中央任务也是独立 scheduled task，只读取最新有效任务结果和上一份中央结果，不建立
结果文件 Inbox、数据库或 transcript parser。四个任务在最初 14 次有效运行内显式固定为 2026-08-06 官方
Power 默认 `gpt-5.6-sol` + `medium`，不继承用户配置，也不在验收期间动态切换模型。

自动运行严格只读：不得编辑文件、格式化、运行会写入工作区的命令、调用外部应用、执行网络写操作、提交、
推送、创建 proposal 或修改 owner。工作区前后不一致即整次失败。

项目事实判断权归目标工程线程：Project Scout 负责任务普查、工程事实重建、对比式因果复盘、候选穷举、项目内
反证、抽象、证据等级和本地 owner 建议，并以 `project_claim_hash` 固定完整 Project Card。中央只负责结构和
来源硬门禁、跨项目关系、global owner 对比、外部通用性调研、精确 before/after 与呈现。中央不得因缺少项目
上下文而降级、改写、隐藏或删除项目卡；有异议时必须保留项目立场并追加独立注释，由用户裁决。

## Owner 路由

候选只能分类为：

- `already_covered`：现有 owner 已表达，不换措辞新增；
- `add`、`replace`、`consolidate`：可能修改 global managed block，但只形成 review draft；
- `route_to_owner`：项目事实进入项目正式 owner，多步骤方法进入 Skill；
- 证据不足：保持观察，不沉淀。

全局正文结构重构不属于日常 Scout 权限，必须另行审批。必须执行的行为仍只由实际 `AGENTS.md` 拥有。Owner
路由是 Project Scout 的本地判断；中央可以指出 global owner 关系或提出 `coverage_dispute`，但不得覆盖本地判断。

## 证据与确认

E1 单次观察只进入紧凑观察项；E2 单项目重复、正式接受或真实验收必须完整出卡，并显著标明 `1/3 projects`
和错误全局化风险；E3 至少两个项目独立出现，中央只建立关联而不合并丢失差异；E4 只用于确认后采用证明。

Project Card 包含痛点、事件时间线、直接与反向证据、因果链、被接受变化、抽象过程、被删除的项目细节、
本地 owner 理由、最终规则、反例和未证明事项。中央卡原样嵌入 Project Card，再追加外部调研、global owner
关系、精确 before/after/unchanged 和五种用户动作。所有 E2/E3 卡完整显示，不设数量上限；无法完整输出时整次
失败，不允许部分卡片或中央排名。确认必须逐张进行，每次重读最新 owner 并重新计算修订；不得把 scheduled
draft 当作 pending proposal。

## 能力门禁与验收

创建自动化前必须真实证明：

1. standalone run 创建独立任务并加载正确项目与 Skill；
2. Scout 能读取属于该项目的近期任务摘要，或诚实降级；
3. 中央任务能读取并区分三个 Scout 的最新结果和上一份中央结果，且保持所有 Project Card hash 不变；
4. 自动 worktree 前后零 diff、零 commit、零 push、零外部写操作；
5. 用户原有 dirty 工作区逐字节不变；活跃工作区并发变化只限定快照覆盖，不让其他稳定候选整体失效；
6. 四个任务实际请求并由宿主接受 `gpt-5.6-sol` + `medium`，不可观测的实际 runtime metadata 被诚实标记。

任一能力不可用即停在手动回放。每个项目累计 14 次有效工作日运行后，只能提交是否降频的决策卡，不自动
改变周期。采用必须由至少两个项目中无答案泄漏的新自然任务证明；撤销后再用新任务验证不再采用。

## 后果

优点是把目标工程的深度复盘、global owner 结构约束和人工授权连成可观察纵切，同时不扩展 Core Store 或批量
授权面，也不让缺少项目上下文的中央任务成为第二审计者。代价是中央摄取依赖宿主原生任务可读能力；全部卡片
完整展示会增加阅读与输出成本，输出预算不足时必须诚实失败。

## 平台依据

- [Scheduled tasks](https://learn.chatgpt.com/docs/automations)：独立 Scheduled task、项目绑定与周期运行边界；
- [AGENTS.md instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md)：global/project instruction chain 与 owner 加载；
- [Skills](https://developers.openai.com/plugins/concepts/skills)：显式可复用工作流与自动化调度的职责分离。

## 拒绝的替代方案

- 月度运行：早期观测周期过长，增加验收滞后。
- 自动写入 global owner：违反用户授权与单一行为权威。
- 长期候选 Inbox 或数据库：形成第二治理状态和清理负担。
- transcript parser：扩大隐私面并依赖非正式任务表示。
- 宽泛固定 prompt：不能稳定强制证据、反证、抽象和 owner 判断。
- Central 重新裁定和排名项目候选：缺少目标工程上下文，会造成误删、误降级和单一视角偏差。
- 只显示前三张卡：会把已发现候选伪装成没有捕获，破坏召回与用户裁决证据。
- 当前线程 heartbeat 汇总：不能独立证明不继承活动线程的模型与 reasoning 配置。

## 回滚

暂停并删除四个自动化、归档其 worktree、移除个人 Skill，并通过两个 owner 仓库的 Git 变更恢复文档。因为
没有数据库迁移、长期候选状态或自动 owner 写入，不需要数据回滚。
