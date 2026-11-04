# Agent Memory L1 设计公理

- Status: active
- Owner layer: project_docs
- Applies when: 设计、评审或变更 Agent Memory 的产品目标、行为权威、授权、隐私、证据或发布边界。
- Avoid when: 只执行普通项目工作或不改变机制语义的机械修改。
- Last verified: 2026-09-01
- Evidence: 用户批准的 Agent Memory Core v1 与条件可见终态闭环设计、[Core v1 ADR](../decisions/0057-agent-memory-core-v1.zh.md)、[Runtime storage policy ADR](../decisions/0058-persistent-runtime-journal.zh.md)、[有界规则集演化 ADR](../decisions/0059-bounded-behavior-set-evolution.zh.md)、[周期性 Global Owner Scout ADR](../decisions/0060-periodic-global-owner-scout.zh.md)、[直接可见审阅包 ADR](../decisions/0063-direct-visible-owner-review-packs.zh.md)、[中文双投影审阅包 ADR](../decisions/0064-chinese-contextual-dual-projection-review-packs.zh.md)、[主机感知动态项目注册 ADR](../decisions/0065-host-aware-project-enrollment.zh.md)、[执行与可见输出完整性 ADR](../decisions/0066-scout-execution-and-visible-output-integrity.zh.md)、[生产执行源激活门禁 ADR](../decisions/0067-scout-production-source-activation-gate.zh.md)、[用户主动触发主路径 ADR](../decisions/0068-interactive-project-scout-primary.zh.md)、[跨设备冷启动连续性 ADR](../decisions/0069-cross-device-cold-start-continuity.zh.md)、[原子规则包 ADR](../decisions/0070-atomic-review-pack-rule-bundles.zh.md)、[所见即所签与物理 containment ADR](../decisions/0071-wysiwys-review-pack-bundles-and-physical-target-containment.zh.md)、[白名单公开分发 ADR](../decisions/0072-allowlisted-public-distribution-lane.zh.md)、[公开工程权威切换 ADR](../decisions/0073-public-engineering-authority-cutover.zh.md)、[统一工作站调和 ADR](../decisions/0075-unified-workstation-reconcile.zh.md)、[任务级 Review Pack 交付 ADR](../decisions/0076-task-scoped-review-pack-delivery.zh.md)、[真实读回工作站调和 ADR](../decisions/0078-workstation-reconcile-v2-observed-state.zh.md)、[项目任务前门与确定性终态 ADR](../decisions/0079-project-session-front-door-and-scout-terminal-contract.zh.md)、[消费者可见 Skill 范围 ADR](../decisions/0080-consumer-visible-skill-scope-reconciliation.zh.md)

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
   在同一作用域已经表达的同义内容，不再复制为 managed rule；项目中仍有跨项目价值的通用行为继续比较实际 Global Owner。
2. **演化优先于累积**：新的纠正先判断是否覆盖、修订或归并现有规则；只有真正独立的行为增量才能新增。
3. **容量只提供背压**：单规则 1 KiB、managed block 8 KiB 是 Sidecar 的编辑预算，不是 Codex 文件限制；
   超限拒绝整次修订，但不触发 TTL、LRU、自动删除或后台 GC。
4. **规则集修订授权**：模型可以提出 `no-op`、新增、替换、归并或 owner 路由；删除或替换已有规则必须由
   用户授权精确的修改前状态和修改后规则集，确定性层只执行该修订。
5. **确认前可执行**：完整候选、拟选集合和长期规则集合分开判断。向用户提供确认命令前，复用 Core 实际规则规划器，
   针对该准确集合和当前 Owner 检查差量、冲突、容量及 before/after。未通过预演的集合保留有据候选和整理动作，
   不提供不可执行的全选确认，不静默裁卡、自动删旧规则、提高预算或分批追加绕过总容量。
6. **正式交付不降级**：普通单规则与规则包都先对准确 before/after 同时预演单条和整块容量。容量不足不能把
   必需行为降级为可选 Memories、笔记或摘要；Owner 归属按内容职责判断，逐项保留义务、适用条件与例外。
   路由提议、正文落地、入口部署与后续采用分别取证。详见[完整容量预演与正式 Owner 交付](../decisions/0081-capacity-preflight-and-owner-delivery.zh.md)。

决策材料只保留一份精确规则正文；同卡的相同事实、动作或例外可引用该已显示内容，不重复展开。
独立来源中的每项有价值义务先取得准确去向，再形成用户需要决定的规则增量；归并产生新的内容绑定修订，
不改写既有冻结产物。交付状态与规则状态分别表达：文件内动作仅在当前任务交付就绪且对应预演仍有效时可执行；
排队或失败回执必须用中文说明确认尚未就绪，不能让用户自行解释协议字段。

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
- 可选分发：私有 Git 传播完整 global `AGENTS.md`；本机 target 才决定本机行为。按需同步可覆盖 Windows/macOS 的 Codex 与 Pi；同一源、同一提交、完整字节物化，各宿主分别保留本机 binding。该能力不安装 Pi Hook、不迁移 Scout、不证明新会话采用。详见[全局规范同步契约](../../specs/global-instruction-sync-v1.md)。
- 公开分发：只从白名单导出 Core 与版本化 Plugin/Skill；私有 Owner 是可选后端，不随源码或发行物公开。
- 公开演进：首发验收前私有工程仓库是唯一研发权威；明确切换后公开 `main` 接管全部公开研发与发行，私有工程仓库
  冻结归档。公开候选期不得解释为双 owner 或长期镜像。
- 可选背景：Codex Memories 可以关闭，不能改变强制规则行为。

## 外部项目复盘实验

Scout 是面向多个工程和环境的通用能力，Sidecar 是其实现与维护工程，不是目标工程模型。复用已接受的视觉与
交互语言，工程目标、角色、路径、工具、维护者和环境事实则从每次目标上下文取证；不得移植示例工程的业务链路。

用户可明确请求查看当前工程全貌，或复盘近期协作。查看只重建当前设计，不要求会话普查、Global Owner 整合或
Core 授权预演；复盘先重建用户目标到实际结果的完整路径，再核对近期经验。普通开发不因此触发 Scout。
两种结果都包含有来源的工程全貌，零新增建议不等于没有理解结果。模型、思考强度与时间由用户选择，
不以固定矩阵大小、建议数或模型档位代替审查深度。图谱是已有真理源的版本化解释，不能成为行为 Owner。

复盘深度必须同时包含活动工程知识覆盖与近期任务覆盖。30 天会话窗口不裁掉仍生效的规范、设计决策或验收。
本轮来源、事件、观察与卡片必须可追溯；高价值信号必须形成候选或说明准确的已有覆盖、项目归属、证据缺口和
不持久化理由。项目已沉淀规则后，仍须检查去掉局部实现细节是否存在独立通用行为增量；只有语义相同才去重。
零卡不能由空观察证明候选穷尽。有界复盘只声明已覆盖范围内未发现合格增量，不宣称工程不存在可复用经验。
确定性校验只证明关联与交付守恒；发现能力以不泄露答案的固定源样本及人工校准判断验收，未来采用另行验证。

Global Owner Scout 是用户显式触发的只读项目复盘，不是 Core 的后台治理能力。用户在当前绑定 Git 工程发送
`$global-owner-scout 复盘当前项目` 后，同一任务完成预检、30 天取证、审阅文件和结果链接；默认不创建新聊天或
worktree，用户已选的 worktree 原地沿用。前后完整项目指纹必须一致，包括未跟踪文件内容；并发变化只能按证据
归因，不能直接指称 Scout 写入。复盘不创建 proposal token、不修改 Store、Owner、Git 或外部系统，唯一输出写入
是当前宿主显式授予且位于项目外的不可变 artifact。Scheduled 仍是独立暂停的隔离实验。

该实验的正式激活集合由每台主机动态发现和人工确认，不由共享源携带固定项目名单。Project/global Owner、已提交
Skill 和工程事实属于 Git 可移植层；Codex `projectId`、绝对路径、Scheduled Task、运行计数与未确认 Review Pack
属于主机执行层。内容可移植性不得被冒充为主机激活，主机激活也不得反向成为第二行为 Owner。

Scout 从目标、质量要求与整体分工逐层追到实现、交接和演进原因；近期失败不是工程建议的唯一来源。
工程建议可以包含多层重构、整合、替代或删除方案，按证据、收益假设、代价和反例比较，不以改动大或尚无已接受变更
排除底层方案，也不为凑齐层级制造建议。用户逐层审阅，展示、讨论和实施资格分开；局部未知不阻断无关理解。

该实验分为证据面、呈现面与授权面：目标工程 `project_scout` 对项目事实、证据等级、因果关系、抽象与本地
owner 建议负责，并把同一 Project Card 分别投影为中文、保留业务语境的 Human Context 与精确、Agent 友好的
Rule Projection（仅规则候选）；工程建议保留方案、收益假设、代价、验证条件和实际维护归属，不伪造规则正文。
两者均由项目线程固定并进入内容 hash。只有规则候选随后生成独立 global owner
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
6. **完整证据与必要决策分开呈现**：全部合格 E2/E3 卡和来源保留在同任务不可变文件中。首层给出结论、
   需决定的真实行为增量及风险；已覆盖和无需持久化项不计待决、不要求逐项忽略，完整依据留供查阅。
   默认在当前对话给出总览并展开首项有据建议，完整文件按需打开。已有规范覆盖不等于实现或方法没有维护差异；
   对有据差异复用 Project Card 路由到现有项目或 Skill Owner，不因全局规则已覆盖而丢失，也不把观察全部变成待办。
   不因排序、摘要、容量或外部故障隐藏卡片；语义去重比较全部行为义务与例外，重组已有条款不构成新增规则。
7. **可见性与写入采用不同失败边界**：Session 索引或分页明确终态失败只能产生醒目的 `degraded` 警告，不得删除
    由 Owner、ADR、Git、测试或验收独立支持的卡；隐私、只读、完整性或 Owner parity 失败必须阻断相应写入动作。
8. **人工精确选择、所见即所签**：复盘输出始终是草案。用户可以一次选择同一 Review Pack、scope 和 target 的
   一张或多张可确认卡；每张卡以 `card_id@selection_token` 绑定项目 claim、proposal、superseded 集合、target 与
   Fresh before。Agent 必须读取一次最新 owner、联合重算关系与聚合 before/after，并执行零或一次原子规则包修订；
   Core 必须证明当前回复完整绑定选中集合，只允许 canonical 确认文本或接口规范限定的 Markdown 分隔符转义表示。
   单卡是大小为一的规则包；不得循环复用 approval、
   沿用旧快照、按输入顺序解释集合或留下部分成功。
9. **资源策略随入口分层**：交互入口使用当前任务的宿主设置，不询问或覆盖 model/thinking；可观察时记录实际值。
   暂停的 Scheduled 实验保留其固定模型与滚动窗口，手动复盘不计入实验次数。
10. **零背景状态**：不得增加候选 Inbox、transcript parser、长期候选数据库、后台规则 GC 或第二行为 owner。
11. **证据不可跨级**：定时发现与文件写入不证明自然任务采用。采用和撤销必须由后续无答案泄漏的新任务验证。
12. **可移植安装与可选激活分离**：Bootstrap 安装并验证 Skill 后，所有具备原生绑定与输出授权的 Git 工程即可由用户显式
    触发，无需 Host Enrollment。只有用户明确要求 Scheduled 实验时才进入项目发现与 enrollment；共享 Prompt、
    Manifest 与 Owner 不得写入固定项目名、host `projectId` 或绝对路径。
13. **安全资格先于推荐**：Scheduled enrollment 以滚动 30 天自然任务判断 `active`，Git worktree 能力判断 `eligible`；
    专用 Scout、测试、自动化和委派任务不计入自然活动。交互复盘沿用当前 Local 或已选 worktree；混合任务保留自然
    工作 turns，排除复盘生成内容。来源不可证明时只能 bounded，非 Git 项目不得默认启用。
14. **原生工具必须取得终态**：任务索引或分页调用返回运行中 cell 时，必须恢复同一 cell 直到明确终态；未恢复、
    非法参数或执行序列中断属于 `execution_protocol_failed`。分页工具明确返回终态错误时使用
    `native_thread_pages_terminal_failure` 降级，并保留其他证据独立支持的卡；两者不得互相伪装。
15. **交付内容必须逐字守恒**：确定性 renderer、同任务不可变 artifact、完整字节读回和最终结果链接共同证明技术
    交付；不独立证明 UI 已展示或用户已理解。实际 final 的外部读回可增加证据，但不要求另建控制任务。
    交互 final 显示由同一文件校验的简明建议、链接与 compact receipt，完整证据留在文件；渲染失败不允许手写部分结果。
    默认不调用宿主打开工具，`not_requested` 只证明文件交付；按需打开排队或失败不阻断已验证内容的讨论。
    自然续问恢复对应原交付回执与当前讨论，不要求最新助手消息是回执，不重跑未变化的普查；获准维护沿现有工程链执行。
16. **Enrollment 不等于生产激活**：用户确认 `enabled` 只授权本机配置该项目，不证明 automation 当前 Active、
    原生任务索引可用或 Scheduled 生产链成立。恢复周期运行前必须由真实 `thread_source=automation` canary 在外部
    验收下取得终态；普通任务、fixture、Doctor 与安装 hash 不能替代。
17. **控制权不下放给只读 Scout**：Project Scout 只能输出证据与 Review Pack，不能修改 Host Profile 或
    Scheduled 状态，也不能以文字宣称已暂停。自动化的创建、暂停、恢复与删除由 Bootstrap / 当前交互任务的宿主
    激活控制面执行，并以工具调用后的实际状态复读为准。
18. **可移植内容不冒充主机能力**：仓库 Owner、已提交 Skill、冷启动 Anchor 与插件目录只证明远端可取得的内容；
    只有当前主机完成能力源同步、Core/global binding/Skill 物化、Doctor 后，才能声明交互入口已安装；模型自动加载与自然采用另行观察。
    当前主机 canary 不得外推为另一台机器已经具备相同能力。
19. **冷启动第一跳必须自包含**：任何明确加入跨设备连续性的工程必须携带极小 repo Anchor 或等价官方分发入口，
    使用户只需表达“同步并部署本机 Agent Memory”；不得要求用户记住 Sidecar checkout、canonical Owner 路径、
    project ID、项目名单或安装顺序。Anchor 只路由到唯一 Bootstrap 源，不复制实现或成为第二 Owner；经验证的 portable
    Bootstrap 可以在同一任务继续完成主机调和，不能再人为增加一次“先安装、下个任务再部署”的产品步骤。
20. **派生源与工作区分离**：Bootstrap 只原子更新 `$CODEX_HOME` 下身份固定、clean、可重建的受管源，不得为同步
    而 pull/reset/clean/覆盖 Desktop 活跃项目。项目集合仍由当前主机动态发现和用户决定，不由能力源仓库反推。
21. **公开分发与私有证据分离**：不得把带历史证据和主机痕迹的工程仓库原地公开。公开物必须来自默认拒绝的
    allowlist、commit-bound source manifest、许可证门和隐私扫描；`canonical_owner` 缺省只关闭 global 集成，
    不得阻断 project-scope Core 或创造替代 Owner。
22. **公开工程权威单一化**：独立公开仓库在首发资格完成前只是候选，不能与私有工程源同时拥有产品事实；只有
    公开 Release、干净安装、远端回读和单独人工确认全部成立后，公开 `main` 才成为唯一工程权威，私有工程仓库
    随即冻结归档。发布证据不得自动冒充权威切换，切换后不得继续私有导出或双向同步。
23. **可发现入口不等于安装权威**：公开 checkout、Marketplace 与 Release 页面只帮助定位能力；Anchor 必须验证
    stable immutable Release、tag/commit、资产 digest、checksums 与 manifest 后，才可把准确来源交给安装器。解析失败
    不得回退浮动 branch、私有工程源或人工猜测资产。安装后的 Skill 支持原生自动发现；未显示或宿主明确要求时才提示刷新，不将新聊天设为只读检查的
    前置条件，但主机 source sync、Core/Owner/Skill 物化与 Doctor 不得被推迟到第二个任务。
24. **换源是显式例外而非同步特权**：普通 source sync 永远拒绝 identity 变化；存量主机换到公开 Sidecar 必须先
    生成无写入计划，再由用户一次确认后以 fresh `plan_hash` 原子执行并失败恢复。公开 manifest 的
    `canonical_owner=null` 只表示发行物不携带 Owner：已有 Owner checkout 与 Core binding identity 完全一致时必须保持
    该独立后端；二者缺一、dirty 或 identity 不一致时阻断。移除 Owner 需要另一个明确决策。
25. **任务交付物不是状态或 Owner**：输出目录来自当前任务宿主的明确授权，先读环境 roots 与元数据再预检；
    不猜测 app-storage 路径，不写项目、临时目录、Store 或跨任务桥。`queued` 保留为 `surface_pending`，既不冒充
    opened，也不要求用户反复切窗口。后续准确的人类选择可在原 artifact 读回、Fresh Owner 和 Core 预演后恢复已有
    授权链；它不倒推旧 UI 已展示，不授权未选项。文件丢失、变化或授权不匹配仍拒绝写入。
26. **当前项目任务负责完整收口**：原生项目绑定与显式 `project-root` 确定证据上下文，不依赖 helper cwd。
    只读交互复盘不强制新聊天或 worktree；原生 active/archived history 均分页到冻结窗口边界或 EOF，页大小不等于
    总覆盖上限。正文容量错误可缩小同一请求恢复并保留失败记录；缺口不冒充完整，也不要求用户补交证据。
27. **失败终态不依赖成功产物**：任何发生在 Delivery manifest 之前的阻断必须通过
    `global_owner_scout_terminal_v1` 确定性渲染；不得手写恢复 Markdown，也不得调用依赖 manifest 的 receipt 路径。
28. **托管物化不冒充消费者范围**：用户级安装 exact 不能证明 Desktop 可见项目级同名 Skill exact。完整声明必须由
    本轮原生项目清单、原生有效 Skill 清单和只读内容检查界定；范围缺失返回 bounded，启用入口缺失返回 bounded，重复启用或内容差异返回 drift；停用项不计有效入口，不得自动修改项目 checkout。
    开发用 Bootstrap/Scout 源码位于非自动发现目录，正式安装副本才作为普通任务入口；不以工程版本对齐代替入口唯一。

该实验分层报告：技术实现与安装可独立交付；展示、自然发现、准确选择、后续采用及用户成本只有实际观察后才成立。
未取得真实体验证据时保留未证，不制造更多测试聊天或要求用户配合。Scheduled 的执行源资格与暂停状态独立维护；
不新增文件队列、候选数据库或 transcript parser。当前机制与旧入口的区别见 [ADR 0079 修订](../decisions/0079-project-session-front-door-and-scout-terminal-contract.zh.md)。

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

证据要求不产生执行授权。机制开发、验证或方案确认不授权更新正式 Global Owner；写入、撤销和失败恢复的技术
验证使用隔离的 Owner、Store 与测试事件。正式使用由用户主动触发，只有对应具体规则、作用域和变更的确认才进入
写入链；用户将真实验收留到后续时，不得借用此前候选认可或开发确认继续正式写入。
必要技术验证通过即可交付相应机制改动，真实体验、自然任务采用和收益保留为用户后续验收的独立结论。
未观察到高层证据不构成低层实现失败，也不要求 Agent 为补齐证据主动制造正式变更或追加验收任务。

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
