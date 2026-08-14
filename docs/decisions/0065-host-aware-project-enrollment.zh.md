# ADR 0065：主机感知动态项目注册与跨设备 Owner 连续性

- 状态：Accepted
- 日期：2026-08-07
- 取代：ADR 0060、0063、0064 中固定三个项目的激活假设
- 保留：项目判断权、中文双投影 Review Pack、只读 Scout、人工授权与零自动 Owner 写入

## 背景

固定三个高频项目适合早期验证，但不能成为跨设备产品模型。Codex Desktop 的本地项目集合、绝对路径、
`projectId`、近期任务和安全执行条件都会随主机变化。把固定项目名、路径或 `projectId` 写入共享 Prompt 或
部署配置，会把一台机器的执行状态错误提升为跨设备事实，并要求用户在每台机器重新理解和修正同一套配置。

正式部署还必须区分两种连续性：项目与 global Owner、已提交 Skill 和工程事实可以通过 Git 分发；Scheduled
任务、主机项目映射、运行计数和未确认 Review Pack 属于本机执行状态，不能从另一台机器复制或冒充已续接。

## 决策

采用主机感知的发现、建议、确认与调和链：

```text
Git 可移植层：Project Owner / Global Owner / Skills
-> 本机 Bootstrap
-> Codex Desktop 项目与近期自然任务发现
-> 中文 Enrollment Pack
-> 用户确认本机启用范围
-> Host Enrollment Profile
-> 按确认结果部署 Scheduled Scout
-> 中文 Project Review Pack
-> 用户逐卡授权
-> Project Owner / Skill / Canonical Global Owner
```

共享源不得包含固定项目集合、绝对路径、host `projectId` 或 automation ID。每次 Bootstrap 都从当前 Desktop
项目清单重建事实；新项目只形成建议，确认前不创建 Scheduled Task。现有任务在迁移确认前保持不变。

## 身份与状态

项目状态依次为：

- `discovered`：Desktop 项目存在且主路径可访问；
- `active`：滚动 30 天内至少存在一次自然用户任务，Scout、测试、自动化和委派任务不计入；
- `eligible`：Git 工程且可使用隔离 worktree；
- `enrolled`：用户已确认在当前主机启用。

Git 项目的 `project_content_identity` 由规范化 remote identity 与 primary folder 的仓库内相对位置确定，用于
跨设备识别同一内容工程。`host_project_id` 只绑定当前 Desktop，不进入 Git。无 remote 或非 Git 项目只有
host-local identity，不宣称跨设备同一性。

同一内容身份仅发生路径或 `projectId` 变化且匹配唯一时，可沿用既有 Host Enrollment 并自动重绑；多匹配、
remote 漂移或相对根变化必须重新确认。项目不可访问时自动暂停对应任务但不删除配置。

## Owner 与持久状态

- Project/global `AGENTS.md` 继续是必须执行行为的唯一 Owner。
- Repo-scoped Bootstrap Skill 拥有发现、Enrollment Pack、用户动作和自动化调和方法。
- Versioned Global Owner Scout Skill 拥有项目深挖与 Review Pack 方法。
- `$CODEX_HOME/global-owner-scout/host-profile.json` 只保存本机 enrollment 决策、内容 identity hash、host
  project/automation 映射、cadence 与验证时间；不保存证据、候选、卡片或 Owner 正文。
- Scheduled Task 是 Host Profile 的本机执行投影；不存在跨主机调度租约或运行去重。

项目 `AGENTS.md`、ADR/spec、仓库级 Skill 与工程事实只有在提交并同步后才具备跨设备连续性。canonical global
owner 同样通过私有 Git 分发。Session transcript、未确认 Review Pack、运行计数和 automation memory 不同步。

## Enrollment 与安全

Bootstrap 首先部署或验证 Core、global binding 与两个 Skill，然后只读枚举当前 Desktop 项目和近期任务并显示
中文 Enrollment Pack。`按建议启用`只选择 `active + eligible` 项目。任务来源无法可靠区分时使用
`activity_coverage=bounded` 和“建议试运行”，不得默认选中。

用户可以一次确认多个 Host Enrollment，因为该动作只改变本机执行配置，不修改行为 Owner。每个已确认 Git
项目使用一个 standalone worktree Scheduled Task；模型固定为 `gpt-5.6-sol + medium`，Speed 继承本机，工作日
每日运行。新任务从 09:10 起使用首个空闲的 15 分钟槽，已有确认时段不移动。

非 Git 项目因 Scheduled 只能直接运行在原目录，v5 不为其创建周期任务；它仍显示在 Enrollment Pack 中并解释
安全阻断。未来若有可机械证明的只读环境，须通过新决策扩展。

## 契约与迁移

- Bootstrap Skill：`1.0.0`
- Global Owner Scout Skill：`5.0.0`
- Project result：`global_owner_scout_project_v4`
- Review Pack：`global_owner_scout_review_pack_v3`
- Enrollment Pack：`global_owner_scout_enrollment_pack_v1`
- Host Profile：`global_owner_scout_host_profile_v1`

现有 Skill 4.0.0 与三个 v4 Scheduled Task 在用户确认前保持可运行。Skill 5.0.0 提供有界 legacy v4 兼容路径；
旧结果只作历史证据，不计入 v5 验收。确认迁移后原位更新任务，禁止创建重复任务。

## 验收

1. 正式代码、Prompt 和共享 Manifest 不包含固定项目名、路径或 host `projectId`。
2. Enrollment Pack 项目数与 Desktop 枚举结果守恒；同 remote 不同路径 identity 一致，同名不同 remote 不合并。
3. 确认前 Scheduled Task 零变化；确认后仅更新选中项目，重复执行为 no-op。
4. 活动来源不足时诚实标记 bounded；非 Git 项目不可被默认启用。
5. 两台机器可拥有不同 Host Enrollment，但同步后的 Project/global Owner 与 Skill hash 一致。
6. 一台机器确认并发布 global rule 后，另一台同步可获得相同 Owner；不得声称 Session、卡片或计数已同步。
7. 自动化调和失败时恢复本轮 Host Profile 与已修改任务；活跃工作区逐字节不变。

## 非目标

不建设固定项目白名单、跨主机候选 Inbox、Review Pack 传输、调度租约、运行去重服务、非 Git 无隔离周期运行、
自动 Owner 写入、自动 Git 发布、数据库或第二行为 Owner。

## 平台依据

- [Projects and chats](https://learn.chatgpt.com/docs/projects)
- [Scheduled tasks](https://learn.chatgpt.com/docs/automations)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)

## 回滚

恢复旧 Skill 与自动化快照，删除 Host Profile，并通过 Git 恢复本 ADR 及 L1/L2/L3/canonical model 变更。无数据库
迁移、候选状态或 Owner 数据迁移。
