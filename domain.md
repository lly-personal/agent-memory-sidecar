# Agent Memory Core v1 领域词汇

- Status: active
- Owner layer: project_docs
- Applies when: 命名 Agent Memory 的产品、规则、授权、运行时、作用域、状态与证据。
- Avoid when: 只需执行普通项目工作。
- Last verified: 2026-09-01
- Evidence: [L1](docs/specs/axioms.md)、[L2](docs/specs/topology.md)、[L3](docs/specs/interface.md)、[ADR 0057](docs/decisions/0057-agent-memory-core-v1.zh.md)、[ADR 0059](docs/decisions/0059-bounded-behavior-set-evolution.zh.md)、[ADR 0069](docs/decisions/0069-cross-device-cold-start-continuity.zh.md)、[ADR 0070](docs/decisions/0070-atomic-review-pack-rule-bundles.zh.md)、[ADR 0071](docs/decisions/0071-wysiwys-review-pack-bundles-and-physical-target-containment.zh.md)、[ADR 0072](docs/decisions/0072-allowlisted-public-distribution-lane.zh.md)、[ADR 0073](docs/decisions/0073-public-engineering-authority-cutover.zh.md)、[ADR 0076](docs/decisions/0076-task-scoped-review-pack-delivery.zh.md)

本文件只统一当前 Core v1 语言，不定义额外行为。字段名、协议名与 CLI 标识保留英文。

## 产品与行为

- `confirmed_rule`：用户明确授权、通过七字段校验并绑定一次性 approval 的协作规则。
- `bounded_behavior_delta_set`：相对于当前全局与项目 authority 仍然必要、位于一个 target managed block
  中的已确认规则集合；它不是会话历史或只增不减的事件日志。
- `rule_id`：由持久规则内容确定性派生的标识；规则内容变化会产生新 ID。
- `instruction_target`：规则的原生行为 owner，只允许 `project_agents` 或 `global_agents`。
- `managed_instruction_block`：`AGENTS.md` 中由 Agent Memory 管理的有界规则区块；区块外字节归用户或其他 owner。
- `deployed_rule`：能从实际 instruction target 解析、内容与 ID 一致且未被非空 `AGENTS.override.md` 屏蔽的规则。
- `publication_required`：global source 与本机 target 已完成本地双目标事务，但私有 Git 尚需 commit、push 和远端验证；它不是规则状态。

## 提案与授权

- `seven_field_proposal`：精确包含 `trigger`、`action`、`skip_boundary`、`scope`、`why`、`evidence`、`instruction_target` 的 canonical JSON。
- `rule_relation`：Agent 对候选与当前 authority/规则集关系的本轮分类，只允许
  `already_covered`、`add`、`replace`、`consolidate` 或 `route_to_owner`；不写 Store。
- `rule_revision_v1`：绑定 seven-field proposal hash、instruction target、修改前完整文档 hash 与排序后
  superseded rule IDs 的一次原子规则集修订 identity。
- `rule_revision_bundle_v2`：把同一 scope/target 的一个或多个唯一 seven-field proposal、各自 superseded IDs、
  card/project claim、可见 selection token、完整 target before/after 与 canonical 确认回复绑定为一次无序原子规则包
  identity；单卡是大小为一的规则包。
- `selection_token`：Review Pack 中公开、确定性、128-bit 显示的操作 identity；它绑定卡片与 Fresh 修订，不是秘密、
  proposal token 或长期凭证。
- `approval_ref`：当前有界 prompt event 的 opaque 引用，用于一次确定性授权消费；不是长期凭证。
- `proposal_token`：最多保留 24 小时、只保存 proposal 或规则集修订 hash 的待确认能力；不保存 proposal、
  target 文档、prompt 或回复正文。
- `clarification_draft`：显式“记住”仍有推断时展示的草案；它不创建 token，也不产生 `待确认`。
- `ambient_capability`：Hook 传输的固定、prompt-independent 能力说明与当前 opaque event ref；它不做语义判断。
- `ambient_discovery`：Agent 在任务完成后发现高价值规则并最多展示一张建议卡的实验能力；未证明时不阻塞 Core。

## Scope 与分发

- `primary_folder`：Codex Desktop 多文件夹项目中决定项目指令、Skill、配置和 project scope 自动发现边界的主文件夹。
- `secondary_folder`：可访问资源，但不改变 project scope 或 instruction owner。
- `project_content_identity`：由规范化 Git remote identity 与 primary folder 仓库内相对位置派生的隐私安全标识；
  用于跨设备识别同一内容工程，不包含本机路径或 Codex `projectId`。
- `host_project_id`：当前 Codex Desktop 对本机项目的执行标识；只用于当前主机绑定，不进入 Git 或跨设备 identity。
- `host_enrollment`：用户确认当前主机是否为一个已发现项目运行 Global Owner Scout 的本机配置；不是行为 Owner。
- `project_session_front_door`：当前绑定 Git 项目任务中的唯一 Scout 用户入口；负责显式意图、Fresh 项目绑定、Git
  资格、执行上下文 preflight 与自动隔离路由，不负责在 Local 执行项目深挖。
- `isolated_review_executor`：由宿主从项目任务自动投影的 worktree 任务；继承同一正式调用并完成只读 Project Scout，
  不要求用户重复项目、路径或 prompt。
- `enrollment_pack`：Bootstrap 对本机项目发现、自然活动覆盖、隔离资格、现有状态和建议动作的中文确认界面。
- `task_review_artifact`：当前 Scout 任务在宿主显式 generated-output root 中创建的不可变完整 Review Pack；它位于
  被复盘项目外，只在当前任务展示，不被跨任务发现或摄取，不是 Store、Inbox、数据库、Manifest 或行为 Owner。
- `scout_delivery_manifest`：`global_owner_scout_delivery_v1` 的紧凑控制面；绑定 task artifact 的名称、字节 hash/长度、
  Review Pack/body hash 与卡片/动作守恒，不包含绝对路径、任务 ID、Owner 正文、项目证据正文或长期状态。
- `scout_terminal_result`：`global_owner_scout_terminal_v1` 的 manifest-free 失败控制面；在完整 Review Pack 尚未形成时
  绑定 phase、reason、项目状态与不可确认结果，不是部分 Review Pack、Delivery manifest 或长期状态。
- `repo_bootstrap_anchor`：连续性工程内的极小冷启动 Skill；验证不可变发行物并从安全展开的 portable 在同一任务
  调用正式 Bootstrap，不复制实现、不保存主机状态，也不是行为 Owner。
- `managed_capability_source`：当前 Codex home 下 identity 固定、clean、可重建的 Sidecar 或 canonical Owner 安装
  快照；不等同于活跃项目工作区或行为 Owner。
- `deployment_pack`：按可移植分发、源同步、主机物化、项目激活四层展示本机部署事实的中文回执；前一层不能
  证明后一层。
- `portable_global_instruction_source`：私有 Git 中完整 global `AGENTS.md` 的 canonical source；负责跨设备分发，不决定本机生效。
- `global_instruction_binding`：本机保存的 source path、commit 与完整文件 hash 元数据；用于漂移校验，不保存规则正文。
- `global_instruction_parity`：canonical source 与本机 global target 的完整文件 hash 相同；它只证明文件分发一致性。
- `public_source_export`：从私有工程仓库的显式 allowlist 重建公开源树的单向第一阶段；记录工程 commit，不复制 Git
  历史，未选中文件留在私有源；它只用于首发引导和 provenance，不是长期同步协议。
- `public_release_build`：只在独立公开仓库的版本 ref 精确指向 HEAD 后生成并验证 release artifacts 的第二阶段。
- `engineering_authority_epoch`：公开产品当前唯一工程事实源，只允许 `private_engineering`、`public_candidate` 或
  `public_active`；前两者的 owner 都是私有工程仓库，后者的 owner 唯一变为公开 `main`。
- `public_authority_cutover`：在公开 artifact 安装、公开发布回读和单独人工确认均成立后，把公开产品工程权威从
  私有仓库一次性切换到公开 `main`，并冻结归档私有工程仓库的治理动作；不是 Core runtime mutation。
- `public_authority_marker`：`public_active` 后由公开仓库跟踪的 `agent_memory_public_authority_v1` provenance 文件；
  它绑定首个公开 Release 和原始工程 snapshot，但不自行授权切换，也不是行为 Owner。
- `release_resolver`：Anchor 内只读解析 stable immutable GitHub Release 的确定性消费者；同时验证 tag/commit、asset
  digest、checksums、release/source manifest 与 portable，并把普通文件安全展开到临时解析目录；失败不回退。
- `workstation_reconcile`：fresh、同 identity 更新与 legacy 换源共享的单一主机部署模型；用户只表达一次部署目标，
  仅在 Sidecar identity 变化时看见一份短计划并确认一次，随后原子 source/host 物化并得到一份分层回执。
- `source_authority_cutover`：存量主机以无写入 plan 和 fresh `plan_hash` 把受管 Sidecar identity 显式切到公开
  Release 的 `workstation_reconcile` 内部事务；不放宽普通 sync，也不隐式移除私有 Owner。
- `source_manifest`：把 Sidecar 和可选 canonical Owner 的 credential-free remote、ref 与完整 commit 绑定的安装输入。
- `core_public`：不携带 canonical Owner 的公开安装 profile；project scope Core 可用，global 集成明确 unavailable。
- `owner_integrated`：宿主另外提供 commit-bound 私有 Owner 后启用 global binding 的安装 profile。
- `public_artifact_verified`：公开导出物在本地完成内容、hash、包安装和入口 smoke；不代表已经公开发布。
- `public_install_verified`：从已构建 Release 形态在干净环境安装并执行真实入口；不代表新任务采用、连续性或工程权威切换。
- `public_published`：经明确外部授权后回读到公开仓库、Tag、Release 或 registry 状态；不代表 `public_active`。

## Runtime 与 Store

- `Runtime Ledger`：拥有 `prompt_events`、`runtime_sessions` 与 `proposal_tokens` 的有界运行时记录层。
- `Authorization Ledger`：拥有一次性 `approval_consumptions`；不保存规则历史。
- `Installation Registry`：拥有 immutable runtime identity 与 global binding；不决定行为状态。
- `immutable_runtime`：按内容 SHA-256 寻址的 zipapp；Desktop Hook 只指向该 artifact，不从 editable checkout 加载。
- `maintenance_lock`：Core cutover 期间旧新 Hook 均识别的短期锁；存在时 Hook fail-open。
- `core_cutover`：经 dry-run 和新授权后，把 legacy Store 重建为 Core v1 七表 Store 的一次性维护操作。
- `physical_target_containment`：在解析和写入前拒绝逻辑 owner 控制面内的 link/reparse、非普通文件与多硬链接，
  证明 owner 没有被用户或仓库可控制的文件系统别名导向授权边界之外；操作系统拥有的顶层目录映射不等同于 owner 漂移。

## 用户状态

- `待确认`：当前 scope 存在未过期 proposal token。
- `生效中`：规则是实际 target 中未被 override 屏蔽的 `deployed_rule`。
- `已停用`：撤销当次结果，或 target 中仍存在但被 override 屏蔽；删除后的规则不进入长期停用列表。

SQLite 历史行、Git commit、Hook 输出、Memories 召回和 Agent 自述都不能单独决定上述状态。

## 证据语言

- `configured_readiness`：配置、schema、artifact 与安装记录一致。
- `native_ingress`：Desktop 原生事件进入 Hook。
- `transport_observed`：有界 capability 被送达。
- `instruction_deployed`：实际 instruction target 已通过解析和漂移校验。
- `model_adoption_observed`：新 Desktop 任务的可见行为采用规则。
- `continuity_observed`：后续任务采用且撤销后的新任务不再采用。
- `cross_host_bootstrap_proven`：真实另一设备从同步后的连续性工程完成首次能力加载、Doctor 与交互 Scout canary；
  当前主机空 profile 或临时目录测试不属于此证据。
- `product_effect_observed`：证据显示未来重复说明或纠正成本实际下降。
- `delivery_prepared`：确定性 Review Pack 已创建为 task artifact、完成同文件回读并生成有效 Delivery manifest；只证明
  交付准备，不证明宿主已展示、用户可见或 Production 可用。
- `surface_pending`：宿主明确返回 `queued` 后，实际 task final 保留经 Delivery manifest 绑定的 artifact 链接，外部
  controller 已复核字节、hash、卡片和动作守恒；只证明完整内容可发现，不证明用户已打开，确认关闭且不计 Production。
- `surface_observed`：外部 controller 从实际任务结果回读 compact receipt，并验证同任务 artifact 字节与 Delivery
  manifest 一致；内部 verifier、文件存在、宿主 open 调用或模型自述都不能单独证明该层。

证据不可跨级。Doctor、单元测试、Hook 自检、文件 parity 或 SQLite 记录都不能冒充模型采用。
