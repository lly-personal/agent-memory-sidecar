# ADR 0076：任务级 Review Pack 交付与宿主表面证明

- 状态：Accepted
- 日期：2026-08-21
- Owner layer：user / project_docs
- 扩展：[ADR 0063](0063-direct-visible-owner-review-packs.zh.md)、[ADR 0066](0066-scout-execution-and-visible-output-integrity.zh.md)、[ADR 0068](0068-interactive-project-scout-primary.zh.md)
- 保留：[ADR 0071](0071-wysiwys-review-pack-bundles-and-physical-target-containment.zh.md) 的所见即所签绑定

## 背景

连续三次同类 Project Scout 运行证明，Project Card、Review Pack validator、renderer 与内部 visible-output verifier
可以保持稳定，而用户最终收到的聊天正文仍会在 renderer 之后被宿主或模型截断、改写或手工恢复。六卡结果曾完整
交付；七卡结果的实际 final 已与 renderer hash 不同；八卡结果只恢复了短摘要并丢失 validation receipt。模型、CLI、
Skill 核心流程和项目事实没有形成对应变更变量。

这推翻了 `interactive_project_scout=current_host_production_proven` 的交付层结论，但不推翻已经独立验证的 Project
Card、Owner parity、Review Pack 语义、renderer 能力或只读证据。根因是当前 verifier 只验证交给它的字符串，无法
观察随后真正进入用户界面的 final bytes；把大段 Markdown 再交给模型搬运不是一个可验证的产品边界。

## 决策

### 结果层立即降级

`interactive_project_scout` 立即回到 `production_unproven / interactive_host_blocked`。任何 validator、renderer、
文件写入或工具成功都只能证明各自结果层；只有实际同任务用户表面经过外部回读验证，才可恢复
`current_host_production_proven`。

### 交付控制面

新增 `global_owner_scout_delivery_v1`，不改变 `global_owner_scout_project_v4`、
`global_owner_scout_review_pack_v4` 或 `selection_token`。Delivery v1 只绑定：

```text
contract_version, status, delivery_surface, artifact_name, artifact_sha256,
artifact_bytes, review_pack_hash, visible_body_sha256, project_cards,
visible_cards, visible_action_counts, visible_actions, bundle_action_count,
wrapper_count, delivery_manifest_sha256
```

`status=prepared` 只证明 artifact 已从确定性 renderer 字节创建并完成同文件回读；
`delivery_surface=task_artifact` 只允许当前任务的宿主生成文件表面。manifest 不包含绝对路径、任务 ID、Owner 正文或
项目事实正文，也不写 Store。

### 同任务 artifact 是输出，不是文件桥

正式 interactive 路径为：

```text
validated Review Pack v4
-> deterministic renderer bytes
-> visible-output verifier
-> immutable task artifact + Delivery v1 manifest
-> host opens the artifact in the same task, or explicitly reports queued
-> compact final receipt
-> external controller reads the actual task result and verifies the surface
```

artifact 只能写入宿主为当前任务提供、且位于被复盘项目工作树之外的 generated-output workspace。目标目录必须由
当前宿主上下文显式提供；Skill 不猜测目录、不写系统临时目录、不写项目 `.sandbox`、不把任意 `$CODEX_HOME`
路径当后备，也不把 artifact 复制到另一个任务。宿主显式授予的 task output root 可以物理位于其 app-managed
storage 中；资格来自 task grant，而不是路径前缀。目标文件名由 Review Pack hash 确定性派生，创建后按原始 UTF-8
字节回读校验。

这不恢复 ADR 0063 已拒绝的文件结果桥：artifact 不被跨任务发现、摄取、排队或持久治理，不是 Candidate Inbox、
Store、数据库、Manifest 或行为 Owner。用户只在产生它的当前任务内查看和选择。

### 后台任务的 queued 事实与两阶段状态

首条真实 worktree canary 证明：后台创建的 Scout 任务可以完整生成并校验四张卡的 artifact，但宿主文件预览返回
`queued`；同一控制任务再次打开该文件也返回 `queued`。这不是 artifact 或 renderer 失败，也不是用户表面已打开。
因此 Delivery v1 保留三种精确结果：

- `open_succeeded -> surface_observed / confirmation_eligible=true`：唯一可计入主机 Production 资格的结果；
- `open_queued -> surface_pending / confirmation_eligible=false`：final 必须保留经 manifest 绑定的原 artifact 链接，
  controller 重验字节、hash、卡片和动作后只证明内容可发现；
- `open_failed -> interactive_host_blocked / confirmation_eligible=false`：没有可验证 artifact 链接，不显示替代内容。

`surface_pending` 解决“完整内容再次不可发现”的体验缺口，但绝不把后台排队改写成已展示，也不计入三条 Production
canary。用户随后查看任务时可打开原链接；在得到可观察 opened 证据前，确认入口保持关闭。

第二条真实 worktree canary 还证明 Desktop 实际 final 会在 helper 回执末尾追加一个空行。controller 只允许把“标准
单换行 + 一个宿主空行”归一成标准单换行；三个以上末尾换行、空格、尾注、字段或正文变化仍失败关闭。这是宿主
envelope 归一化，不是对回执语义或 hash 的宽松比较。

后续第一条前台可见 canary 又证明：任务 worktree 虽包含 Scout 5.6.0 源码，正式 `$global-owner-scout` 入口仍解析
用户安装的 5.5.0，最终返回 legacy inline Review Pack。该运行的前台可见性不能替代消费者身份，因此固定归类为
`ineligible / runtime_skill_identity_mismatch`。从此 controller 在创建 canary 前必须绑定 installed Skill version/hash；
只有 commit-bound Bootstrap/Release 安装后的新任务才有资格进入 Delivery v1 验收。

### 失败关闭

以下任一条件使 interactive 结果成为 `interactive_host_blocked`，且不得显示部分卡片、确认命令或成功回执：

- 当前任务没有明确的 host-generated output root；
- output root 位于被复盘项目工作树内，或目标不是安全的普通文件；
- artifact 已存在但字节不相同，或创建、flush、回读、hash 校验失败；
- 宿主既未明确打开也未明确排队 artifact；
- compact final receipt 未在实际任务结果中守恒；
- 外部 controller 无法读取或验证真实用户表面。

不得退回大段 inline 搬运、手工摘要、项目文件、系统临时文件、Store 或中央服务。Scheduled 继续
`production_blocked`，不随本 ADR 恢复。

## 验收

1. Delivery helper 对 0、1、3、6、7、8、24 卡真实长度 fixture 生成不可变 artifact；artifact bytes、body hash、
   卡片、逐卡动作、总动作和 wrapper 守恒。
2. output root 位于任一 protected project root 内、目标目录为 link/reparse、既有同名文件字节不同、artifact 被篡改
   或缺失时全部失败关闭，项目与 Owner 零修改。
3. 当前任务通过宿主工具打开 artifact，用户可直接查看完整中文卡片；聊天只返回 compact receipt，不再搬运全文。
4. 宿主明确返回 `queued` 时，聊天返回带原 artifact 链接的 compact pending receipt；controller 验证为
   `surface_pending`，确认关闭且不计 Production。
5. controller 读取实际新任务 final，验证 receipt 与 artifact；内部 tool output 不得替代该证据。
6. 三个独立 Git worktree canary 均通过精确入口、同任务 artifact、实际 final 回读和只读守恒后，才恢复
   `interactive_project_scout=current_host_production_proven`。
7. 用户从 artifact 复制的 canonical `确认 <card_id>@<selection_token>[、...]` 仍由现有
   `rule_revision_bundle_v2` Fresh 重算，不增加长期 Review Pack 状态。
8. canary 创建前必须验证正式入口的 installed Scout version/hash；任何 runtime identity mismatch 或 legacy inline
   envelope 都标记为 ineligible，不计三条样本。

## 平台依据

- [Work with files](https://learn.chatgpt.com/docs/artifacts-viewer)
- [Git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)

官方文档证明 Desktop 可以在聊天旁预览生成文件，但不承诺 Scout 专用持久 artifact API。因此 host-generated
output root 与同任务打开必须在每个实际入口中 Fresh 证明；不可用时保持阻断。

## 非目标与回滚

不增加数据库、MCP 服务、跨任务文件桥、候选 Inbox、后台摄取、自动确认、项目内报告文件或第二 Owner。回滚删除
Delivery helper 并恢复本 ADR 对应的 L1/L2/L3/Skill 变更；在旧 inline 路径重新通过真实用户表面验收前，回滚不能
恢复 `production_proven`。
