# ADR 0068：用户主动触发的 Project Scout 成为正式入口

- 状态：Accepted
- 日期：2026-08-12
- 取代：ADR 0067 中把 Scheduled 恢复视为 Global Owner Scout 主要产品交付路径的目标状态
- 保留：ADR 0067 的真实失败证据、automation-source 激活门禁、中文双投影、只读边界、逐卡授权和 Owner 连续性验证

## 背景

三个普通独立 worktree 任务已经证明 Project Scout 可以取得原生任务索引终态、分页读取自然任务、生成中文
Review Pack，并通过确定性 renderer 与可见输出校验。相同 Skill、Prompt、模型和 worktree 条件进入
`thread_source=automation` 后，三个真实 Scheduled 运行和一个最小探针都未取得任务索引终态。

继续把 Scheduled 恢复作为用户获得卡片的前置条件，会把已证明可用的项目复盘能力长期锁在未证明的宿主执行面
之后，并继续制造“安装完成但用户没有结果”的状态断裂。用户真正需要的是在目标工程中低成本触发一次深度复盘、
直接看到可判断卡片并逐张决定，而不是必须拥有每日后台运行。

Skill 5.2.0 已包含 `manual_30d`、用户请求模式和完整项目分析契约，但其 renderer 仍无条件输出 Scheduled Inbox
wrapper、14 次运行文案，并对手动任务强制 Scheduled pilot 的模型配置。因此手动能力尚未形成独立产品入口。

## 决策

### 正式产品入口

Global Owner Scout 的正式入口改为用户在目标 Git 工程中新建独立 worktree 任务并显式发送：

```text
$global-owner-scout 复盘当前项目
```

该入口固定使用 30 天手动证据窗口，依赖当前 Desktop 项目绑定推导身份，不要求用户提供路径、project ID、模型、
reasoning、Speed、Skill 版本、候选提示或深挖 Prompt。Skill 保持禁止隐式触发；普通实现、Git 操作和自然 continuation
不得进入 Scout。

交互任务继承当前任务的 model、reasoning 与 Speed，并在可用时记录实际运行值；校验只要求请求值与已观测实际值
一致。质量由覆盖、证据、卡片、renderer 和可见输出门禁决定。Scheduled 扩展仍固定
`gpt-5.6-sol + medium`，Speed 继承本机。

### 双呈现 surface

Project 与 Review Pack schema 继续使用 `global_owner_scout_project_v4` 和
`global_owner_scout_review_pack_v3`。renderer 与 verifier 增加独立执行参数：

- `interactive`：输出“本次需要判断”，不显示 Scheduled、Inbox、`0/14` 或 14 次计数，不包含 Inbox wrapper；
- `scheduled`：保留定时运行文案和唯一末尾 Inbox wrapper。

surface 只控制呈现 envelope，不改写 Project Card、Human Context、Rule Projection、Owner relation 或动作资格。
renderer 回执记录 surface 与 wrapper 数量；verifier 必须拒绝 surface、正文、回执或 wrapper 不一致。

### 状态与验收分离

状态按入口分别报告，不再用一个整体 Scout 状态覆盖不同执行面：

```text
interactive_project_scout: implemented -> installed -> production_proven
scheduled_project_scout: production_blocked / PAUSED / 0 of 14
owner_continuity: instruction_deployed / adoption_unproven -> adoption -> revocation
```

三个用户创建的真实 worktree 任务必须分别通过精确一句话入口 canary，才可声明 interactive production proof。
手动运行永不计入 Scheduled 的 14 次实验。用户完成 `修改`、`忽略` 或其他单卡动作可证明交互可操作；只有真实
Owner 写入与后续自然任务才能证明部署、采用和撤销。

### Bootstrap 与 Scheduled

正常工作站部署安装并验证 Skill 后，即可声明交互入口已安装；它不需要 Host Enrollment。项目枚举可以继续作为
信息展示，但 Scheduled 能力阻断时不得要求用户处理新的 enrollment 建议。

现有三个 Host Enrollment 和自动化保留为主机级历史授权与未来能力复测配置，原位迁移到最新 Skill 后继续
`PAUSED`。不得创建、删除或恢复周期运行。只有用户以后明确要求复测，且新的真实 automation-source canary 取得
终态，Scheduled 扩展才重新进入 ADR 0067 的单项目恢复门禁。

## 验收

1. 三个目标工程分别创建独立 worktree 任务，只输入正式触发语，Prompt 不包含预期候选。
2. 每个任务加载 Skill 5.3.0、使用 `manual_30d`，取得原生任务索引终态并分页读取所选自然任务。
3. 每个任务直接显示中文 Review Pack；interactive verifier 证明卡片与动作守恒、wrapper 数为零。
4. `no_material_delta` 只有在完整或可信 bounded 普查后成立；已知候选未出现时必须给出基于最新事实的失效理由。
5. 项目工作区、Owner、Git、自动化和外部系统保持不变。
6. 三项目通过后只提升 `interactive_project_scout`；Scheduled 仍保持 `production_blocked`。

## 平台依据

- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Scheduled tasks](https://learn.chatgpt.com/docs/automations)

## 回滚

恢复 Skill 5.2.0、Bootstrap 1.1.0、先前文档与三个暂停任务/Profile 快照。整个迁移期间 Scheduled 保持暂停，
没有数据库、候选或 Owner 内容迁移。
