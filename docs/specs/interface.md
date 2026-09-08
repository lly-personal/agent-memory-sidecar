# Agent Memory L3 接口规范

- Status: active
- Owner layer: project_docs
- Applies when: 实现或验收规则、proposal、状态、CLI、失败反馈和迁移操作。
- Avoid when: 判断产品公理或组件所有权；读取 [L1](axioms.md)与 [L2](topology.md)。
- Last verified: 2026-09-01
- Evidence: 用户批准的条件可见终态闭环设计、[Core v1 ADR](../decisions/0057-agent-memory-core-v1.zh.md)、[Runtime storage policy ADR](../decisions/0058-persistent-runtime-journal.zh.md)、[有界规则集演化 ADR](../decisions/0059-bounded-behavior-set-evolution.zh.md)、[周期性 Global Owner Scout ADR](../decisions/0060-periodic-global-owner-scout.zh.md)、[直接可见审阅包 ADR](../decisions/0063-direct-visible-owner-review-packs.zh.md)、[中文双投影审阅包 ADR](../decisions/0064-chinese-contextual-dual-projection-review-packs.zh.md)、[主机感知动态项目注册 ADR](../decisions/0065-host-aware-project-enrollment.zh.md)、[执行与可见输出完整性 ADR](../decisions/0066-scout-execution-and-visible-output-integrity.zh.md)、[生产执行源激活门禁 ADR](../decisions/0067-scout-production-source-activation-gate.zh.md)、[用户主动触发主路径 ADR](../decisions/0068-interactive-project-scout-primary.zh.md)、[跨设备冷启动连续性 ADR](../decisions/0069-cross-device-cold-start-continuity.zh.md)、[原子规则包 ADR](../decisions/0070-atomic-review-pack-rule-bundles.zh.md)、[所见即所签与物理 containment ADR](../decisions/0071-wysiwys-review-pack-bundles-and-physical-target-containment.zh.md)、[白名单公开分发 ADR](../decisions/0072-allowlisted-public-distribution-lane.zh.md)、[公开工程权威切换 ADR](../decisions/0073-public-engineering-authority-cutover.zh.md)、[统一工作站调和 ADR](../decisions/0075-unified-workstation-reconcile.zh.md)、[任务级 Review Pack 交付 ADR](../decisions/0076-task-scoped-review-pack-delivery.zh.md)、[确定性 Release 发布 ADR](../decisions/0077-deterministic-release-promotion.zh.md)、[真实读回工作站调和 ADR](../decisions/0078-workstation-reconcile-v2-observed-state.zh.md)
- Extended by: [项目任务前门与确定性终态 ADR](../decisions/0079-project-session-front-door-and-scout-terminal-contract.zh.md)、[消费者可见 Skill 范围 ADR](../decisions/0080-consumer-visible-skill-scope-reconciliation.zh.md)

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

确认前使用 `rule preview-bundle --target-file <observed-owner> --from-json -` 对准确 `rule_revision_bundle_v2` 做零写入预演。
Core 复用正式 bundle planner，校验整个 target before hash，并返回 `rule_bundle_preview_v1`：
`target_before_sha256, bundle_sha256, before_bytes, budget_bytes, items, combined`。每个 item 包含
`card_id, status, projected_bytes, target_after_sha256, error_code`；combined 使用同一结果字段及排序的 `card_ids`。
`status=ready` 才表示该准确集合通过；`blocked` 保留准确错误，未知 projected/after 为 null。一次调用计算单卡与整个选集，
不创建 Store、proposal、批准、锁、journal 或目标文件。预演只证明当前字节下的结构、容量与差量；语义关系仍由复盘判断，
真实部署仍在授权及锁内重新规划。Runtime zipapp 的 `preview-bundle` 入口提供相同只读能力，供 Scout 从实际安装 identity 调用。
两种 Core 预演入口和 `scout.py prepare-review` 都允许重复传入 `--select-card <id>` 核查明确子集。未传则预演全部拟议项。
子集必须是唯一已知成员；仍保留完整候选与单项投影。`bundle_sha256` 绑定完整输入，`combined.card_ids` 与 after hash
绑定准确所选组合；不能为了预演子集删除其他卡片或重跑项目发现。

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
- `instruction_cleanup_required` 表示规则事务已经提交，`error.details` 必须明确
  `operation_committed=true / approval_consumed=true / recovery_required=true`；退出码 `1` 只表示清理尚未闭合。
  此时必须先读取实际规则，不得输出“未部署 / 长期状态未变更”或复用已消费授权；后续授权 mutation 仍执行恢复。
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
| 已提交但清理未完成 | `记忆检查：清理待完成｜结论：规则操作已提交｜动作：待事务清理｜长期状态：{实际 target 读回状态，无法读回则未证明}`；优先于通用失败回执 |

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

- `rule list` 只读取实际 target、容量和 pending token；不读取历史 memory，不恢复文件事务或删除 journal。
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
deploy、edit、consolidate 或 revoke 在提交前失败使用“未部署”，新任务采用尚未观察到时使用“未证明”。
提交后清理或锁释放失败使用 `instruction_cleanup_required` 的“规则操作已提交、清理待完成”回执，并读回实际 target；
不得把已经提交的结果说成未部署，也不得把清理未完成说成整体成功。

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
| 提交前文件/数据库事务失败 | 恢复原状态并返回 `mutation_failed` |
| 提交后清理或锁释放失败 | `instruction_cleanup_required`，操作已提交、批准已消费、清理待完成 |
| 恢复所需事件已过期且没有持久提交证明，或旧 journal 无法归因 | `instruction_recovery_unproven`，保留实际 target 与 journal，需有据对齐；不得推断未提交并回滚 |
| 文件存在但新任务未采用 | `instruction_deployed`、`adoption_unproven` |
| Global Git 未推送 | 本机可生效，但明确 `publication_required` |

## Global Owner Scout 实验契约

Global Owner Scout 的交互或 Scheduled 输出都是只读 `review draft`，不是 Core proposal。内部 Project Card 和用户可见
Review Pack 只存在于当前任务结果；interactive 可以写入当前任务宿主显式提供、位于项目外的不可变
generated-output artifact，但不得写入 Store、文件 Inbox、项目文件或 `AGENTS.md`。

### Workstation Bootstrap 与 Host Enrollment

Repo/plugin 分发的冷启动 Anchor 固定识别：

```text
同步并部署本机 Agent Memory
```

Anchor 只负责验证并调用正式 Bootstrap，不复制其实现。公开通道先运行同包 `resolve_release.py`；默认解析 latest stable，也可消费用户
指定版本。只有 `agent_memory_release_resolution_v1 / verified` 才能提供 root `source-manifest.json`，并只用其中
repository、immutable ref 与 full commit。Resolver 必须验证 Release immutable/stable、tag/commit、GitHub asset digest、
`SHA256SUMS`、release/source manifest 与 portable 内嵌副本；仓库 checkout、repo marketplace 或浮动 branch 本身都
不是公开 source authority。GitHub API metadata 请求依次接受显式 `GITHUB_TOKEN`/`GH_TOKEN` 或本机现有非交互 `gh`
authentication，只把 token 放入 API 请求头且不写入输出；两者均不可用时允许匿名请求。API rate limit、无效认证与
metadata 缺失必须保留可区分 detail，外层失败仍固定为 `release_resolution_blocked` 且不兜底。
私有开发通道可使用显式 development manifest，但不得成为公开兜底。Resolver 把 portable 手工安全展开到解析目录，
拒绝绝对路径、`..`、symlink、reparse 语义、非 regular file 与重复条目。Anchor 从该已验证副本在同一任务执行正式
Bootstrap 工作站调和，并安装 Bootstrap/Scout；不得要求 project ID、项目名单或资源配置，不得在当前任务把新安装
Skill 冒充已加载。可靠自动发现边界仍是一次 Codex 刷新或下一任务，但 source/host 物化必须在当前部署任务完成。

`agent-memory-workstation-bootstrap` Skill 2.2.2 提供两个显式模式：

- `inspect`：从 Resolver 已验证的 Release/source manifest 与 portable 组件构造唯一 `DesiredBundleIdentity`，再真实读取
  Marketplace/Plugin/source/runtime/Skills。fresh/同 identity 直接同步并部署；只有既有 Sidecar 或 Marketplace identity 变化时
  显示一份人类可读计划并等待一次确认，再消费 fresh hash 原子 apply。显式禁用 Plugin 保持不变并阻断。随后验证 Core、
  global binding、Doctor 与 versioned Skills；Skill 安装通过后从下一任务保证交互 Scout 可用，无需 Host Enrollment。项目发现和
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
部分同步声明为部署完成。活跃项目 checkout 永远不是更新目标。`managed_sources.py sync-sources` 和
`managed_sources.py materialize-host` 是统一事务内部的严格底层命令，不具备独立完成语义；Agent 不得用临时手工命令
序列替代统一入口后再宣称完整物化。

已有受管源 identity 与 release manifest 不一致时，普通 sync 继续失败关闭。统一生产入口为：

```text
managed_sources.py workstation-reconcile --dry-run --codex-home <home> --source-manifest <source> --release-manifest <release>
managed_sources.py workstation-reconcile --apply --codex-home <home> --source-manifest <source> --release-manifest <release> --plan-hash <hash>
managed_sources.py workstation-reconcile --verify-consumer --codex-home <home> --source-manifest <source> --release-manifest <release> --desktop-project-inventory <inventory>
```

计划精确遵循 [`workstation-reconcile-v2`](../../specs/workstation-reconcile-v2.md)，内部 source 事务仍遵循
[`source-authority-cutover-v2`](../../specs/source-authority-cutover-v2.md)。无 `--force`；apply 前重算完整
状态。`canonical_owner` 存在时按 manifest 物化；值为 `null` 且已有 clean Owner checkout 与 Core binding 的
root/commit 精确一致时为 `keep_owner`，二者都不存在时为 `public_core`，其他组合
`source_cutover_owner_state_ambiguous` 阻断。Plugin/Marketplace mutation 在 source rollback 释放前完成 exact readback；
任一参与者失败共同恢复。apply receipt 只证明本机 distribution/source/materialization，不证明当前任务加载或跨主机连续性。
为承接已发布 Anchor 1.x，旧命令名 `source-cutover` 在输入同时包含 Resolver 生成的 sibling
`release-manifest.json`、`resolution.json` 与 `portable/` 时兼容路由到上述统一入口；缺少该完整形态时仍执行底层
Source Authority Cutover，不得把任意 source manifest 升级为发行授权。

`agent_memory_workstation_reconcile_plan_v2` 顶层精确包含：

```text
contract_version, bootstrap_version, status, desired_bundle, observed_distribution,
source_plan_hash, changes, blockers, confirmation_required, requires_reload, plan_hash
```

`DesiredBundleIdentity` 精确包含 `release_ref, source_commit, core_version, plugin_version, plugin_sha256,
bootstrap_version, bootstrap_sha256, scout_version, scout_sha256`。`observed_distribution` 精确包含 Marketplace 的
`status, source_sha256, ref, commit` 与 Plugin 的 `status, source_sha256, ref, version, content_sha256, enabled`。只允许
从 Resolver receipt 与逐字节匹配的 Release 资产构造期望身份；实际状态只允许从 Codex JSON CLI、clean tracked
Marketplace checkout、可选 legacy install metadata 和 physical Plugin cache 构造，不得由 Agent 填写。当前 Codex CLI
未生成 legacy metadata 时，ref 必须来自已校验的 tracked Marketplace manifest；metadata 存在时仍须逐字段严格校验。
当 managed source 已 exact 时，dry-run 还必须通过该受管 Sidecar 执行只读 Doctor，并读取 live runtime identity、Owner
parity 和物理安装的 Bootstrap/Scout version/hash。任一漂移生成 `host:materialize`；历史 cutover receipt 不参与当前
`noop` 或 `ready` 判定。

`agent_memory_workstation_deployment_pack_v3` 顶层精确包含：

```text
contract_version, status, display_locale, generated_at, desired_bundle, distribution,
source_sync, host_materialization, consumer_scope, consumer_activation, limitations, pack_hash
```

`consumer_scope` 精确包含：

```text
status, inventory_status, desktop_project_count, scanned_project_count,
matching_skill_count, projects, limitations
```

每个 project 精确包含 `project_ref, display_name, status, skills`；每个 Skill 精确包含
`name, scope_level, version, content_sha256, relation`。临时输入 `agent_memory_desktop_project_inventory_v1` 顶层精确包含
`contract_version, inventory_status, projects`，每项只含 `display_name, path, is_git_repository`；无本机 primary folder
时 `path=null`。路径只供本轮只读检查，不得进入输出、Pack hash、Git 或持久状态。Git 项目从 primary folder 到 repo
root 逐级检查两个产品同名 `.agents/skills`，非 Git 项目只检查 primary folder；缺失不是漂移，路径不可用、物理树别名、
超出 512 文件系统条目或 8 MiB 读取预算、读取中变化、不可读或版本不可解析使范围为 `bounded`。

`status` 只允许 `ready`、`reload_required`、`consumer_scope_drift`、`consumer_scope_bounded`、
`distribution_reconcile_blocked`、`source_sync_blocked` 或 `host_materialization_blocked`。中文 renderer 固定先显示期望发行、
Plugin 分发、源同步、主机物化、消费者范围、消费者采用，再显示未证明事项与唯一下一步。apply 固定不越过模型采用层，
返回 `reload_required`；一次 Desktop 刷新后，只有已加载 2.2.2 Bootstrap 的新任务执行只读 `--verify-consumer`、所有主机
读回仍 exact、Desktop 项目枚举完整且项目级同名 Skill 全部 exact，才允许 `ready`。任何本机结果都保留真实第二台设备、
Scheduled、连续性与产品收益未证明边界。

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

正式交互入口只允许用户在目标 Git 工程的当前项目任务中显式发送：

```text
$global-owner-scout 复盘当前项目
```

Skill 禁止隐式触发。入口必须先于任务索引、线程分页、Owner 比较和项目深挖完成一次前置 preflight：Fresh
解析当前 Desktop 项目绑定，并通过 `python -B scripts/scout.py inspect-context` 取得无路径
`global_owner_scout_preflight_v1` Git/只读快照。已在独立 worktree 时原地继续；该正式调用授权恰好一个只读 executor；位于
Local 时必须使用宿主原生项目任务创建能力，把当前 working-tree state 与同一正式调用作为初始 prompt 一次性投影，
并在隔离任务继续，用户不重复输入。不得创建空子任务、不得用
shell 手工创建 worktree、猜测路径或先执行部分复盘再检查上下文。项目非 Git、绑定不可验证或宿主无法投影时，
入口在 preflight 阶段通过 `global_owner_scout_terminal_v1` 失败关闭。
投影成功时，前门任务只返回宿主原生 created-task surface，把用户直接链接到唯一 executor；该状态只证明
`routed`，不得声称复盘、Review Pack、安装采用或用户验收已经完成。完整 Review Pack 或 Terminal 只在 executor 任务产生。

`global_owner_scout_preflight_v1` 精确包含：

```text
contract_version, git_repository, execution_context, head, status_sha256,
staged_diff_sha256, unstaged_diff_sha256, untracked_files_sha256,
context_snapshot_sha256
```

`execution_context` 只允许 `local` 或 `linked_worktree`，snapshot hash 覆盖其他全部字段，输出不含路径。它只证明 Git
执行上下文与基线，不证明 Desktop 项目绑定、成功投影、安装采用或 Review Pack 结果。

隔离执行器固定 `evidence_window.kind=manual_30d`，且
`host_automation_memory_read=host_automation_memory_updated=false`。项目身份来自当前 Desktop 绑定；Prompt 不包含
路径、project ID、固定项目名、Skill 版本、候选提示、模型或完整深挖协议。入口不要求用户填写资源配置，也不为
自动隔离 executor 注入 model/thinking override；使用该 executor 的宿主解析 model、reasoning 与 Speed。可观测时
`actual_model/actual_reasoning` 必须等于该任务请求值，不可观测时使用 `request_only`。

### 真实用户旅程验收

Scout 的用户需求闭合必须从真实使用场景、完整行为链、体验和心智模型四个维度验收。代码测试、固定语义样本、
文件读回或安装检查只证明各自层级；新增验收标准本身不证明体验已经通过。

| 维度 | 真实场景与验收行为 | 通过条件 |
| --- | --- | --- |
| 使用场景 | 用户在持续演进的目标工程中提出正常复盘请求，执行者从真实 Owner、决策、成功/失败及验收原文发现经验；覆盖仍生效的较早沉淀、近期新经验、已有覆盖和项目专属约束 | 不向执行者提示候选答案，不要求用户补充“请更深入”才发现已标注的关键经验；每项关键经验有正确去向及可核查依据，不按卡片数量评分 |
| 行为链 | 从发起复盘、进入唯一执行任务、阅读结果、选择确认/修改/忽略，到准确作用域读回、后续自然任务采用、查看/修订/撤销 | 真实入口贯通实际结果；用户不重复输入或寻找多个任务，确认与结果对应；后续任务不靠重述规则或测试提示采用，撤销后新任务不再从该 Owner 获得规则 |
| 体验 | 观察用户能否找到结果、理解建议与例外、作出决定；检查等待、降级、无法确认及失败时的可见反馈和恢复动作 | 首层内容说明发生了什么、用户成本、接受前后变化、影响范围和合法例外；状态与动作准确，已证价值可发现，无无效重试或重复确认；记录额外操作与理解困难，未实测不声称易用或耗时达标 |
| 心智模型 | 检查用户对“当前项目的事实与规范”“待确认的通用候选”“已经生效的作用域规则”及“未发现增量/资料不足”的理解 | 用户能区分上述状态，知道何时影响未来任务以及如何查看和撤销；同类状态与动作保持一致，不要求先理解 worktree、版本、hash、parity 或协议枚举才能完成主要任务，技术核对材料按需展开 |

最小场景组还必须包含：准确已有覆盖而无新候选、资料不足但保留独立有据候选、结果排队打开或打开失败、
修改候选后再确认、忽略且不写入、作用域不适用的普通任务，以及撤销后的新任务。它们与既有宿主入口矩阵分别
回答用户需求和执行机制问题；机制场景通过不能替代用户旅程通过。普通非复盘任务继续遵循默认安静边界。

每个场景记录真实起点、用户意图、用户可见动作、系统响应、最终结果、理解或操作阻断及证据来源；
没有对应证据时标为未验证。机器可核查的加载、写入、作用域和可见状态由 Agent 验证，理解与决策困难以真实
使用观察或用户反馈校准；模型自评和“30 秒判断”等界面文案均不构成体验证据。控制证据只保存为该次验收产物，
不新增长期用户行为库或第二状态 Owner。

### Project Scout：`global_owner_scout_project_v5`

v5 保留主机身份与顶层字段，增加严格来源与发现关联；不接收旧 v4 载荷，不允许为旧结果补造来源后迁移。
顶层必须包含 `display_locale=zh-CN`、`project_identity`、运行 identity、证据窗口、模型观测、项目 owner 快照、结构化
`session_coverage`、证据源、事件、结构化观察去向、全部合格 E2/E3 `project_cards`、只读证明和限制。不得再用
`session_evidence_available` 布尔值，也不得限制项目卡数量。

来源必须覆盖 `sessions / owners / decisions / successes / failures / acceptance` 六类，逐类声明读取范围、逻辑引用、
状态与未覆盖范围；没有相关材料可以说明不适用，但 Owner 不可不适用。近期任务窗口不裁掉仍生效的工程知识。
深读先建立当前行为 Owner 的标题/编号条款与控制 Owner 的接受/反转决策索引，再按该索引分段读取。冻结前从原文索引
反查高价值条款和有效/无效路径的观察去向；不能只复核模型已经声明的事件。完整读取 ADR 不代表覆盖未读公理或后续纠偏，
含可复用知识的未读范围继续限制发现资格。该步骤复用现有来源、观察和 gap，不要求逐段生成卡片，也不增设长期索引。
一条复合规范中各个独立行为义务、触发条件、用户代价与合法例外都必须在投影后保留；同主题观察不能代替完整语义覆盖。
抽象后还须反查合法成功路径：若不同前置条件已满足同一目标，拟议动作是否仍然必要？不能把项目采用的某个手段、
次数或顺序变成所有任务的硬门；缩窄 When、保留具体 Skip，或将手段分流为项目/Skill 方法，再冻结语义。
材料丰富、横跨当前规范与累积决策的复盘，冻结前由独立上下文先从原文建立义务清单，再复核草稿投影。复核者首先只接收
原始来源及索引/缺口，冻结独立清单后才接收草稿；不接收 Global Owner 措辞或预期候选答案，避免已有草稿主导发现分母。
使用已有内部子代理能力，不新建用户任务或长期实体。独立清单是本轮临时核查证据，不是第二规则 Owner。
逐项修正有据缺口后重验关联、隐私与语义 hash；无法取得独立复核时记录覆盖限制，不把同一上下文自评称为独立验收。
反查同时检查“已有观察但只覆盖部分义务”的来源，不能只检查完全没有观察的条款。项目已存在完整规则只证明局部覆盖；
仍有跨项目行为价值时，保留通用投影进入实际 Global Owner 比较，不得在项目阶段以已有沉淀提前排除。
每个事件都有观察去向，每张卡准确关联一个观察；来源、事件、观察和卡片的引用必须互相解析，卡片的规范证据 hash
从本卡 `direct_evidence` 重算。观察明确项目约束、通用增量、排除理由及精确 Owner，单项目正式接受可支持 E2。
`no_material_delta` 必须有非空的有据观察及去向，只表示已覆盖范围未发现合格增量。来源不足时降级并保留独立支持的卡。
精确字段由 [Scout contracts](../../.agents/skills/global-owner-scout/references/contracts.md) 拥有；
[独立语料评分](../../.agents/skills/global-owner-scout/references/discovery-evaluation/rubric.md) 验证发现能力，不能用格式校验替代。
交互 `manual_30d` 执行器在任务普查前运行 `inspect-output`，失败使用 `output_preflight_unavailable / preflight`；最终交付仍重新校验。
Scheduled 使用既有最终 Inbox wrapper 与可见文本校验，不增加文件输出根或预览能力依赖。

`session_coverage` 至少记录任务索引上限、发现数、窗口内数量、选择数、完整读取数、turn page 数、排除理由、
是否截断，以及 `complete/bounded/degraded`。达到宿主任务索引上限、未读到窗口边界或无法继续分页时只能使用
`bounded/degraded`，不得声称完成完整 session 复盘。

Skill 5.9.0 的所有入口固定使用已验证的原生任务索引上限 `50` 作为首次且唯一的索引请求，不得先请求更大
页面探测上限。调用使用最长 60 秒的初始 yield；返回 `cell_id` 时必须对同一 cell 最多连续 wait 两次、每次最长
60 秒。cell 未终态前禁止发起第二次索引调用，`Script running` 不得解释为 unavailable、timeout 或 degraded。

`discovery_methods` 只允许终态枚举：`native_index_completed`、`native_index_host_cap`、
`native_index_terminal_failure`、`native_thread_pages_completed`、`native_thread_pages_terminal_failure`、
`execution_protocol_failed`。`complete` 必须同时包含
`native_index_completed` 与 `native_thread_pages_completed`；`bounded` 必须包含 `native_index_host_cap` 与
`native_thread_pages_completed`。index 明确终态失败使用 `degraded / native_index_terminal_failure`；index 已取得终态但
至少一个已选任务分页明确终态失败时使用 `degraded / native_thread_pages_terminal_failure`，同时要求
`truncated=true` 且完整读取数小于选择数，并保留其他正式证据独立支持的卡。未恢复 cell、非法参数或执行中断一律
为项目 `failed` 并记录 `execution_protocol_failed`；可以同时保留此前已经证明的 index 终态，但不得声称分页完成或
生成卡片。

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

`project_support` 精确包含
`count, project_refs, basis, coverage_note`。E2 的 count 通常为 1；E3 至少为 2。refs 必须是隐私安全的 opaque
identity，`basis` 与 `coverage_note` 必须说明独立证据与覆盖边界，不得再使用固定分母。

### Project Review Pack：`global_owner_scout_review_pack_v6`

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

Review Pack 顶层包含 `display_locale=zh-CN`，原样包含完整 `project_result`，并追加 owner parity、全部 review cards、`selection_preview`、限制和
`review_pack_hash`。每个 review card 按原始顺序引用一个不可改写的 `project_claim_hash`，附带对应 integration
preview、`recommended_action`、中文 `recommended_action_reason`、未来行为变化以及 `allowed_actions`。内部 E2/E3
Project Card 数必须等于 Review Pack 卡数。每个可确认卡还必须包含由当前 canonical source hash 派生的
`selection_token`；仅组合可确认的卡保留组合标识但不显示单项确认，其余卡该字段为 `null`。

`scout.py prepare-review` 从只读 runtime installation 绑定取得并验证实际 Core artifact，通过其 `preview-bundle` 对当前
本机 Owner 字节执行单项及完整组合预演。`selection_preview` 记录 artifact hash 与 Core 回执或明确错误；纯归属/已覆盖
结果为 `null`。Global relation 决定动作，不能沿用冻结 Project classification 推断全局增量。只有通过准确组合预演才
显示对应组合确认；失败时完整保留候选，先整理合并、替换或归属，再对新选择预演。预演不消耗批准，也不写 Owner/Store。

活动 Skill 的所有 Python 操作只能从 `scripts` 目录执行 `python -B scripts/scout.py <operation>`；dispatcher 复用
validator、Owner resolver、renderer、visible verifier 与 delivery 实现。确定性 renderer 只接受通过 validator 的
Review Pack，使用 `scout.py render-review --surface interactive|scheduled` 并通过 stdin 输入完整对象；禁止动态
import、直接猜选相邻 helper 或 renderer 失败后的模型手工重写。它按固定顺序生成 Markdown：中文结果状态、未执行规则变更的说明与覆盖/确认限制、
交互 surface 的`本次需要判断 N 项`或 Scheduled surface 的`今日需要判断 N 项`中文索引、全部完整决策卡、E1 与 Session/模型覆盖技术附录、简短校验回执。每张卡先显示
项目事件、用户成本、建议范围、具体 before/after、最大反例和全部可选动作构成的决策摘要，再显示完整核对依据。
用户可直接复制对应动作，无需先读技术材料或理解选择标识；确认仍绑定原有精确内容与令牌，不新增模糊批准入口。
协议状态、证据等级、Owner 关系及模型信息进入核对依据或技术附录；零候选只声明已核查范围没有合格增量。表格
最多四列，before/after 使用两列表格；不得依赖 HTML 折叠、自定义 App UI 或图片。宿主文件预览只承载相同
Markdown 字节，不得改写内容或成为新的语义层。默认
任何最终答复不得显示原始 JSON。renderer 回执包含 surface、可见正文 SHA-256、Project Card 数、可见卡数、
逐卡动作计数向量、动作总数和 wrapper 数。interactive 不得出现 Scheduled/Inbox/`0/14`/14 次文案且 wrapper
必须为零；scheduled 必须生成唯一且最后一个 Inbox wrapper。只读
`scout.py verify-visible --surface ...` 校验 renderer 或 artifact 的正文 hash、卡片和动作守恒、surface-specific
wrapper 数量、无原始 JSON和无手工尾注；它不证明实际用户 final。`degraded` 仍显示有独立正式证据的卡；
`failed` 显示可见失败终态，不制造空白结果。

### Interactive Delivery：`global_owner_scout_delivery_v1`

正式 interactive 入口不再把 renderer 全文交给模型搬运。它必须从 Skill scripts 目录运行
`scout.py prepare-delivery --artifact-dir <host-output-root> --protected-root <project-root>`，通过 stdin 输入完整 Review Pack。
`artifact-dir` 必须是当前任务上下文显式提供、已存在且位于所有 protected roots 外的 generated-output workspace；
不得猜测或回退系统临时目录、项目 `.sandbox`、任意 `$CODEX_HOME` 路径或另一个任务目录。宿主显式授予的 task output
root 即使物理位于其 app-managed storage 中仍然有效；资格来自当前任务 grant，而不是路径前缀。

Delivery v1 精确包含：

```text
contract_version, status, delivery_surface, artifact_name, artifact_sha256,
artifact_bytes, review_pack_hash, visible_body_sha256, project_cards,
visible_cards, visible_action_counts, visible_actions, bundle_action_count,
wrapper_count, delivery_manifest_sha256
```

`status=prepared`、`delivery_surface=task_artifact`。artifact 名称固定为
`global-owner-scout-review-pack-<review_pack_hash 前 16 hex>.md`；创建使用 exclusive 普通文件语义，既有同名字节完全
相同可以幂等复用，不同则失败。helper 必须在返回 manifest 前 flush、回读并重新运行 visible-output verifier。
manifest canonical hash 排除自身 hash 字段，不包含绝对路径、任务 ID 或 Review Pack 正文。

opened 与 queued receipt 生成必须同时接收 artifact path 与原 host-output root，并再次验证 direct-child
containment、普通只读文件、字节/hash 和 visible-output 守恒。随后 Agent 必须使用当前任务宿主的文件打开工具展示
该 artifact；这是 Scout 最后一个工具调用。只有明确 terminal opened/success 才进入成功分支；明确 `queued` 返回
同一 artifact 链接和 `surface_pending / confirmation_eligible=false` compact receipt，供用户发现与外部控制器验证，
但不计 Production。`pending`、缺失、失败或不可观察结果进入阻断分支。工具成功后 final 只返回 artifact 链接和
compact Delivery receipt；工具失败或缺少该表面时返回
`interactive_host_blocked`，不得显示部分卡片、确认命令或成功回执。`prepared` 与 open 成功仍只证明当前运行的
交付准备/表面调用；production 资格必须由外部 controller 回读实际 task final 与 artifact 后验证。

所有 Python helper 固定使用 `python -B`，安装器原子排除 `__pycache__`、`.pyc` 和 `.pyo`。Scout 在执行前后复核
个人 Skill 安装目录的字节码缓存指纹；任何新建或变化均属于外部写入并失败关闭，Scout 不得通过删除缓存掩盖失败。

### Manifest-free Terminal：`global_owner_scout_terminal_v1`

任何在 Delivery manifest 形成之前发生的 preflight、Session 协议、隐私/契约、只读、output root、renderer 或预算
阻断都必须构造并校验以下精确字段：

```text
contract_version, status, phase, reason_code, project_state, confirmation_eligible
```

`confirmation_eligible` 固定为 `false`；`phase` 只允许 `preflight`、`session_census`、`project_review`、`delivery`；
`project_state` 只允许 `unchanged`、`changed`、`unverified`。活动入口把完整对象传给
`scout.py render-terminal`，得到含 canonical object hash 的中文终态回执。该路径不需要 Delivery manifest，不能显示
部分卡片、路径或确认命令，也不能被手写 Markdown 替代。成功生成 manifest 后的 opened/queued/blocked receipt 继续
使用 `scout.py render-receipt`，两条路径不得混用。

`reason_code -> status / phase / allowed project_state` 固定为：

```text
project_binding_unavailable -> interactive_entry_blocked / preflight / unverified
git_worktree_ineligible -> interactive_entry_blocked / preflight / unverified
worktree_projection_unavailable -> interactive_entry_blocked / preflight / unchanged|unverified
output_preflight_unavailable -> interactive_host_blocked / preflight / unchanged|unverified
execution_protocol_failed -> failed / session_census / unchanged|unverified
read_only_violation -> failed / project_review / changed
privacy_or_contract_failed -> failed / project_review / unchanged|unverified
output_root_unavailable -> interactive_host_blocked / delivery / unchanged|unverified
render_integrity_failed -> render_integrity_failed / delivery / unchanged|unverified
output_budget_exceeded -> output_budget_exceeded / project_review / unchanged|unverified
```

宿主 open 发生在 manifest 形成后，只能走 manifest-bound blocked/queued/opened receipt，不属于 Terminal reason。

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
- 原生任务索引未取得终态、调用参数非法或执行协议中断时使用 `failed / execution_protocol_failed`；index 或 thread
  page 工具明确返回终态错误才分别允许 `degraded / native_index_terminal_failure` 或
  `degraded / native_thread_pages_terminal_failure`。运行内的失败包不得把 `failed` 再描述为
  “degraded / Session unavailable”。Scheduled 状态变更不属于只读 Scout；外部 Host Activation Control 观察到
  首次协议错误后执行并复读 `PAUSED`。没有实际控制面调用时只能报告“需要暂停”，不得声称已暂停。
- 输入缺失、结构不合法、E1 晋升、隐私泄漏、工作区变化、未经授权的外部写操作或无法证明只读时，该项目 Review Pack
  显示失败终态；不得输出未通过校验的卡。
- pre-manifest 失败必须通过 Terminal v1 renderer 输出，不得把失败对象交给 Delivery manifest receipt，也不得手写
  `interactive_host_blocked`。
- renderer、artifact 创建/回读、宿主打开或实际 final 回读失败，正文 hash/卡片/动作不守恒、surface/wrapper
  不匹配或存在手工尾注时，整次运行使用 `render_integrity_failed`、`output_budget_exceeded` 或
  `interactive_host_blocked` 失败终态；不得展示部分卡片或手工生成替代 Markdown。
- 宿主明确返回 `queued` 时，必须保留经同一 manifest 绑定的 artifact 链接并返回 `surface_pending`；它只证明内容
  可发现且可外部复核，确认保持关闭，也不得计入五条入口矩阵。
- Python helper 产生或修改字节码缓存时按外部副作用失败；缓存清理由安装阶段负责，自动 Scout 不得自清理。
- 当前 Scheduled 宿主强制每个 automation 读取并更新自身 memory，并在最终答复末尾追加一个 Inbox directive。
  二者是宿主控制面 wrapper，不是 Scout 证据、候选 Inbox 或去重状态。memory 只允许记录运行时间、覆盖/终态、
  卡片数量或 hash、只读/parity 结果；不得记录原始证据、卡片正文、候选语义或去重判断。确定性 Review Pack 与
  校验回执仍是完整人工审阅内容，单个 Inbox directive 仅负责让该任务在 Scheduled 中可见。普通 worktree 前向
  测试不读写 automation memory；`host_automation_memory_read/updated` 必须同为 true 或同为 false，且始终不得作为证据。
- 若更高层运行时要求执行后置 Agent Memory 审计，该审计保持静默并复用已渲染的卡片与校验回执作为终态；不得
  调用独立 `agent-memory` Skill、追加第二条 memory 状态、proposal 或治理回执。interactive 的宿主 artifact open
  必须是最后一个工具调用；scheduled 继续使用可见输出 verifier 和唯一末尾 Inbox wrapper。
- 活跃原工作区的并发变化只记录为当前隔离快照之外的限制；稳定隔离快照中的卡不得因此整体失效。
- 2026-08-11 的三个真实 v5.1 Scheduled 运行及最小 automation-source probe 证明本主机原生任务索引未取得终态。
  每个 Host Enrollment 保持 `0/14`，自动化保持 `PAUSED`；普通 worktree 前向测试不再拥有恢复权。只有新的真实
  automation-source canary 在外部 180 秒观察预算内取得终态后，才可恢复一个 Skill 5.9.0 项目 canary；
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
longitudinally_effective`，并按入口分别报告。Fresh 反例已撤销旧的三个 inline canary 交付层证明；当前必须报告
`interactive_project_scout=production_unproven / interactive_host_blocked`，直到五条真实入口矩阵的同任务
artifact 与实际 final 外部回读通过；`scheduled_project_scout=production_blocked / PAUSED / 0 of
14`，`owner_continuity=adoption_unproven`。跨设备冷启动只有空 profile 与受管源契约验收时必须报告
`cross_host_bootstrap=implementation_verified / production_unproven`，直到真实第二台设备完成首次加载、Doctor 与
交互 canary；不得用任一主机或入口的测试替代另一主机或入口的生产证明。

真实入口 canary 在创建前必须绑定正式入口实际解析的 installed Scout version 与 content identity。验收矩阵至少包含
Local clean 自动投影、Local dirty 自动投影、already-worktree 原地执行、thread-page 明确终态失败降级和缺少
output root 的 Terminal v1 五条切片。工作树包含较新
Skill 源码不等于该任务采用它；若任务解析旧版本、没有 Delivery v1 或返回 legacy inline Review Pack，则结果固定为
`ineligible / runtime_skill_identity_mismatch`，不计通过、失败或五条入口矩阵分母。先由 commit-bound
Bootstrap/Release 完成安装与新任务发现，再重跑前台可见验收。

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
  "sidecar": {"remote": "https://example.invalid/agent-memory-sidecar.git", "ref": "v0.3.5", "commit": "<40 hex>"},
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

该管理员操作固定为 `release_promotion_v1`。`inspect` 必须保持零写入，并输出
`agent_memory_release_promotion_plan_v1 / authorization_required`；计划精确绑定 public repository、vSemVer tag、full
commit、clean HEAD、annotated local tag、remote main/peeled tag、Changelog release section、immutable-releases enabled、
local `SHA256SUMS`/release manifest 与远端 uploaded asset 的有序 name/bytes/SHA-256 集合，以及
`is_draft=false / is_immutable=true` 目标。`apply` 只接受 fresh exact `plan_hash`，随后只执行一次 draft publication；
成功前必须验证 Release attestation、每个本地资产的 Release attestation，并回读 publication timestamp、non-draft、
immutable 与未漂移资产集。成功输出 `agent_memory_release_promotion_receipt_v1 / public_published`。远端 mutation 后任一
验证失败都不得声称回滚或仍处于 draft，必须返回 blocked 并重新只读确认实际远端状态。

`refs/tags/v*` 从首次远端创建即 write-once，而不是等 Release publish 后才不可变。只有完整版本 PR 已合入 clean、
同步的 public `main`，且本地 annotated tag 上完整 release build 通过，才首次 push tag。同 source commit 的 draft
workflow 失败可幂等重试；任何要求新 commit 的修复都必须删除 stale draft、保留旧 tag 与 ruleset、使用下一语义版本。

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
