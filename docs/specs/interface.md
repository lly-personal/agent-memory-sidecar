# Agent Memory L3 接口规范

- Status: active
- Owner layer: project_docs
- Applies when: 实现或验收规则、proposal、状态、CLI、失败反馈和迁移操作。
- Avoid when: 判断产品公理或组件所有权；读取 [L1](axioms.md)与 [L2](topology.md)。
- Last verified: 2026-08-14
- Evidence: 用户批准的条件可见终态闭环设计、[Core v1 ADR](../decisions/0057-agent-memory-core-v1.zh.md)、[有界规则集演化 ADR](../decisions/0059-bounded-behavior-set-evolution.zh.md)、[周期性 Global Owner Scout ADR](../decisions/0060-periodic-global-owner-scout.zh.md)、[直接可见审阅包 ADR](../decisions/0063-direct-visible-owner-review-packs.zh.md)、[中文双投影审阅包 ADR](../decisions/0064-chinese-contextual-dual-projection-review-packs.zh.md)、[主机感知动态项目注册 ADR](../decisions/0065-host-aware-project-enrollment.zh.md)、[执行与可见输出完整性 ADR](../decisions/0066-scout-execution-and-visible-output-integrity.zh.md)、[生产执行源激活门禁 ADR](../decisions/0067-scout-production-source-activation-gate.zh.md)、[用户主动触发主路径 ADR](../decisions/0068-interactive-project-scout-primary.zh.md)、[跨设备冷启动连续性 ADR](../decisions/0069-cross-device-cold-start-continuity.zh.md)、[原子规则包 ADR](../decisions/0070-atomic-review-pack-rule-bundles.zh.md)、[所见即所签与物理 containment ADR](../decisions/0071-wysiwys-review-pack-bundles-and-physical-target-containment.zh.md)、[白名单公开分发 ADR](../decisions/0072-allowlisted-public-distribution-lane.zh.md)、[公开工程权威切换 ADR](../decisions/0073-public-engineering-authority-cutover.zh.md)

## 七字段提案

进入授权或 proposal hash 的 payload 必须精确包含：

```json
{
  "trigger": "何时适用",
  "action": "未来执行什么",
  "skip_boundary": "何时不得应用",
  "scope": "project",
  "why": "为什么值得减少未来重复成本",
  "evidence": "当前任务中支持该规则的可验证事实",
  "instruction_target": "project_agents"
}
```

- `scope=project` 必须对应 `project_agents`；`scope=global` 必须对应 `global_agents`。
- 七字段 canonical JSON 的 SHA-256 是规则内容 identity；需要修改 instruction target 时，授权与
  proposal token 绑定下节定义的规则集修订 hash。
- 持久 instruction 只写 `When / Do / Skip` 和派生 `rule_id`。
- 单条渲染后上限 1 KiB；含 marker、heading 和换行的完整 managed block 每 target 上限 8 KiB。
- 8 KiB 只约束 managed block；完整 `AGENTS.md` 字节数只报告，不作为 Sidecar 修改块外正文的理由。
- `why`、`evidence`、原始 prompt 和回复不进入长期 Store。

## 规则集修订

规则集修订是对一个 instruction target 的一次原子 before/after 变更。canonical
`rule_revision_v1` hash 必须绑定：

- 七字段 proposal 的 canonical SHA-256；
- `instruction_target`；
- 修改前完整 target 文档 SHA-256；
- 去重并按字典序排序的 `supersedes` rule IDs。

`supersedes` 为空表示新增；一个 ID 表示替换；多个 ID 表示归并。所有 ID 必须存在于同一实际 target，
且不得重复。归并后的新规则插入最早被替换规则的位置，未被替换规则保持原顺序。

`rule_revision_bundle_v2` 是同一 instruction target 的一个无序原子规则包：

```json
{
  "contract_version": "rule_revision_bundle_v2",
  "target_before_sha256": "<64 lowercase hex>",
  "items": [
    {
      "card_id": "<review card id>",
      "project_claim_hash": "<64 lowercase hex>",
      "proposal": {"trigger": "...", "action": "...", "skip_boundary": "...", "scope": "global", "why": "...", "evidence": "...", "instruction_target": "global_agents"},
      "supersedes": [],
      "selection_token": "<32 lowercase hex>"
    }
  ]
}
```

- `items` 至少一项；`card_id` 与 proposal 必须唯一，所有项使用同一 scope/target。
- 每项 `supersedes` 独立排序去重；不同项不得覆盖同一个旧 rule ID，且所有 ID 必须存在于同一 Fresh before。
- `selection_token` 确定性绑定 card ID、project claim、proposal hash、排序后的 superseded IDs、instruction target 与
  完整 target before hash；确认文本固定为按 card ID 排序的 `确认 <card_id>@<token>[、...]`。
- Core 必须重算全部 token，并校验当前 approval event 的 prompt hash 与 canonical 确认文本完全一致；失败不消费 approval。
- bundle 先统一移除所有 superseded rules，再稳定插入全部结果；输入排列不得改变 after bytes、错误或 receipt。
- bundle revision hash 绑定 canonical bundle hash、instruction target、完整 target before hash 与完整 target after hash。
- 单卡确认使用大小为一的 bundle；任一项 no-op、stale、冲突、超容量或写入失败，整包零修改且不消费 approval。

Agent 在创建 proposal 前把候选分类为：

| 关系 | 行为 |
| --- | --- |
| `already_covered` | 已被实际规则或当前任务已读取的正式 owner 覆盖；不创建 token、不写文件。 |
| `add` | 真正独立的行为增量；`supersedes` 为空。 |
| `replace` | 修订一条现有规则；绑定一个 `supersedes` ID。 |
| `consolidate` | 用一条规则替换多条重叠规则；展示精确 before/after 后确认。 |
| `route_to_owner` | 项目事实、设计或状态应进入其正式 owner；不创建 token、不写 managed block。 |

该分类是 Agent 的本轮语义判断，不写 Store，不创造用户状态。无法可靠判断关系时只展示澄清草案。

## 公开 CLI

```text
agent-memory rule list [--target global_agents|project_agents]
agent-memory rule deploy --from-json <json-or-path> --approval-ref <ref> [--supersedes <rule_id>]...
agent-memory rule deploy-bundle --from-json <bundle-json-or-path> --approval-ref <ref>
agent-memory rule revoke <rule_id> --approval-ref <ref>
agent-memory setup [--apply]
agent-memory doctor
```

旧 `status/remember/forget` 不存在，也不提供兼容别名。编辑等价于带一个 `--supersedes` 的 deploy；
归并使用重复的 `--supersedes`，单值调用保持兼容。

内部实验入口：

```text
agent-memory proposal create --source-event <ref> --from-json <payload> [--supersedes <rule_id>]...
agent-memory proposal replace --source-event <ref> --from-json <payload> [--supersedes <rule_id>]...
agent-memory proposal confirm --approval-ref <ref> --from-json <same-payload> [--supersedes <same-rule_id>]...
agent-memory proposal discard --approval-ref <ref>
```

## JSON result

机器输出统一为：

```json
{
  "contract_version": "agent_memory_result_v1",
  "operation": "rule.deploy",
  "status": "ok",
  "scope": "project",
  "target": "project_agents",
  "data": {},
  "error": null
}
```

- 成功和幂等 no-op 返回退出码 `0`。
- 所有失败返回退出码 `1` 和非空 `error={code,message,details}`。
- 不允许 traceback、半个 JSON 或调用开始即成功。
- Global mutation 的 `data.publication_required=true` 表示 source 已更新但 Git 发布尚未由 CLI 证明。
- `rule list` 的 `data.targets` 对每个实际 target 返回
  `managed_block_bytes`、`managed_block_budget_bytes`、`remaining_bytes`、
  `document_bytes` 与 `rule_count`；完整文档字节数只用于可见性。

## 用户操作

### 普通工作

普通、未审计且没有合格规则时完全静默。已生效规则自然执行，不逐次播报记忆机制。

### 条件可见终态

以下任一条件使本轮进入可见 Agent Memory 流程：

1. 用户主动审计是否触发、保存或产生了可观测结果；
2. 用户明确要求记住一条未来规则；
3. Agent 识别出候选，或面向用户表示将使用、正在使用或已经使用 Agent Memory。

Agent 必须先完成当前任务。进入流程后，最终答复尾部必须有且只有一个真实终态；commentary、内部提醒、
Hook 输出、CLI 调用开始和将来时承诺均不算结果。尾部统一为：

```text
记忆检查：<状态>｜结论：<用户可读分类>｜动作：<实际动作>｜长期状态：<状态>
```

固定结果如下；花括号只允许填用户可读摘要，不得暴露 event ref、token、原始 JSON、命令或内部诊断标签：

| 场景 | 必须使用的最终尾部 |
| --- | --- |
| 主动审计但无候选 | `记忆检查：已完成｜结论：没有合格的可复用规则｜动作：未创建建议｜长期状态：未变更` |
| 实际 authority 已覆盖 | `记忆检查：已完成｜结论：当前规则已经覆盖｜动作：未创建建议｜长期状态：未变更` |
| 应进入正式 owner | `记忆检查：已完成｜结论：内容应归入{正式 owner}｜动作：未创建长期规则｜长期状态：未变更` |
| proposal create 成功 | 确认卡片最后一行使用 `记忆检查：已完成｜结论：发现新的可复用规则｜动作：已创建确认建议｜长期状态：待确认` |
| 显式 deploy 或 confirm 成功 | 回显最终 `When / Do / Skip / 范围` 后使用 `记忆检查：已完成｜结论：规则已部署｜动作：已写入{范围}规则｜长期状态：生效中` |
| 失败 | `记忆检查：执行失败｜结论：{已证明事实}｜动作：未保存或未部署｜长期状态：未变更` |

无动作回执只证明本轮分类被用户看见，不证明分类正确、内容持久化或后续行为采用。若关系无法可靠判断，
展示澄清草案，并以“需要澄清 / 未创建建议 / 未变更”终态结束。

### 显式记住

无歧义 utterance 是一次授权。Agent 回显最终 `When / Do / Skip` 与范围后直接 deploy；不增加第二次确认。
成功后必须使用上述部署终态。若内容已被 authority 覆盖，使用已覆盖终态；若任何字段或与现有规则的关系仍需推断，只展示
“澄清草案”，不创建 token、不写文件、不称为 `待确认`。显式请求没有授权额外删除时，Agent 不得借
容量压力静默归并。

### Proposal

- `create` 成功后才能显示一张建议卡，且卡片最后一行必须是 `待确认` 终态。
- `replace` 原子删除旧 token 并创建绑定修订内容的新 token。
- `confirm` 只接受当前 session/scope 的最新、未过期、proposal、target before hash 与
  `supersedes` 完全匹配的 token。
- `discard` 消费当前回复并删除 token，不写 instruction。
- token 缺失、过期、被替换或内容不同均不得降级为直接 deploy。
- Core v1 旧 token 若只保存七字段 proposal hash，只能继续确认 `supersedes` 为空的普通新增；
  不得在确认时附加编辑或归并目标。

### 查看、编辑、撤销

- `rule list` 只读取实际 target、容量和 pending token；不读取历史 memory。
- 编辑产生新 `rule_id` 并原子替换旧规则；归并在同一事务中替换全部具名旧规则。
- 撤销从实际 target 删除规则；当次返回 `已停用`，以后不建立可查询历史。
- Global 操作同时变更 source 与本机 target；Git push 是独立 distribution 维度。

## 状态

| 用户状态 | 唯一判定 |
| --- | --- |
| `待确认` | 当前 scope 存在未过期 proposal token。 |
| `生效中` | 规则在实际 target 可解析且未被 override 屏蔽。 |
| `已停用` | 撤销当次结果，或仍存在但被 override 屏蔽。 |

删除后的规则不再出现在后续列表。SQLite 行、Git commit、Hook 输出或 Agent 自述不能单独决定状态。

## 失败语义

任何失败都必须在保留当前任务结果的前提下使用条件可见失败尾部。proposal 或分类动作失败使用“未保存”，
deploy、edit、consolidate 或 revoke 失败使用“未部署”，新任务采用尚未观察到时使用“未证明”；不得先声称成功。

| 失败 | 必须结果 |
| --- | --- |
| payload/target 不一致 | `invalid_proposal`，未保存 |
| approval 缺失、过期、已消费 | `approval_invalid`，未保存 |
| Review Pack 回复、token 或 bundle 内容不完全一致 | `approval_content_mismatch`，未部署且不消费授权 |
| event/session/scope 不符 | `scope_mismatch`，未保存 |
| proposal 缺失、过期或 hash 不同 | `proposal_invalid`，未保存 |
| 与实际 target 中现有规则字节级相同 | `rule_already_covered`，不创建 token、不写文件 |
| supersedes 重复、缺失、跨 target 或与 token 不同 | `rule_revision_invalid`，未保存 |
| proposal 后实际 target 完整 hash 漂移 | `rule_revision_stale`，未保存 |
| instruction owner 内的 link/reparse/非普通文件/多硬链接 | `instruction_target_unsafe`，未部署且不消费授权；操作系统拥有的顶层目录映射不单独构成失败 |
| Store owner 内的 link/reparse/非普通文件/多硬链接或向未授权主体授予访问 | `store_unsafe` / `store_permissions_unsafe`，失败关闭；Windows 允许当前用户、SYSTEM 与 Administrators 的等价受信主体表示 |
| Skill 安装源或目标 owner 内的 link/reparse/非普通文件/多硬链接 | `skill_target_unsafe`，不复制、不替换、不删除 alias 指向的目录 |
| override、编码、权限或完整文件漂移 | 精确错误码，未部署 |
| 单条或 managed block 超限 | `instruction_capacity_exceeded`，返回 before/projected/budget，未部署且不消费授权 |
| 文件/数据库事务失败 | 恢复原状态并返回 `mutation_failed` |
| 文件存在但新任务未采用 | `instruction_deployed`、`adoption_unproven` |
| Global Git 未推送 | 本机可生效，但明确 `publication_required` |

## Global Owner Scout 实验契约

Global Owner Scout 的交互或 Scheduled 输出都是只读 `review draft`，不是 Core proposal。内部 Project Card 和用户可见
Review Pack 只存在于当前任务结果，不得写入 Store、文件 Inbox 或 `AGENTS.md`。

### Workstation Bootstrap 与 Host Enrollment

Repo/plugin 分发的冷启动 Anchor 固定识别：

```text
同步并部署本机 Agent Memory
```

Anchor 只负责使正式 Bootstrap 可发现。公开通道必须从 portable release 取得 root `source-manifest.json`，并只用其中
repository、immutable ref 与 full commit 安装 `.agents/skills/agent-memory-workstation-bootstrap` 与
`.agents/skills/global-owner-scout`；仓库 checkout、repo marketplace 或浮动 branch 本身都不是公开 source authority。
私有开发通道可使用显式 development manifest，但不得成为公开兜底。Anchor 不得要求 project ID、项目名单或资源配置，
不得复制完整实现，也不得在当前任务把新安装 Skill 冒充已加载。可靠加载边界是下一任务。

`agent-memory-workstation-bootstrap` Skill 1.6.0 提供两个显式模式：

- `inspect`：先同步受管 Sidecar/canonical Owner 源，再部署或验证 Core、global binding 与 versioned Skills；Skill
  安装通过后从下一任务保证交互 Scout 可用，无需 Host Enrollment。项目发现和
  `global_owner_scout_enrollment_pack_v1` 继续作为信息面；Scheduled 阻断时不得要求
  用户处理新的 enrollment 建议，也不得改变 Scheduled Task 或 Host Profile。
- `apply_enrollment`：只在用户明确要求复测或配置 Scheduled 实验时，消费当前 Enrollment Pack 的明确选择并原子调和
  `$CODEX_HOME/global-owner-scout/host-profile.json` 与对应 Scheduled Task。

`enabled` 只表示用户授权本机配置该项目，不表示 automation 当前 Active 或生产可用。`apply_enrollment` 为新项目
建立配置后必须先保持 `PAUSED`，再由当前交互任务中的 Host Activation Control 创建一个临时 standalone
automation-source canary。canary 只允许调用一次 `list_threads(limit=50)`；外部验收任务以 `wait_threads`/读取任务
状态观察最多 180 秒。只有明确终态才允许恢复一个 Project Scout canary。预算届满仍为 `inProgress` 时输出
`host_activation_blocked / native_index_non_terminal`，实际复读相关任务为 `PAUSED`，删除临时 automation，且不
改变用户 enrollment 决策。

Project Scout 是只读证据面，不得调用 Scheduled 管理工具、修改 Host Profile 或声称已暂停自己。创建、暂停、
恢复、删除的实际执行者只能是 Bootstrap / 当前交互任务的宿主控制面；每次变更后必须重新读取实际 automation
状态。普通任务、普通 worktree 测试、fixture、Doctor、Skill 安装或 `ACTIVE` 配置均不能替代上述生产门禁。

项目依次分类为 `discovered`、`active`、`eligible`、`enrolled`。`active` 要求滚动 30 天内至少一次自然用户任务；
Scout、测试、自动化和委派任务不计入。`eligible` 要求 Git 工程与 worktree 隔离。来源识别不完整时
`activity_coverage=bounded`，推荐只能是 `trial`；非 Git 项目推荐 `blocked`。

Git 项目内容 identity 采用 `project_content_identity_v1`：把移除凭据、query、fragment 与末尾 `.git` 的规范化
remote identity 和 primary folder 的仓库内相对位置共同输入 SHA-256。结果只暴露最终 content identity 与
`content`/`host_local` identity kind，
不得输出 remote URL 或绝对路径。无 remote 或非 Git 项目只使用 host-local identity。

`inspect` 使用的能力源是固定 authority identity，不是固定项目集合。它把两个源 staging 到当前 Codex home 下的
受管 source root，验证期望 remote identity、clean worktree 和 commit 后才替换；两个源中任何一个失败时不得把
部分同步声明为部署完成。活跃项目 checkout 永远不是更新目标。生产命令固定为 `managed_sources.py sync-sources`
和 `managed_sources.py materialize-host`；后一命令从受管源执行 Core setup、global binding、Doctor 与两项 Skill
安装，Agent 不得用临时手工命令序列替代该契约后再宣称完整物化。

`agent_memory_workstation_deployment_pack_v1` 顶层精确包含：

```text
contract_version, status, display_locale, bootstrap_version, generated_at,
portable_distribution, source_sync, host_materialization, project_activation,
limitations, pack_hash
```

`status` 只允许 `ready`、`reload_required`、`source_sync_blocked` 或 `host_materialization_blocked`。中文 renderer 固定
先显示四层结果表，再显示未证明事项与唯一下一步。`portable_distribution` 不能证明 `source_sync`；源同步不能证明
Core/Owner/Skill 已物化；物化不能证明当前任务已加载或另一台机器已通过。仅完成当前主机空 profile 测试时，必须
保留“真实第二台设备未证明”。

`global_owner_scout_enrollment_pack_v1` 顶层精确包含：

```text
contract_version, status, display_locale, bootstrap_version, generated_at,
portable_layer, discovery, projects, recommended_project_refs,
current_automation_count, automation_change_count, allowed_actions,
limitations, pack_hash
```

每个 `projects` 项精确包含：

```text
project_ref, display_name, identity_kind, content_identity_hash, host_project_ref,
discovered, accessible, activity, activity_coverage, eligibility,
eligibility_reason, enrollment_status, existing_automation_ref,
recommended_action, recommendation_reason
```

推荐只允许 `migrate_enabled`、`enable`、`trial`、`defer`、`exclude`、`keep`、`blocked`。`按建议启用`只消费
已证明 `active + eligible` 的 `enable` 与 `migrate_enabled`；`trial` 必须点名确认。Enrollment Pack 项目数必须
与 Desktop 枚举数守恒，且 `automation_change_count=0`；确认前自动化配置与 Host Profile 字节均不得变化。

`global_owner_scout_host_profile_v1` 顶层精确包含
`contract_version, profile_version, updated_at, scout_skill_version, entries, profile_hash`。每个 entry 精确包含：

```text
content_identity_hash, host_project_ref, automation_ref, status,
cadence, time_slot, last_verified_at
```

`status` 只允许 `enabled`、`deferred`、`excluded`。Profile 不保存路径、remote、任务、证据、候选、卡片正文、
Owner 内容或跨主机租约。自动化调和全部成功后才原子替换 Profile；任一任务更新失败必须恢复本轮已修改任务并
保持旧 Profile。

### 用户主动触发入口

正式交互入口只允许用户在目标 Git 工程的独立 worktree 任务中显式发送：

```text
$global-owner-scout 复盘当前项目
```

Skill 禁止隐式触发，固定 `evidence_window.kind=manual_30d`，且
`host_automation_memory_read=host_automation_memory_updated=false`。项目身份来自当前 Desktop 绑定；Prompt 不包含
路径、project ID、固定项目名、Skill 版本、候选提示、模型或完整深挖协议。交互任务继承当前任务的 model、
reasoning 与 Speed；可观测时 `actual_model/actual_reasoning` 必须等于请求值，不可观测时使用 `request_only`。

### Project Scout：`global_owner_scout_project_v4`

v4 是不兼容 v3 的主机身份升级。顶层必须包含 `display_locale=zh-CN`、`project_identity`、运行 identity、证据窗口、模型观测、项目 owner 快照、结构化
`session_coverage`、证据源、事件、E1 观察项、全部 E2/E3 `project_cards`、只读证明和限制。不得再用
`session_evidence_available` 布尔值，也不得限制项目卡数量。

`session_coverage` 至少记录任务索引上限、发现数、窗口内数量、选择数、完整读取数、turn page 数、排除理由、
是否截断，以及 `complete/bounded/degraded`。达到宿主任务索引上限、未读到窗口边界或无法继续分页时只能使用
`bounded/degraded`，不得声称完成完整 session 复盘。

Skill 5.5.0 的所有入口固定使用已验证的原生任务索引上限 `50` 作为首次且唯一的索引请求，不得先请求更大
页面探测上限。调用使用最长 60 秒的初始 yield；返回 `cell_id` 时必须对同一 cell 最多连续 wait 两次、每次最长
60 秒。cell 未终态前禁止发起第二次索引调用，`Script running` 不得解释为 unavailable、timeout 或 degraded。

`discovery_methods` 只允许终态枚举：`native_index_completed`、`native_index_host_cap`、
`native_index_terminal_failure`、`native_thread_pages_completed`、`execution_protocol_failed`。`complete` 必须同时包含
`native_index_completed` 与 `native_thread_pages_completed`；`bounded` 必须包含 `native_index_host_cap` 与
`native_thread_pages_completed`；`degraded` 必须具有明确 `native_index_terminal_failure`。未恢复 cell、非法参数或
执行中断一律为项目 `failed` 并记录 `execution_protocol_failed`，不得降级伪装为 Session 不可用。

相关自然任务通过原生 `read_thread` 分页到窗口边界或 EOF，记录发现数、窗口数、选择数、完整读取数、读取页数和
排除理由。每页固定使用宿主已验证的 `turnLimit=10` 与 `maxOutputCharsPerItem=20000`，不得用更大值探测能力。
Scheduled、Scout、测试和委派任务继续排除；活跃任务以读取时快照为准，不等待项目会话结束。

`project_identity` 精确包含
`identity_kind, content_identity_hash, host_project_ref_hash, git_worktree_eligible, binding_status`。
`binding_status` 为 `bound`、`rebound` 或 `ambiguous`；只有非 ambiguous 的 Git content identity 可以运行
Scheduled Scout 或沿用跨路径 Host Enrollment。

每张 Project Card 必须包含：

1. `human_context`：`display_locale=zh-CN`、不超过 60 字符的 `decision_title`、1–3 个短段落的
   `project_story`、`user_cost`、`recommended_outcome`、`concrete_before`、`concrete_after`、
   `strongest_counterpoint` 与至少一个直接证据 `evidence_refs`；
2. 项目痛点与重复成本；
3. 事件时间线与直接证据；
4. 反向证据和错误全局化风险；
5. 失败/重复、被接受变化、预防行为和证据边界构成的因果链；
6. 项目事实、删除细节和通用行为构成的抽象过程；
7. 项目 owner、Skill、global candidate 或不持久化的本地判断与理由；
8. 反例、未证明事项、隐私检查和精确七字段 Rule Projection；
9. `normalized_evidence_hash` 与覆盖 `human_context` 及上述全部项目语义字段的 `project_claim_hash`。

Project Card 是目标工程线程的语义结论。Human Context 与 Rule Projection 都必须在 global owner 比较前形成。
后续 integration preview、Markdown renderer 和按需中央审阅必须验证并保留 `project_claim_hash`，不得翻译、补写
或修改 Human Context、证据等级、痛点、反证、抽象、owner 建议或七字段。证据引用只保留可在
对应项目中重建的逻辑定位，不得输出私有绝对路径、原始对话、token、密钥、完整命令或内部诊断正文。

所有用户叙事字段固定使用简体中文。长度超过 40 字符且完全没有汉字的自然语言句子校验失败；代码、URL、来源
标题、产品名、枚举、ID 和拟写入 Owner 的精确文本是明确豁免。隐私抽象只能删除敏感或局部实现细节，不得删除
用户理解真实事件所必需的项目领域词汇。

证据分级如下：

| 等级 | 含义 | 可否生成全局卡 |
| --- | --- | --- |
| E1 | 单次事件或尚未验证的观察 | 否，只进入紧凑观察项 |
| E2 | 单项目重复出现、被正式决策接受或通过真实验收 | 是，必须完整显示单项目证据和误判风险，不使用固定项目总数作分母 |
| E3 | 至少两个项目独立出现同一机制 | 是，按需中央审阅只建立关联，不得合并丢失项目差异 |
| E4 | 已确认规则在后续自然任务中改变判断与行动 | 只证明采用，不用于发现候选 |

`project_support` 在 v4 中精确包含
`count, project_refs, basis, coverage_note`。E2 的 count 通常为 1；E3 至少为 2。refs 必须是隐私安全的 opaque
identity，`basis` 与 `coverage_note` 必须说明独立证据与覆盖边界，不得再使用固定分母。

### Project Review Pack：`global_owner_scout_review_pack_v4`

Project Scout 固定全部 Project Card 后，读取同一时刻的 canonical global `AGENTS.md` source 与活动宿主的本机
global `AGENTS.md` target，生成独立 `integration_preview`。每项 preview 只包含原卡 hash、global relation、一手调研、owner 对比、精确
before/after/unchanged、风险、重复状态和动作资格；它不得回写 Project Card。

两个物理端点只能由 Skill 的只读 Owner resolver 解析：从
`$CODEX_HOME/agent-memory-sidecar/memory.sqlite` 的 `global_instruction_binding` 获取 canonical source root，并把
活动 `$CODEX_HOME/AGENTS.md` 作为本机 target。resolver 只输出固定逻辑 ref、当前内容 hash、状态与 snapshot hash；
不得输出路径。binding、Store 或任一文件不可用时返回 `unavailable`，不得搜索或回退到项目根 `AGENTS.md`。

`owner_parity` 必须显式记录固定逻辑端点 `canonical_global_agents` 与 `host_local_global_agents`；项目根
`AGENTS.md` 只属于项目证据，绝不能替代本机 global target。snapshot identity 覆盖端点标识、状态和双方内容
hash，避免“hash 合法但比较对象错误”。

Review Pack 顶层包含 `display_locale=zh-CN`，原样包含完整 `project_result`，并追加 owner parity、全部 review cards、限制和
`review_pack_hash`。每个 review card 按原始顺序引用一个不可改写的 `project_claim_hash`，附带对应 integration
preview、`recommended_action`、中文 `recommended_action_reason`、未来行为变化以及 `allowed_actions`。内部 E2/E3
Project Card 数必须等于 Review Pack 卡数。每个可确认卡还必须包含由当前 canonical source hash 派生的
`selection_token`；不可确认卡该字段为 `null`。

确定性 renderer 只接受通过 validator 的 Review Pack，并且只能从 Skill `scripts` 目录直接执行
`render_review.py --surface interactive|scheduled`、通过 stdin 输入完整对象；禁止动态 import 或 renderer 失败后的模型手工重写。它按固定顺序生成 Markdown：运行状态与覆盖/parity 警告、
交互 surface 的`本次需要判断 N 项`或 Scheduled surface 的`今日需要判断 N 项`中文索引、全部完整决策卡、E1 与 Session/模型覆盖技术附录、简短校验回执。每张卡先显示
项目事件、用户成本、建议、具体 before/after、最大反例和推荐动作构成的 30 秒判断，再显示完整核对依据。表格
最多四列，before/after 使用两列表格；不得依赖 HTML 折叠、自定义 App UI、图片或预览期 Visualizations。默认
任何最终答复不得显示原始 JSON。renderer 回执包含 surface、可见正文 SHA-256、Project Card 数、可见卡数、
逐卡动作计数向量、动作总数和 wrapper 数。interactive 不得出现 Scheduled/Inbox/`0/14`/14 次文案且 wrapper
必须为零；scheduled 必须生成唯一且最后一个 Inbox wrapper。Agent 必须逐字返回 renderer 结果，再由只读
`verify_visible_output.py --surface ...` 校验正文 hash、卡片和动作守恒、surface-specific wrapper 数量、无原始 JSON
和无手工尾注。`degraded` 仍显示有独立正式证据的卡；
`failed` 显示可见失败终态，不制造空白结果。

所有 Python helper 固定使用 `python -B`，安装器原子排除 `__pycache__`、`.pyc` 和 `.pyo`。Scout 在执行前后复核
个人 Skill 安装目录的字节码缓存指纹；任何新建或变化均属于外部写入并失败关闭，Scout 不得通过删除缓存掩盖失败。

`edit` 与 `ignore` 始终可用。parity matched 且项目建议为 `global_agents` 的 `add/replace/consolidate` 卡才允许
`confirm`；`project_owner/route_to_owner` 推荐 `keep_project`，`skill` 推荐 `make_skill`，`already_covered` 或
`no_persistence` 推荐 `ignore`，上述卡均不提供直接确认。parity 漂移或不可用时移除所有 `confirm`。用户要改变
Owner 去向时必须先通过 `edit` 生成刷新卡。用户在同一 Scout 任务中可以精确选择一张或多张同 scope/target
的可确认卡；renderer 把动作显示为 `确认 <card_id>@<selection_token>`，并明确可用 `、` 一次连接多个完整
`card_id@selection_token` 对。任何确认都必须对选中集合执行一次最新 owner/parity 读取和联合关系重算。按需 `central_review` 可以
读取已可见 Review Pack 并追加跨项目关系，但不是 Scheduled 模式，也不改变原卡或动作资格。

Review Pack 卡片不得称为 `pending proposal`，不得包含 approval ref 或 proposal token；`selection_token` 是可见操作
identity，不是待确认状态或长期凭证。用户确认选中集合只是授权
Agent 进入原子规则包链的起点：Agent 必须重新读取最新 global owner 和 parity、联合判断选中卡及其相互关系并
计算聚合 before/after。若语义关系或最终规则发生实质变化，零写入并展示刷新包；未变化时执行恰好一个
`rule deploy-bundle`。成功后未选择 Project Card 只需刷新 integration preview，不重新执行项目复盘。

### 失败与只读语义

- `session_coverage.status=bounded/degraded` 时必须精确声明未覆盖范围；项目 Git、owner 和验收事实仍可形成
  有限结果，但不得用布尔值或模糊措辞伪造完整任务普查。
- 原生任务索引未取得终态、调用参数非法或执行协议中断时使用 `failed / execution_protocol_failed`；只有工具
  明确返回终态错误才允许 `degraded / native_index_terminal_failure`。运行内的失败包不得把 `failed` 再描述为
  “degraded / Session unavailable”。Scheduled 状态变更不属于只读 Scout；外部 Host Activation Control 观察到
  首次协议错误后执行并复读 `PAUSED`。没有实际控制面调用时只能报告“需要暂停”，不得声称已暂停。
- 输入缺失、结构不合法、E1 晋升、隐私泄漏、工作区变化、外部写操作或无法证明只读时，该项目 Review Pack
  显示失败终态；不得输出未通过校验的卡。
- renderer 失败、输出被截断、正文 hash/卡片/动作不守恒、surface/wrapper 不匹配或存在手工尾注时，整次运行使用
  `render_integrity_failed` 或 `output_budget_exceeded` 失败终态；不得展示部分卡片或手工生成替代 Markdown。
- Python helper 产生或修改字节码缓存时按外部副作用失败；缓存清理由安装阶段负责，自动 Scout 不得自清理。
- 当前 Scheduled 宿主强制每个 automation 读取并更新自身 memory，并在最终答复末尾追加一个 Inbox directive。
  二者是宿主控制面 wrapper，不是 Scout 证据、候选 Inbox 或去重状态。memory 只允许记录运行时间、覆盖/终态、
  卡片数量或 hash、只读/parity 结果；不得记录原始证据、卡片正文、候选语义或去重判断。确定性 Review Pack 与
  校验回执仍是完整人工审阅内容，单个 Inbox directive 仅负责让该任务在 Scheduled 中可见。普通 worktree 前向
  测试不读写 automation memory；`host_automation_memory_read/updated` 必须同为 true 或同为 false，且始终不得作为证据。
- 若更高层运行时要求执行后置 Agent Memory 审计，该审计保持静默并复用已渲染的卡片与校验回执作为终态；不得
  调用独立 `agent-memory` Skill、追加第二条 memory 状态、proposal 或治理回执。可见输出 verifier 必须是最后一个
  工具调用；通过后不再调用任何 Skill 或工具。interactive 无 wrapper；scheduled 的单个 Inbox directive 始终是
  最后一个控制 wrapper。
- 活跃原工作区的并发变化只记录为当前隔离快照之外的限制；稳定隔离快照中的卡不得因此整体失效。
- 2026-08-11 的三个真实 v5.1 Scheduled 运行及最小 automation-source probe 证明本主机原生任务索引未取得终态。
  每个 Host Enrollment 保持 `0/14`，自动化保持 `PAUSED`；普通 worktree 前向测试不再拥有恢复权。只有新的真实
  automation-source canary 在外部 180 秒观察预算内取得终态后，才可恢复一个 Skill 5.5.0 项目 canary；
  在 14 次有效运行期间必须显式请求
  `gpt-5.6-sol` 与 `medium` reasoning，并记录请求值、
  宿主可见的实际值和 telemetry 可用性。只有 request 不能证明实际模型；不可观测时诚实标记 `request_only`，
  但不得仅因此把具备 `complete/bounded` Session 覆盖的运行降级。Speed/service
  tier 不进入 `model_observation`，不作为有效运行门禁，并继承本机 Codex 当前配置。
- 每个 Host Enrollment 独立累计 14 次有效运行；离线、失败、`degraded` 和无效结果不计数。同一项目连续三次仅因 Session
  索引不可用而降级时暂停该项目并显示能力阻断。第 14 次后只能产生降频决策卡。
- 文件写入只能声明 `instruction_deployed`；至少两个项目的新自然任务采用前，必须同时声明
  `adoption_unproven`。撤销后的新任务不再采用，才证明撤销行为。

状态声明固定使用以下证据阶梯，禁止跨级：`designed -> implemented -> installed -> production_proven ->
longitudinally_effective`，并按入口分别报告。当前主机三个真实用户任务 canary 已证明
`interactive_project_scout=current_host_production_proven`；`scheduled_project_scout=production_blocked / PAUSED / 0 of
14`，`owner_continuity=adoption_unproven`。跨设备冷启动只有空 profile 与受管源契约验收时必须报告
`cross_host_bootstrap=implementation_verified / production_unproven`，直到真实第二台设备完成首次加载、Doctor 与
交互 canary；不得用任一主机或入口的测试替代另一主机或入口的生产证明。

## Core cutover

```text
agent-memory maintenance core-cutover --dry-run
agent-memory maintenance core-cutover --apply --plan-hash <hash> --approval-ref <ref>
```

Dry-run 不写入，输出源/目标 schema、稳定计划 hash、表计数、复制/丢弃策略、artifact hash 和备份目标。
Apply 需要新的当前 approval ref；setup 遇到旧 schema 只返回 `migration_required`。

迁移必须：

1. 使用旧新运行时共同识别的维护锁，锁期间 Hook fail-open。
2. 创建永久保留的完整 SQLite backup 与 SHA-256。
3. 在临时库迁移、执行 FK 与 integrity check，并用新 artifact 自检。
4. 旧 proposal token 全部失效；只复制能关联保留 event 的 approval consumption。
5. 原子切换 Store 与 Hook；任一失败恢复旧 Store、Hook 和 instruction 文件。

## 公开分发接口

公开源同步使用 `agent_memory_source_manifest_v1`：

```json
{
  "contract_version": "agent_memory_source_manifest_v1",
  "distribution": "release",
  "sidecar": {"remote": "https://example.invalid/agent-memory-sidecar.git", "ref": "v0.3.0", "commit": "<40 hex>"},
  "canonical_owner": null
}
```

- release manifest 的 Sidecar 必须同时固定 ref 与完整 commit；clone/fetch 后 commit 不同即
  `managed_source_commit_mismatch`，不得执行安装代码。
- `canonical_owner` 可以为 `null`。此时 setup 不创建 global binding，Doctor 仍可证明 Core ready；global mutation 与
  Owner parity 返回 unavailable，不搜索本机其他 Owner。
- owner-integrated manifest 的 Owner 使用同一三字段和 commit 校验；其 remote 不进入 Deployment Pack 或公开 archive。
- 开发模式允许当前私有工作站沿用明确的 branch source，但不得被 public exporter 或 release workflow 接受。

`public_source_export_v1` 的输入包含独立 public repository URL、engineering source commit、SPDX license expression 与
UTF-8 license file；输出目录必须不存在。它只复制 allowlist 选择面，记录 engineering commit 与公开 snapshot digest；
未选中文件留在私有源，已声明但为空的 pattern、alias/hardlink、binary、隐私命中、缺许可证或 dirty source 失败关闭。
所有选中的 UTF-8 文本与许可证在写入和计算 snapshot 前统一为 LF；公开根目录同时映射
`* text=auto eol=lf` 的 `.gitattributes`，使后续跨平台 clone 继续保留 snapshot 的物理字节。无法严格解码的字节失败关闭，
公开源码 identity 不得随私有工程或公开消费 checkout 的 CRLF/LF 策略漂移。
Allowlist 中的 `path/**` 固定表示该目录下全部后代普通文件；实现不得直接依赖 Python 版本相关的尾部 `**` glob
返回集合，遍历中遇到 alias/reparse 或零普通文件均失败关闭。
独立公开仓库提交后，release builder 才接受 `v<Core>` ref，并要求 origin、ref commit 与 public HEAD 三者一致；随后验证
Core wheel/sdist、portable bundle、SBOM、checksums、可重建性和实际消费者 smoke。任一失败均为
`public_export_blocked`，且不改变 Git、Codex home、Store 或远端。

Core wheel/sdist 与 portable Plugin/Skill bundle 分开验证，并由 release manifest 记录各自文件名、字节数和 SHA-256。
公开仓库、tag、Release、PyPI 与安全设置不是 exporter 操作。

首发 seed 没有 `PUBLIC_AUTHORITY.json`，release builder 必须逐字节验证 `PUBLIC_EXPORT_RECEIPT.json` 登记的全部 tracked
snapshot。权威切换后的公开仓库跟踪 `agent_memory_public_authority_v1`：顶层精确包含
`contract_version, status, repository, engineering_source_commit, initial_public_release, activated_at`；
`initial_public_release` 精确包含 `ref, commit, snapshot_sha256`。只有 repository identity、UTC 时间、tracked marker、
初始 tag/commit 和初始 commit→当前 HEAD 祖先关系全部成立，builder 才允许后续公开原生提交不再匹配旧 export snapshot。
marker 不进入 Core Store、不授权切换，也不改变行为 owner。

公开工程权威固定为 `private_engineering -> public_candidate -> public_active`。前两期唯一 owner 都是私有工程仓库；
`public_active` 需要 `public_install_verified`、`public_published` 和独立人类确认，并在同一治理转换中冻结归档私有工程源。
公开仓库可见、Tag、Release 或 marker 任一单独事实都不得冒充该转换。转换后禁止从私有仓库持续导出、双向同步或
接受公开产品变更；后续公开代码、规范、测试、Issue、PR、CI、Tag 与 Release 只在公开 `main` 演进。

GitHub Tag workflow 只允许在 public repository 创建/恢复 draft，随后上传完整资产、比对远端资产集并确认仍为 draft；
它不得持有管理员 Token 或自动 publish。immutable-releases API 需要 Administration(read)，因此另一次明确授权的
管理员操作必须在 publish 前确认 enabled，复读 draft 资产，publish 后逐资产验证 attestation，并回读非 draft 且
immutable。失败可以保留 draft 重试；immutable Release 发布后不得移动或复用 tag/asset，修复使用新版本。PyPI 是
另一个独立授权面。

`agent_memory_public_release_manifest_v1.source` 顶层精确包含
`repository, ref, commit, authority_epoch, engineering_source_commit, initial_public_release, authority_activated_at`；
`initial_public_release` 精确包含 `ref, commit, snapshot_sha256`。seed release 使用
`authority_epoch=private_engineering` 且 activation 为 `null`；后续公开原生 release 使用 `public_active` 与 marker UTC 时间。

## 验收

- 自动化覆盖七表 schema、迁移失败恢复、七字段、一次性授权、scope、容量、双目标事务、compact no-write、
  Memories-off、单/多规则修订 hash、旧 add-only token 兼容和 result contract。
- Runtime transaction p95 不高于 10 ms，Hook subprocess p95 不高于 150 ms；受支持的本地验收环境执行三轮完整样本，
  以三轮 p95 的中位数判定。GitHub 托管 CI 的独立性能 job 只记录同构三轮观测，不因宿主抖动授予或撤销性能资格，
  功能矩阵不重复消费该噪声敏感测量。
- 真实 Desktop 证明 project deploy/adopt/revoke、global 两项目、primary folder、compact 和 Memories-off。
- Ambient 单卡、条件可见 no-op/失败终态与零建议 control 继续标记 experimental，不阻塞 Core。
- 任何面向用户提及 Agent Memory，但最终答复没有确认卡片、部署回执、no-op 回执或失败回执，都判为失败。
