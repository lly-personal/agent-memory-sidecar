# ADR 0064：中文业务语境审阅包与双投影模型

- 状态：Accepted
- 日期：2026-08-07
- 取代：ADR 0063 的 Project Card 与 Markdown 呈现契约
- 保留：ADR 0063 的直接交付拓扑、无中央阻断、只读自动化、人工最终授权与现有单规则修订链

## 背景

三份真实 v3 Scheduled 结果证明 Project Card 可以直接进入 Scheduled，但没有证明用户能够理解并判断。Sidecar
与 Feishu 结果的大量自然语言字段为英文；三个项目的 renderer 都把完整契约按固定顺序平铺，缺少决策索引、
项目业务叙事和信息优先级。中文标题、字段守恒与 hash 正确不能替代可理解的确认体验。

根因是同一 Project Card 同时承担两个不同读者的目标：用户需要中文、熟悉的项目语境、具体成本和选择后果；
最终 Owner 需要去项目化、精确、紧凑的 `When / Do / Skip`。隐私抽象正确地删除了路径、命令和局部阈值，
但旧契约没有为用户保留独立的脱敏业务叙事，于是 Agent 规则投影被直接当成了用户界面。

## 决策

Global Owner Scout 采用同源双投影：

```text
project evidence
-> project_v3 Project Card
   -> Human Context: zh-CN, contextual, privacy-safe
   -> Rule Projection: abstract, exact, owner-ready
-> integration preview
-> review_pack_v2 Chinese decision view
-> one user action
-> fresh owner read and existing single-rule revision path
```

目标工程线程拥有两个投影。`human_context` 与原有项目证据、因果、反证、owner 建议和 `rule_payload` 一起进入
`project_claim_hash`；renderer、integration preview 与按需中央审阅都只能校验和排版，不能翻译、补写或改写项目
语义。项目业务叙事可以保留用户熟悉的领域名词，但不得包含私有绝对路径、完整命令、账号、token、原始对话、
内部诊断正文或无助于判断的局部标识。

用户可见自然语言固定为简体中文。产品名、枚举、ID、URL、来源标题与拟写入 Owner 的精确文本可以保留原文；
英文专业词首次出现在说明正文时必须有中文解释。该语言策略只属于 Global Owner Scout 呈现契约，不扩展为所有
Agent 回复的 global 行为规则。

## 接口与动作

Skill 升级为 4.0.0，输出 `global_owner_scout_project_v3` 与 `global_owner_scout_review_pack_v2`。每张 Project Card
新增 `human_context`：`display_locale`、`decision_title`、`project_story`、`user_cost`、`recommended_outcome`、
`concrete_before`、`concrete_after`、`strongest_counterpoint` 与 `evidence_refs`。旧 v2/v1 结果不兼容接收；由于没有
数据库或候选状态，不执行数据迁移。

Review item 使用 `recommended_action`、`recommended_action_reason` 和 `allowed_actions`。`confirm` 只对 parity matched
且项目建议为 `global_agents` 的 `add/replace/consolidate` 卡开放；项目 Owner、Skill、已覆盖和不持久化卡不提供
直接确认。用户若要改变建议去向，先用 `修改 <card_id>：…` 生成新卡，再确认新快照。

## 呈现

确定性 renderer 依次显示：运行状态与警告、`今日需要判断 N 项` 索引、所有完整决策卡、技术附录和校验回执。
每张卡先显示 30 秒判断，再显示完整核对依据。before/after 使用两列表格；证据使用列表；表格最多四列；不得依赖
HTML 折叠、自定义 App UI、图片或预览期 Visualizations。全部 E2/E3 卡继续守恒且完整展开；容量不足仍以
`output_budget_exceeded` 整包失败。

## 验收与上线

旧三次 v3 运行不计入呈现验收，v4 从每项目 `0/14` 开始。上线前暂停三个自动化，在三个项目各运行一次 30 天
全新盲测。用户不查看 JSON、日志或项目文件，仍须能说明发生了什么、重复成本、建议 Owner、接受后的行为变化和
最大风险。只有三份 Review Pack 均获得用户明确的可读性确认，才更新 Scheduled Prompt 并重新启用。

语言 validator 拒绝用户叙事字段中的纯英文长句，但豁免代码、URL、来源标题、产品名、枚举、ID 与精确 Owner
文本。结构测试还必须覆盖证据引用、动作路由、parity 漂移、隐私、降级、无候选、容量失败与多卡守恒。

## 非目标与回滚

不建设中央传输、数据库、候选 Inbox、transcript parser、自动 Owner 修改、App/MCP 自定义 UI、动态模型路由或
第二行为 Owner。不改变 `gpt-5.6-sol + medium`、本机 Speed 继承或工作日每日周期。若原生 Markdown 经三项目真实
盲测仍不能支持判断，保持自动化暂停，并把自定义 UI 作为单独产品决策。

回滚恢复 Skill 3.0.0 与 v3 自动化 Prompt，并通过 Git 恢复 ADR/L1/L2/L3 和 canonical model；无数据迁移。
