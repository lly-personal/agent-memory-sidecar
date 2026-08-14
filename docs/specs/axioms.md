# Agent Memory L1 设计公理

- Status: active
- Owner layer: project_docs
- Applies when: 设计、评审或变更 Agent Memory 的产品目标、行为权威、授权、隐私、证据或发布边界。
- Avoid when: 只执行普通项目工作或不改变机制语义的机械修改。
- Last verified: 2026-08-14
- Evidence: 用户批准的 Agent Memory Core v1 与条件可见终态闭环设计、[Core v1 ADR](../decisions/0057-agent-memory-core-v1.zh.md)、[有界规则集演化 ADR](../decisions/0059-bounded-behavior-set-evolution.zh.md)、[周期性 Global Owner Scout ADR](../decisions/0060-periodic-global-owner-scout.zh.md)、[直接可见审阅包 ADR](../decisions/0063-direct-visible-owner-review-packs.zh.md)、[中文双投影审阅包 ADR](../decisions/0064-chinese-contextual-dual-projection-review-packs.zh.md)、[主机感知动态项目注册 ADR](../decisions/0065-host-aware-project-enrollment.zh.md)、[执行与可见输出完整性 ADR](../decisions/0066-scout-execution-and-visible-output-integrity.zh.md)、[生产执行源激活门禁 ADR](../decisions/0067-scout-production-source-activation-gate.zh.md)、[用户主动触发主路径 ADR](../decisions/0068-interactive-project-scout-primary.zh.md)、[跨设备冷启动连续性 ADR](../decisions/0069-cross-device-cold-start-continuity.zh.md)、[原子规则包 ADR](../decisions/0070-atomic-review-pack-rule-bundles.zh.md)、[所见即所签与物理 containment ADR](../decisions/0071-wysiwys-review-pack-bundles-and-physical-target-containment.zh.md)、[白名单公开分发 ADR](../decisions/0072-allowlisted-public-distribution-lane.zh.md)、[公开工程权威切换 ADR](../decisions/0073-public-engineering-authority-cutover.zh.md)

## 产品定义

Agent Memory 不是通用记忆数据库或规则事件日志，而是用户授权的有界协作规则发布器：

> 将相对于现有全局与项目 authority 仍然必要的行为增量，经过一次明确授权后可靠发布到正确作用域的
> `AGENTS.md`，并确保后续任务能够采用、查看、演化和撤销。

连续性价值由以下乘积决定：

```text
正确规则 × 正确作用域 × 实际加载 × 行为采用 × 可撤销
```

任一项为零，都不能声称连续性成立。成功必须同时满足：

1. 普通、未审计且没有合格候选的任务保持安静。
2. 用户主动审计、明确记住，或 Agent 面向用户表示 Agent Memory 已参与时，最终答复必须以一个真实终态结束；
   过程说明、Hook 传输或将来时承诺不算终态证据。
3. 未确认内容不进入长期指令。
4. `生效中` 只来自实际 target 中可解析且未被 override 屏蔽的规则。
5. 后续新任务采用规则；撤销后的新任务不再从该 owner 获得规则。
6. 失败只报告已证明层级，不以调用开始、数据库记录或文件存在冒充完成。

## 有界行为增量

managed block 是当前 target 的有界行为增量集合，不是按会话追加的历史：

1. **Authority 不重复**：项目 `AGENTS.md`、当前任务已按项目 router 读取的 L1–L3 或其他正式 owner
   已经表达的内容，不再复制为 managed rule。
2. **演化优先于累积**：新的纠正先判断是否覆盖、修订或归并现有规则；只有真正独立的行为增量才能新增。
3. **容量只提供背压**：单规则 1 KiB、managed block 8 KiB 是 Sidecar 的编辑预算，不是 Codex 文件限制；
   超限拒绝整次修订，但不触发 TTL、LRU、自动删除或后台 GC。
4. **规则集修订授权**：模型可以提出 `no-op`、新增、替换、归并或 owner 路由；删除或替换已有规则必须由
   用户授权精确的修改前状态和修改后规则集，确定性层只执行该修订。

## 八条公理

| 公理 | 强制边界 | 禁止项 |
| --- | --- | --- |
| 连续性价值 | 新实体必须直接降低未来重复说明或错误行动。 | 只增加流程、报告或内部状态。 |
| 用户授权 | Agent 可以发现和概括；只有用户能授权长期变化。 | 自动批准、沉默即同意、把未接受选项持久化。 |
| 单一行为权威 | 必须执行的规则只存在于实际生效的 `AGENTS.md`。 | 把 SQLite、Memories、Hook、Skill、Git 源或撤销历史当作第二 owner。 |
| 概率与确定性分离 | 语义发现可由模型完成；授权、scope、写入、状态和撤销必须确定执行。 | 用模型判断或关键词命中替代授权。 |
| 最小持久化 | 确认前只保存有期限、内容绑定的 opaque ref/hash。 | 保存原始 prompt、回复或 proposal 正文。 |
| 证据不可跨级 | 配置、传输、会话终态、部署、采用、连续性和收益分别陈述。 | 用过程播报、测试、Doctor、Hook 输出或 parity 代替终态或行为采用。 |
| 可逆与诚实失败 | 规则可编辑、可撤销；失败明确为未保存、未部署或未证明。 | 先宣称成功再写入，或隐藏部分完成。 |
| 奥卡姆约束 | 只保留闭环必需的 owner、状态和入口。 | 通用记忆库、自然语言路由器、自动治理、生命周期控制面、大型证据控制面。 |

上述公理同时约束规则集演化：语义重叠判断仍属于 Agent 的概率判断，任何自动删除、静默归并或
把项目事实复制到 managed block 都违反用户授权、单一行为权威和奥卡姆约束。

文件安全按控制权而不是路径字符串形式判定：owner、Store、Skill 或公开选择面内由用户或仓库可控制的 symlink、
junction/reparse、非普通文件和多硬链接必须拒绝；操作系统拥有的顶层目录映射不是用户可控制的 owner 漂移，
不得仅因 macOS 等宿主的标准路径布局误拒绝合法运行。Windows 私密权限按实际授权主体判定，不以 ACE 数量或
SDDL 文本表现形式代替权限语义。

## 产品分层

- 稳定核心：显式授权、作用域校验、规则部署、查看、编辑和撤销。
- 实验能力：Ambient discovery 与单卡建议；不阻塞稳定核心发布。
- 可选分发：私有 Git 传播完整 global `AGENTS.md`；本机 target 才决定本机行为。
- 公开分发：只从白名单导出 Core 与版本化 Plugin/Skill；私有 Owner 是可选后端，不随源码或发行物公开。
- 公开演进：首发验收前私有工程仓库是唯一研发权威；明确切换后公开 `main` 接管全部公开研发与发行，私有工程仓库
  冻结归档。公开候选期不得解释为双 owner 或长期镜像。
- 可选背景：Codex Memories 可以关闭，不能改变强制规则行为。

## 外部项目复盘实验

Global Owner Scout 是用户显式触发的外部项目复盘 workflow，不是 Core 的默认后台治理能力。正式入口是用户在
目标 Git 工程中新建独立 worktree 任务并发送 `$global-owner-scout 复盘当前项目`；它重建项目事实、提炼候选并
直接生成用户可见的 Project Review Pack。任何运行都只产生 `review draft`，不得创建 proposal token、写入七表
Store、修改任何 `AGENTS.md`、发布 Git 或调用外部写操作。Scheduled 只是暂停的可选宿主扩展，不能阻断交互结果。

该实验的正式激活集合由每台主机动态发现和人工确认，不由共享源携带固定项目名单。Project/global Owner、已提交
Skill 和工程事实属于 Git 可移植层；Codex `projectId`、绝对路径、Scheduled Task、运行计数与未确认 Review Pack
属于主机执行层。内容可移植性不得被冒充为主机激活，主机激活也不得反向成为第二行为 Owner。

该实验分为证据面、呈现面与授权面：目标工程 `project_scout` 对项目事实、证据等级、因果关系、抽象与本地
owner 建议负责，并把同一 Project Card 分别投影为中文、保留业务语境的 Human Context 与精确、Agent 友好的
Rule Projection；两者均在 global owner 比较前由项目线程固定并进入内容 hash。同一任务随后生成独立 global owner
integration preview，并把完整中文审阅包直接呈现给用户；用户独占长期规则的最终取舍和授权。Sidecar 的按需中央
审阅只能追加跨项目关系与并列注释，不能成为项目卡可见性或确认的前置条件。

该实验遵循以下不变量：

1. **证据先于抽象**：项目事实先形成候选，外部调研只能验证或挑战候选，不能凭空创造规则。
2. **双投影不混用**：Human Context 必须使用简体中文和用户熟悉的脱敏项目语境，帮助用户判断真实成本、建议、
   行为变化与最大风险；Rule Projection 才删除项目名、路径、命令和局部阈值，供最终 Owner 精确修订。不得把
   抽象规则直接充当用户确认界面，也不得把项目故事写入 global managed block。
3. **单项目证据不冒充共识**：单项目重复、正式接受或真实验收可以形成 E2 卡片，但必须显示实际独立项目支持
   数、覆盖边界、外部支持或用户级偏好，以及错误全局化风险；不得使用固定项目总数作分母。
4. **项目语义不可被整合预览覆盖**：Project Card 的 Human Context、Rule Projection 与其他核心语义以内容 hash
   固定；后续 global owner 比对与按需
   中央审阅可以校验、关联、质疑和追加注释，但不得修改项目证据等级、痛点、反证、抽象或 owner 建议。
5. **正式 owner 优先**：项目事实、设计规范和多步骤方法分别路由到项目 owner 或 Skill；只有未来跨项目
   必须执行的行为增量才进入 global managed block 的人工决策范围。
6. **直接全量可判断**：每个项目全部合格 E2/E3 卡必须由该项目的当前复盘任务直接完整显示；先给出中文决策
   索引和逐卡 30 秒判断，再展示完整依据，E1 与技术覆盖进入附录。内部 Project Card 数与可见 Markdown 卡数必须
   守恒，不得通过中央失败、排名、摘要或通知策略隐藏项目卡。
7. **可见性与写入采用不同失败边界**：Session 覆盖不足只能产生醒目的 `degraded` 警告，不得删除由 Owner、ADR、
   Git、测试或验收独立支持的卡；隐私、只读、完整性或 Owner parity 失败必须阻断相应写入动作。
8. **人工精确选择、所见即所签**：复盘输出始终是草案。用户可以一次选择同一 Review Pack、scope 和 target 的
   一张或多张可确认卡；每张卡以 `card_id@selection_token` 绑定项目 claim、proposal、superseded 集合、target 与
   Fresh before。Agent 必须读取一次最新 owner、联合重算关系与聚合 before/after，并执行零或一次原子规则包修订；
   Core 必须证明当前回复逐字等于选中集合的 canonical 确认文本。单卡是大小为一的规则包；不得循环复用 approval、
   沿用旧快照、按输入顺序解释集合或留下部分成功。
9. **资源策略随入口分层**：交互任务继承当前任务的 model、reasoning 与 Speed，并验证可观测实际值与请求一致；
   暂停的 Scheduled 14 次实验仍固定 `gpt-5.6-sol + medium`，Speed/service tier 继承本机配置。用户触发语不携带
   资源配置，手动运行也不计入 Scheduled 14 次实验。
10. **零背景状态**：不得增加候选 Inbox、transcript parser、长期候选数据库、后台规则 GC 或第二行为 owner。
11. **证据不可跨级**：定时发现与文件写入不证明自然任务采用。采用和撤销必须由后续无答案泄漏的新任务验证。
12. **可移植安装与可选激活分离**：Bootstrap 安装并验证 Skill 后，所有满足隔离条件的目标工程即可由用户显式
    触发，无需 Host Enrollment。只有用户明确要求 Scheduled 实验时才进入项目发现与 enrollment；共享 Prompt、
    Manifest 与 Owner 不得写入固定项目名、host `projectId` 或绝对路径。
13. **安全资格先于推荐**：滚动 30 天自然任务决定 `active`，Git worktree 能力决定 `eligible`；Scout、测试、
    自动化和委派任务不计入自然活动。任务来源不可证明时只能 `bounded / 建议试运行`，非 Git 项目不得默认启用。
14. **原生工具必须取得终态**：任务索引或分页调用返回运行中 cell 时，必须恢复同一 cell 直到明确终态；未恢复、
    非法参数或执行序列中断属于 `execution_protocol_failed`，不得伪装为 Session 不可用或覆盖降级。
15. **可见结果必须逐字守恒**：只有通过校验的 Review Pack 经确定性 renderer 完整生成，且最终回复的正文 hash、
    卡片、动作与 surface-specific wrapper 数量通过二次验证，才算完成呈现。interactive 必须零 wrapper，scheduled
    必须唯一末尾 wrapper；renderer 失败后不得由模型手工重写结果。
16. **Enrollment 不等于生产激活**：用户确认 `enabled` 只授权本机配置该项目，不证明 automation 当前 Active、
    原生任务索引可用或 Scheduled 生产链成立。恢复周期运行前必须由真实 `thread_source=automation` canary 在外部
    验收下取得终态；普通任务、fixture、Doctor 与安装 hash 不能替代。
17. **控制权不下放给只读 Scout**：Project Scout 只能输出证据与 Review Pack，不能修改 Host Profile 或
    Scheduled 状态，也不能以文字宣称已暂停。自动化的创建、暂停、恢复与删除由 Bootstrap / 当前交互任务的宿主
    激活控制面执行，并以工具调用后的实际状态复读为准。
18. **可移植内容不冒充主机能力**：仓库 Owner、已提交 Skill、冷启动 Anchor 与插件目录只证明远端可取得的内容；
    只有当前主机完成能力源同步、Core/global binding/Skill 物化、Doctor 与新任务加载后，才能声明交互入口已安装。
    当前主机 canary 不得外推为另一台机器已经具备相同能力。
19. **冷启动第一跳必须自包含**：任何明确加入跨设备连续性的工程必须携带极小 repo Anchor 或等价官方分发入口，
    使用户只需表达“同步并部署本机 Agent Memory”；不得要求用户记住 Sidecar checkout、canonical Owner 路径、
    project ID、项目名单或安装顺序。Anchor 只路由到唯一 Bootstrap 源，不复制实现或成为第二 Owner。
20. **派生源与工作区分离**：Bootstrap 只原子更新 `$CODEX_HOME` 下身份固定、clean、可重建的受管源，不得为同步
    而 pull/reset/clean/覆盖 Desktop 活跃项目。项目集合仍由当前主机动态发现和用户决定，不由能力源仓库反推。
21. **公开分发与私有证据分离**：不得把带历史证据和主机痕迹的工程仓库原地公开。公开物必须来自默认拒绝的
    allowlist、commit-bound source manifest、许可证门和隐私扫描；`canonical_owner` 缺省只关闭 global 集成，
    不得阻断 project-scope Core 或创造替代 Owner。
22. **公开工程权威单一化**：独立公开仓库在首发资格完成前只是候选，不能与私有工程源同时拥有产品事实；只有
    公开 Release、干净安装、远端回读和单独人工确认全部成立后，公开 `main` 才成为唯一工程权威，私有工程仓库
    随即冻结归档。发布证据不得自动冒充权威切换，切换后不得继续私有导出或双向同步。

该实验按入口独立停止：无法证明交互 worktree 任务取得任务索引终态、中文 Review Pack 可理解性、直接呈现、
隔离零变化或隐私过滤时，交互入口保持 `interactive_host_blocked`；无法证明 automation 执行源时只保持 Scheduled
暂停，不得阻断已经通过的交互入口。Session 原生
工具返回明确终态错误时可以展示其他正式证据支持的降级结果；调用持续运行但未终态时属于宿主激活阻断，既不
生成降级卡也不计入 14 次完整有效运行，不得以新增文件队列、数据库或 transcript parser 补洞。

## 条件可见终态

Agent Memory 的默认体验是安静但可审计，而不是无条件静默：

- 普通任务没有合格候选且用户没有审计时，不显示检查过程或回执。
- 一旦进入 Agent Memory 流程，当前最终答复必须显示且只显示一个与实际动作一致的终态：确认卡片、
  直接部署、已覆盖、正式 owner 路由、无候选或诚实失败。
- 无动作回执只证明本轮 Agent 给出了可见分类，不是持久化、部署或采用证据。
- 用户可见终态由 Agent / Skill 负责；不得为此增加语义 Hook、持久化分类、审计表或第二行为 owner。

## 证据阶梯

证据只能逐级声明：

1. `configured_readiness`
2. `native_ingress`
3. `transport_observed`
4. `instruction_deployed`
5. `model_adoption_observed`
6. `continuity_observed`
7. `product_effect_observed`

自动化最多直接证明前四层的机制事实。真实 Desktop 新任务才能证明采用与撤销后的连续性。

## 非目标

Core v1 不提供：

- 通用知识记忆、长期撤销历史或数据库驱动的行为召回；
- 自动规则压缩、过期清理、LRU、后台 GC 或未经确认的语义归并；
- 自动审批、语义 Hook、transcript/compact summary 恢复；
- 自动 Git 发布或跨设备实时同步；
- task/transcript、Host Profile、Scheduled 状态、未确认 Review Pack 或运行计数的跨设备同步；
- Ambient discovery 的稳定产品承诺；
- 用 release harness、诊断报告或 SQLite 行创造行为事实。

## 重新决策条件

只有当 Codex 原生能力同时提供明确授权、确定作用域、must-apply 语义、可审计撤销和可验证分发时，才重新
评估移除 Sidecar。任何平台变化先更新本层，再改变 L2/L3 或代码。
