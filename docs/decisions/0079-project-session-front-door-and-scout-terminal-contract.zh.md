# ADR 0079：项目任务入口与确定性 Scout 交付

- 状态：Accepted
- 日期：2026-09-01
- Owner layer：user / project_docs
- 扩展：[ADR 0068](0068-interactive-project-scout-primary.zh.md)、[ADR 0076](0076-task-scoped-review-pack-delivery.zh.md)；
  当前入口与恢复策略以 2026-11-03 修订为准，原自动投影决策保留溯源。
- 平台依据：[Codex Git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)

## 2026-11-03 修订：复盘后的建议与当前对话续接

真实复盘交付了约 90 KB 的完整报告，九张通用规则卡全部已有覆盖，另有十八条项目、方法或未证观察。
用户继续要求沉淀建议时，答复却停留在已有覆盖与修复路线，没有把结论变成可讨论的具体变化。
文件完整性与报告完成因此不足以证明协作完成。进一步取证发现：全局已有覆盖可以吞掉有据项目维护动作；
固定回执没有建议正文；恢复说明只认最近 final；正文说明 Scheduled 未验范围也会被整包拒绝。

采用当前对话、原生历史及按需文件预览。默认总览并展开首项建议，完整报告按需打开；已有覆盖且无差异的项
不制造决定。项目/方法的真实维护差异复用现有卡片，质疑与澄清优先，不新增候选类型、数据库或治理入口。
摘要同时保留当前集成动作和原因；失败终态不能显示成零增量。建议只消费已通过 manifest 校验的同一份字节，
不在校验后重读另一份文件。旧 opened/queued 回执保持只读兼容。新 not_requested 只证明文件交付，预览失败不阻断讨论。

隐式选择仅用于可识别的既有 Scout 报告续接；普通工程任务不开始新复盘。恢复时从原生历史找到所讨论报告的
原交付回执，不要求最近助手消息恰好是回执。讨论、修改建议和选择归属不授予项目写入；已有明确实施授权
覆盖具体变化时沿现有工程链继续。全局规则仍需准确内容、Fresh Owner/Core 和真实批准。

技术回归先复现再修复动作丢失、缺少默认交付入口和正文误伤；同时验证失败/澄清状态、零增量、旧回执、
摘要篡改与校验后文件替换。固定同源输入的消融结果：旧版及仅改指引仍拒绝 not_requested；仅改呈现可恢复文件，
却仍忽略维护动作；完整候选保留 keep_project、首项建议与 artifact_verified，且不出现全局确认权限。
这些测试通过现有 CLI 和临时隔离目录执行，不是用户体验观察。

另以同一宿主继承设置对四种指引/实现组合前向评估 F1–F5。旧版也能给出合理续接，因此不能声称语义准确率提升。
首次完整候选曾把“按推荐先修改”误解为直接写项目；保留该失败，补清“继承已展示动作”的边界后，独立复验回到
调整建议而不写文件。模型回放只证明该固定样本下的拟议行为；实际展示、理解、自然采用、撤销、Windows 实机及
整段交付提速仍未证明。语料和评分沿既有 discovery evaluation 维护，不要求用户再做验收测试。

## 2026-11-02 修订：同任务收口与按需恢复

真实运行证实了四个断点：创建 executor 后前门停止，用户必须追问结果；最近 50 项索引未覆盖 30 天；
Windows 执行者漏读已授予的输出目录，并因从 Skill 目录执行而误判 Git 上下文；已核实的宿主实现只返回
`queued`，因此重复要求前台打开不能取得旧契约期待的 opened 终态。另有已覆盖卡片被列成待决定项，
把取证完整性转化成了不必要的用户决策量。纠正一次运行不等于产品修复或自然采用。

本修订替代下文的强制新任务投影与固定单页索引要求，其余授权、只读和内容守恒约束保留：

- 交互 Scout 在当前绑定项目任务只读完成，沿用已有 Local/worktree，不默认创建任务或 worktree；
  `inspect-context --project-root` 显式绑定当前项目，前后指纹不一致则不声明稳定复盘结果。只读任务不需要新的执行控制面。
- 先读当前任务的环境授权与宿主元数据，再做输出预检；目录不存在或来源不能证明时仍早停，不根据路径模式猜测授权。
- 复用原生 active/archived history 游标，分别到 30 日边界或 EOF，再读取选中自然任务；页大小不充当总覆盖上限。
  明确容量错误允许缩小同一请求后读回，保留首次失败；不能恢复的范围诚实降级。
- 单一不可变审阅文件仍保留全部证据。首层仅列有实际行为增量的决策；已有覆盖或无需持久化的项进入参考部分，
  不要求用户逐项忽略。新增规则必须指出现有条款无法覆盖的具体行为，不能把现有原则的重组当作增量。
- `queued` 只证明打开请求受理，不能证明已展示。技术收口包括文件读回和结果链接，展示与自然采用另列未证。
  现有 `verify-final` 负责从原回执恢复准确文件和 manifest；不能重跑发现、改写旧文件或伪造 opened。
  用户后续明确选择原包中的准确条目时，先核对原文件、当前 Owner 与准确选择，再进入已有 Core 原子预演和授权链；
  该动作不把历史 queued 升级为已展示，也不授权未选规则。

依据：原生 history/read_thread 游标实测；Windows 安装包中打开 handler 的只读核查；两端实际任务与产物读回。
[OpenAI 的 Skill 精简建议](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)、
[Tw93 的上下文工程实践](https://tw93.fun/2026-03-12/claude.html)支持按职责拆分与减少冗余上下文；
[渐进呈现原则](https://www.nngroup.com/articles/progressive-disclosure/)支持先呈现必要决定，再提供完整依据。
这些外部材料帮助选择方案，不证明本工程性能、展示成功或用户决策成本已下降。验收采用隔离回归与真实既有失败读回；
不新增用户配合测试，不以组件加速代替完整旅程收益。

### 消融与验收依据

- 同一固定场景下，独立执行者分别前向评估旧版和候选版：旧版因额外新聊天授权及排队恢复断点停止；候选版可描述同任务交付与准确选集恢复。仅属模型协议演练，不是实际 Desktop 完成时间对比。
- 两版对九组固定语义来源均保留了必要增量和例外，正确处理既有条款合取与部分覆盖。因此本次不能声称去重准确率提升；该材料进入已有 discovery evaluation，持续检验误增和误删。
- 原生历史探针以小页完成活动、归档两分区的游标读取，共 7 页、59 条不重复记录；这证明分页入口可用，不等于项目 30 天正文已全部读完。混合工程/复盘会话必须保留自然工作 turns。
- 回归先复现再修复显式目录、失败索引冒充上限、未跟踪链接改向和原确认绑定丢失；随后只保留 artifact 与 receipt，调用隔离安装的 Core 完成准确预演。未写正式 Owner。
- 移除强制 executor/controller，不新增队列、数据库或状态机。完整证据和准确授权仍保留；没有以减少卡片数代替内容完整，也不把旧报告恢复等同新报告的完整绑定恢复。

维护继续使用当前 L1/L2/L3、Delivery 契约、现有测试与发布/Bootstrap 链路。历史副本或项目级同名 Skill 不能凭安装回执宣布一致；必须核对实际被加载的身份，保留未核查入口。真实显示、理解、一次确认、后续采用与撤销，以及整段等待时间和人工介入的改善仍待自然使用证据，不因此要求额外测试聊天。

## 原决策背景（保留溯源）

真实项目任务验收暴露了三个相互放大的断点：正式入口要求用户先自行新建 worktree；Skill 在执行十余分钟后才检查
当前环境；没有 host output root 时，失败回执又要求先拥有一个成功的 Delivery manifest。另一个原生任务分页终态
错误虽然只截断部分 Session 覆盖，当前枚举却只能把它压成整个 `execution_protocol_failed`，从而删除已经由项目
Owner、ADR、Git、测试或验收独立支持的卡片。

这不是安装漂移：现场安装的 Skill 与 helper 字节和公共源一致。它证明设计把隔离实现、用户入口、覆盖分类和交付
终态分给了用户、模型自由文本与多个 helper，缺少一个可执行的前门状态机。

官方 Codex 文档把 Local 定义为前台、worktree 定义为互不干扰的独立 checkout，并说明 Codex 可以从当前分支连同
未提交变化创建 managed worktree。由此，worktree 是执行隔离原语，不应成为用户必须提前理解和完成的业务前置。

## 决策

### 一个用户入口，两个内部角色

正式调用仍然只有 `$global-owner-scout 复盘当前项目`，但允许用户直接在当前绑定的目标 Git 项目任务中发送。
入口先执行前置 preflight，且必须发生在任务索引、线程分页、Owner 比较和项目深挖之前：

1. Fresh 解析当前 Desktop 项目绑定、Git 资格、当前 Local/worktree 上下文与只读基线；
2. 通过 `python -B scripts/scout.py inspect-context` 生成无路径 `global_owner_scout_preflight_v1` Git/只读快照；
3. 已在独立 worktree 时原地继续；
4. 该正式调用授权恰好一个只读 executor；位于 Local 时使用宿主原生项目任务创建能力，把当前 working-tree state 与
   同一正式调用作为初始 prompt 自动投影到隔离任务并继续，用户不重复输入；
5. 宿主没有该能力、项目非 Git 或绑定不可验证时，在 preflight 直接返回确定性阻断终态。

投影成功后，前门任务只返回宿主原生 created-task surface，使用户可直接进入唯一 executor。它是 `routed` 证据，
不是复盘完成、Review Pack 已形成或用户表面已验收的证据；完整结果只在 executor 任务产生。

原项目任务是 `project_session_front_door`，负责意图、项目绑定和自动路由；隔离任务是
`isolated_review_executor`，负责完整只读复盘与 Review Pack。不得创建需要二次续传的空子任务、用 shell 手工创建 worktree、猜测路径或要求用户
复制 prompt。Local 中不得先运行部分 Scout 再晚检查 worktree。

### 覆盖错误按消费者精确降级

`native_thread_pages_terminal_failure` 表示任务索引已取得终态，但至少一个已选择自然任务的分页返回明确终态错误。
它要求 `status=degraded`、`truncated=true`、`fully_read_task_count < selected_task_count`，并保留由其他正式证据独立
支持的卡片。未恢复运行中 cell、非法参数或执行序列中断仍是 `execution_protocol_failed`；该状态可以保留此前已经
证明的 index 终态，但不得声称线程分页完成，也不得生成卡片。

### pre-manifest 失败也有确定性终态

新增 `global_owner_scout_terminal_v1`。它精确包含：

```text
contract_version, status, phase, reason_code, project_state, confirmation_eligible
```

它只表示本次没有形成完整可确认 Review Pack，`confirmation_eligible` 固定为 `false`。任何发生在 Delivery manifest
形成之前的 preflight、Session 协议、隐私/契约、只读、output root、renderer 或预算阻断都必须把该对象交给活动 runtime dispatcher 的
`render-terminal`，不得手写 Markdown，也不得错误调用需要 Delivery manifest 的 `render-receipt`。
manifest 形成后的 queued/opened/host-open failure 继续使用 manifest-bound receipt，不能倒流到 Terminal v1。

### 一个活动 helper 前门

Skill 的所有活动 Python 操作只通过 `python -B scripts/scout.py <operation>`。dispatcher 复用现有 validator、Owner
resolver、renderer、visible verifier 与 delivery 实现；冻结的 v4 文件仅作为明确的历史兼容路径保留。模型不再从
多个相邻脚本名推断下一步入口。

## 验收

1. Local clean、Local dirty、已在 worktree 三种入口都在任何任务索引前完成 preflight；前两种自动投影，后一种原地执行。
2. 用户只发送一次正式调用；内部隔离任务不得要求重述项目、路径、版本、候选或协议。
   前门的 created-task surface 只报告路由，不升级复盘结果层。
3. 明确 thread-page 终态失败生成 degraded Review Pack，并守恒其他正式证据支持的卡片；未终态/非法调用仍失败且无卡。
4. 缺少 output root 或早期失败不依赖 Delivery manifest，能生成可验证、无路径、不可确认的 Terminal v1 receipt。
5. Skill 活动文档只调用 `scout.py`；旧 helper 仅由 dispatcher 或兼容实现引用。
6. Source/测试通过不证明安装或模型采用。commit-bound Bootstrap 安装后，必须用新的真实 Desktop 项目任务分别验证
   Local clean、Local dirty、already-worktree、thread-page failure 和 missing-output-root 五条垂直切片。

## 非目标与回滚

本决策不允许项目内报告文件、系统临时目录 fallback、长期 Review Pack 状态、跨任务文件桥、自动确认、Owner 写入或
Scheduled 激活。若宿主缺少自动 worktree fork，入口诚实阻断，不把用户手工建 worktree重新定义为产品成功路径。
回滚必须同时恢复 L1/L2/L3、Skill、dispatcher、Terminal v1 和覆盖枚举；只删除某一层会重新制造心智断裂。
