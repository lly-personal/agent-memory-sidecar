# ADR 0069：跨设备冷启动锚点与主机能力物化闭环

- 状态：Accepted
- 日期：2026-08-12
- 取代：ADR 0052、0065 与 0068 中“目标主机已能先取得 Bootstrap/Sidecar checkout”的隐含前提
- 保留：动态项目注册、交互 Project Scout 主路径、Host Enrollment 分离、中文 Review Pack 与人工逐卡授权
- 公开来源修订：本 ADR 中“私有 Sidecar `main` / repo marketplace 是第一跳 source authority”的段落已由 ADR 0072
  修订；它只保留为历史私有开发事实，公开安装必须使用 portable release 的 commit-bound manifest。

## 背景

当前主机已经完成三个工程的 Global Owner Scout 5.3.0 交互 canary，但远端事实表明只有 Sidecar 仓库包含
Bootstrap 与完整 Scout 源。业务工程即使同步到另一台机器，也没有可被 Codex 在该工程中发现的第一跳；裸机还
需要用户知道 Sidecar 仓库、canonical Owner 仓库、本地路径、安装顺序和 setup 命令。此前“同步并部署本机 Agent
Memory”SOP 从 Bootstrap 开始，却没有说明一台尚未拥有 Bootstrap 的主机如何获得它。

这造成了三个不可信断裂：

1. Git 内容可移植被错误等同于主机能力已物化；
2. 当前主机通过的交互 canary 被错误外推为另一台机器可冷启动；
3. 同一工程的 Owner 可以随 Git 续接，但完整 Scout 属于未同步的用户级安装，用户仍需重新解释部署细节。

## 决策

### 仓库冷启动锚点

明确加入跨设备连续性的 Git 工程携带一个极小的 repo-scoped `agent-memory-bootstrap-anchor`。它只识别用户的统一
部署意图 `同步并部署本机 Agent Memory`，并把执行路由到正式 Bootstrap；它不复制 Bootstrap/Scout 实现、不拥有
行为规则、不保存主机项目集合，也不创建 Scheduled Task。

同一工程还可携带 repo marketplace，指向 Sidecar 私有 Git 仓库内的 `agent-memory-sidecar` 冷启动插件。插件只
封装同一个 Anchor，使 Codex 可以通过官方 Git-backed marketplace 安装第一跳；完整 Bootstrap 与 Scout 仍只有
Sidecar `.agents/skills/` 一个权威源。若插件未加载，Anchor 使用内置 `skill-installer` 从相同私有仓库安装两项
Skill。新安装能力只从下一任务保证可发现。

### 受管能力源

Bootstrap 1.3.0 不再要求用户先提供本地 checkout。它从固定的能力权威身份同步 Sidecar 与 canonical Global
Owner 到 `$CODEX_HOME/agent-memory/sources/` 下的受管、可重建快照：

- 两个源先全部完成隔离 clone 与身份/clean/commit 校验，再替换本机受管目标；
- 已存在受管源若 remote identity 不符或 worktree dirty，整次同步失败关闭；
- 不对任何 Desktop 活跃项目执行 pull、reset、clean 或覆盖；
- 私有源使用本机既有 Git 凭据，认证失败报告 `source_sync_blocked`；
- 受管源只是安装输入，不是行为 Owner、项目工作区或跨主机状态库。

随后 Bootstrap 从 clean Sidecar 源运行 Core setup，从 clean canonical 源建立 global binding，执行 Doctor，并原子安装
Bootstrap 1.3.0 与 Scout 5.3.0 到本机 Skill 根。完整结果通过
`agent_memory_workstation_deployment_pack_v1` 分四层报告：

```text
portable distribution
-> source synchronization
-> host materialization
-> project activation
```

任何前一层成功都不得冒充后一层。相同主机上的空 CODEX_HOME 测试只证明确定性冷启动实现；真实第二台设备仍需
独立验收后才能声明 `cross_host_bootstrap=production_proven`。

### 项目与主机状态

项目发现继续动态遍历当前 Desktop 可见项目，不从 capability source、Anchor 或历史实验名单推断项目集合。Project
Owner、已提交工程事实与仓库 Anchor 随该工程 Git 同步；canonical Global Owner 与版本化能力随各自私有源同步。
以下状态仍只属于当前主机，不跨设备同步：

- Codex project ID 与绝对路径；
- Host Profile、Scheduled Task、运行计数；
- 本机任务历史与覆盖；
- 未确认 Review Pack 与候选；
- 插件启用开关和当前任务是否已加载新 Skill。

## 验收

1. Sidecar、PDG 与飞书三个工程均包含同名 Anchor 和 repo marketplace，且不包含固定本机路径、project ID 或项目
   allowlist。
2. Sidecar 插件通过官方 plugin validator；Anchor、Bootstrap 与 Scout 通过 Skill quick validation。
3. 空临时 CODEX_HOME 从私有 Git 源同步两个 clean snapshot；重复运行 no-op；源身份错配或 dirty 时失败且不清理。
4. Bootstrap 安装 Core/global binding/两项 Skill 并通过 Doctor；生成中文 Deployment Pack，四层状态互不替代。
5. 项目枚举仍与当前 Desktop 结果守恒；inspect 对自动化和 Host Profile 零变化。
6. 三个活跃工程的现有 dirty 内容逐字保持不变，只提交明确新增的 Anchor/marketplace 文件。
7. 在真实第二台设备只同步任一连续性工程后发送统一部署语，完成首次插件/Skill加载、下一任务物化、Doctor 与
   交互 Scout canary；在此之前只报告 `cross_host_bootstrap=implementation_verified / production_unproven`。

## 非目标

不构建 task/transcript 同步、Host Profile 同步、Scheduled 同步、未确认卡片同步、跨主机运行去重服务、数据库、
daemon、自动 Owner 写入、自动项目加入或第二行为 Owner。

## 平台依据

- [Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [AGENTS.md instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

## 回滚

通过 Git 恢复本 ADR、L1–L3、canonical model、Anchor 与 marketplace；删除当前主机新安装的插件缓存和受管 source
快照。Core Store、Host Profile、Scheduled Task 与用户项目工作区均未迁移，因此不需要数据回滚。
