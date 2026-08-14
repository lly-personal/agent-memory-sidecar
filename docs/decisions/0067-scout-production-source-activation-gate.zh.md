# ADR 0067：Scout 生产执行源激活门禁与宿主能力阻断

- 状态：Accepted
- 日期：2026-08-11
- 取代：ADR 0066 中“普通 worktree 前向测试通过即可恢复 Scheduled”与未指定执行者的“首次失败即暂停”语义
- 保留：动态项目注册、中文双投影 Review Pack、只读 Scout、人工逐卡授权、零自动 Owner 写入与可见输出完整性门禁

## 背景

三个真实 Scheduled Scout 均在 `thread_source=automation` 中调用原生任务索引后长期停留在运行中，没有取得终态、
任务页或卡片；同一时刻，交互任务的同参数调用可以在数秒内完成。随后创建的最小 Scheduled 探针不加载 Skill、
不读取项目文件、只调用一次 `list_threads(limit=50)`，仍在同一 automation 执行源复现了超过既定 180 秒预算的
`inProgress`。因此首个生产故障位于宿主 automation 执行源访问任务索引的边界，不在候选深挖、Project Card、
renderer 或可见输出 verifier。

先前验收发生了两处 authority 缺口：

1. 普通 worktree 测试只证明 Skill 与工具在交互执行源可工作，却被当作 Scheduled 生产可用性的恢复门禁；
2. 规范要求协议错误后暂停任务，但没有指定由谁调用宿主自动化控制面。只读 Scout 无权修改自身 Scheduled 状态，
   因而失败结果可见但任务继续 Active。

另有一个独立集成缺陷：项目线程通过猜测本机路径寻找 canonical global Owner，曾把项目根 `AGENTS.md` 当作
canonical global source，造成虚假 parity drift。逻辑端点虽在 Schema 中正确，物理端点解析仍不是确定性的。

## 决策

### 生产执行源门禁

任何主机、任何项目在激活 Scheduled Scout 前都必须先通过一个真实 automation-source canary：

```text
创建临时 standalone automation
-> 真实 Scheduled 独立任务出现
-> 原生任务索引在 180 秒观察预算内取得明确终态
-> 外部验收任务读取并确认终态与来源
-> 删除临时 automation
-> 只恢复一个项目 Scout canary
```

普通任务、普通 worktree 盲测、fixture、validator、Doctor、安装 hash 或 automation 配置为 Active 都不能替代该
门禁。观察预算届满而调用仍在运行时，不把原生调用伪造为 terminal failure；由外部宿主验收明确报告
`host_activation_blocked / native_index_non_terminal`，暂停相关 automation，并停止后续激活。

生产门禁通过后也只允许恢复一个项目。该项目必须完成一条真实链路：任务索引终态、自然任务完整分页、有效
Project/Review Pack、确定性 renderer、逐字可见结果和至少一张用户可判断卡。用户实际完成一次卡片动作后，才可
恢复其余已 enrollment 项目并开始各自的 14 次观察。

### 控制权与只读边界

Project Scout 继续只读，不得调用 `automation_update`、修改 Host Profile 或声称已经暂停自己。Scheduled Task 的
创建、更新、暂停和删除只属于 Workstation Bootstrap / 当前交互任务中的宿主激活控制面。控制面必须从最新 Host
Profile 与实际自动化清单解析目标，执行宿主工具调用后重新读取实际状态；仅输出“应暂停”不算完成。

Host Enrollment 与生产激活分开陈述：`enabled` 表示用户允许该主机为项目配置 Scout，不表示任务当前 Active，
更不表示生产可用。能力门禁失败时保留 enrollment 决策与历史结果，但 automation 保持 `PAUSED`，有效运行保持
`0/14`。删除任务仍需用户授权；临时 capability probe 在完成验收后不属于 enrollment，可直接删除。

### 确定性 Owner 端点解析

Scout 不再搜索或猜测 canonical global Owner 路径。它通过 Core Installation Registry 的
`global_instruction_binding` 只读解析 canonical source，并把活动 `$CODEX_HOME/AGENTS.md` 作为本机 global
target。helper 只输出固定逻辑端点、当前内容 hash、parity 状态与 snapshot hash；不得输出路径、remote 或项目
标识。binding 缺失、数据库不可读或端点文件不存在时为 `unavailable`，绝不能回退到项目根 `AGENTS.md`。

### 证据状态

Scout 的状态必须按以下阶梯单独报告：

```text
designed -> implemented -> installed -> production_proven -> longitudinally_effective
```

本主机当前只证明前三层。真实 Scheduled 索引未取得终态，因此整体状态为 `production_blocked`；三项目全部保持
`0/14`。文档、静态测试、普通任务成功和可见失败包不得被表述为“已经修复完成”。

## 当前主机处置

- 暂停三个已 enrollment 的 Project Scout，不删除 Host Profile 或历史结果。
- 暂停并在取证完成后删除临时 runtime probe。
- 保留手动 `project_scout` 能力用于项目内复盘，但手动结果不计入 Scheduled 14 次验收。
- 只有宿主更新、配置变化或新的最小 automation-source canary 真实取得终态后，才重新进入单项目恢复门禁。

## 验收

1. 自动化恢复测试必须来自真实 `thread_source=automation`，并由另一个当前交互任务读取终态；普通任务不得冒充。
2. 180 秒届满仍为 `inProgress` 时，验收结果为 `host_activation_blocked`，automation 实际状态必须复读为
   `PAUSED`，不得进入 14 次计数。
3. `enabled` enrollment、`ACTIVE` 配置、运行开始、失败包可见和生产可用分别陈述，不允许跨级。
4. canonical/local parity 只能来自 Installation Registry 解析的两个固定逻辑端点；项目根 Owner 回退测试必须失败。
5. `failed` Project Pack 不得同时显示“本次为 degraded / Session unavailable”的用户警告。
6. 单项目真实卡片与用户动作闭环完成前，其余项目不得恢复。
7. 活跃工作区、Owner、Git、Core 七表和已安装 Skill 在探针前后保持不变；临时 probe 不留下长期 automation。

## 平台依据

- [Scheduled tasks](https://learn.chatgpt.com/docs/automations)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)

## 回滚

恢复 ADR 0066 对应的 Skill 与文档不会使 Scheduled 生产入口变得可用，因此回滚只用于撤销本次代码变更；三项
Scout 仍保持暂停，直到新的真实 automation-source 证据改变能力判断。无数据库迁移或候选状态需要回滚。
