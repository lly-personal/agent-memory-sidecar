# Agent Memory Core v1 Operator 参考

- Status: active
- Owner layer: project_docs
- Last verified: 2026-08-22
- Evidence: [Core v1 contract](../specs/agent-memory-core-v1.md)、[ADR 0057](decisions/0057-agent-memory-core-v1.zh.md)、[ADR 0059](decisions/0059-bounded-behavior-set-evolution.zh.md)、[ADR 0076](decisions/0076-task-scoped-review-pack-delivery.zh.md)、[Public distribution v1](../specs/public-distribution-v1.md)、[Public authority cutover v1](../specs/public-authority-cutover-v1.md)

## 所有权

```text
Agent/Skill -> Rule Service -> actual AGENTS.md -> later Desktop task
Hook -> Runtime Ledger
User -> authorization
```

- `AGENTS.md` 是唯一行为权威。
- Agent/Skill 判断候选是已覆盖、新增、替换、归并或应路由到其他 owner；该分类不持久化。
- Rule Service 确定执行授权、scope、revision hash、容量、漂移、文件事务和撤销。
- Runtime Ledger 只保存有界事件、session、proposal token。
- Authorization Ledger 只保存一次性授权消费。
- Git 只负责完整 global 文档分发，不决定本机是否生效。

## 公开命令

```powershell
python -m agent_memory_sidecar rule list
python -m agent_memory_sidecar rule deploy --from-json .\rule.json --approval-ref <current-ref>
python -m agent_memory_sidecar rule deploy --from-json .\revised.json --approval-ref <current-ref> --supersedes <rule_id>
python -m agent_memory_sidecar rule deploy --from-json .\merged.json --approval-ref <current-ref> --supersedes <first_rule_id> --supersedes <second_rule_id>
python -m agent_memory_sidecar rule revoke <rule_id> --approval-ref <current-ref>
python -m agent_memory_sidecar setup
python -m agent_memory_sidecar setup --apply
python -m agent_memory_sidecar doctor
```

旧 `status/remember/forget` 与旧诊断、rollout、benchmark、clean-store、instruction-cutover 命令没有别名。
内部实验命令仅为 `proposal create/replace/confirm/discard`。

机器结果使用 `agent_memory_result_v1`。退出码 `0` 表示成功或幂等 no-op；任何失败为 `1`，原因在
`error.code`。

## 七字段与容量

```json
{
  "trigger": "何时适用",
  "action": "执行什么",
  "skip_boundary": "何时跳过",
  "scope": "project",
  "why": "为什么值得复用",
  "evidence": "当前事实",
  "instruction_target": "project_agents"
}
```

`project/project_agents` 与 `global/global_agents` 必须严格配对。七字段 hash 定义规则内容；
`rule_revision_v1` 另行绑定 instruction target、修改前完整文档 hash 和排序后的 superseded IDs。

Review Pack 多选使用 `rule deploy-bundle` 与 `rule_revision_bundle_v2`。Bundle 中每项包含 card/project claim、
完整七字段 proposal、自己的 superseded IDs 与可见 `selection_token`，顶层包含完整 target before hash；所有项必须
属于同一 scope/target。用户回复必须逐字等于按 card ID 排序的 `确认 card_id@token[、...]`。服务把选择解释为
无序集合，在同一 before snapshot 上计算一个完整 after，使用一次 approval 并执行一个文件事务。任一项失败时
整包零写入。Fresh 检查已知目标时使用
`rule list --target global_agents|project_agents`。

Scout 5.6 的 interactive 交付由 `prepare_delivery.py` 内部完成：output root 必须由当前任务宿主显式提供且位于项目
外；artifact 成功打开后只返回 compact receipt；宿主明确返回 `queued` 时返回带同一 artifact 链接的 pending
receipt，确认关闭。生产验收控制任务从实际 Scout final 读取 artifact 路径，并以
`prepare_delivery.py --verify-final --artifact-root <host-output-root>` 验证；内部 renderer/verifier 输出或文件存在不
能替代 `surface_observed`。`surface_pending` 只证明完整内容可发现且字节守恒，不计 Production。

每条渲染后不超过 1 KiB；每个完整 managed block 不超过 8 KiB。超限整次拒绝且不消费授权，错误详情返回
`before_bytes`、`projected_bytes` 与 `budget_bytes`。`rule list` 的 `targets` 返回 managed、budget、
remaining、完整文档字节和规则数；8 KiB 不约束块外正文。

一个 `--supersedes` 表示替换；重复参数表示归并。所有 ID 必须唯一、存在于同一 target。新规则进入最早
被替换位置，其余规则顺序和块外字节保持不变。

## Core Store

新 Store 只有七张表，目录/文件在 POSIX 固定为 `0700/0600`，Windows ACL 只允许当前用户和 SYSTEM；链接、
重解析点或多硬链接 Store 拒绝打开：

```text
core_schema
prompt_events
runtime_sessions
proposal_tokens
approval_consumptions
runtime_installation
global_instruction_binding
```

不得创建 `memories`、`memory_mutations`、`runbooks`、`runtime_deliveries` 或通用 `state`。文件事务的
短期恢复日志位于 Store 相邻目录，只用于确定前滚或回滚。

## Setup 与 immutable runtime

`setup` 是新设备安装 owner。无 `--apply` 时只预览；`--apply`：

1. 创建或验证 Core Store；
2. 构建带内容 SHA-256 的标准库 zipapp；
3. 安装并自检 artifact；
4. 安装 canonical Skill；
5. 原子写入 `UserPromptSubmit` 和 compact-only `SessionStart` Hook；
6. 记录安装身份并执行 doctor。

Hook 命令只引用 immutable artifact，不引用 editable checkout。遇到 legacy schema 时返回
`migration_required`，绝不自动升级。

## 公开安装与分发

- `setup --apply` 不带 global source 是 `core_public`：Core project scope、Runtime、Store、Skill 与 Doctor 可用，
  global binding/Owner parity 明确 unavailable。若该主机已存在 global binding，Bootstrap 必须以
  `public_core_existing_global_binding` 阻断并等待显式解绑/迁移决定，不得把旧绑定伪报为 unavailable。
- `owner_integrated` 另外提供 clean、commit-bound canonical Owner；未配置时不得搜索替代 Owner。
- Workstation Bootstrap 2.1.0 以 `workstation-reconcile --dry-run` 与 exact-hash apply 统一 Marketplace/Plugin/source/host；
  底层 `source-cutover`、`sync-sources` 与 `materialize-host` 继续保持严格、无独立完成声明。期望 Release 身份与真实
  Codex/物理读回不一致时不得生成 `ready`。
- 正常 Desktop 首跳固定为 `codex plugin marketplace add lly-personal/agent-memory-sidecar --ref v0.3.10` 后
  `codex plugin add agent-memory-sidecar@agent-memory`。Marketplace 只提供 Anchor；Anchor 的 Resolver 验证 stable immutable
  Release、tag/commit、asset digest、checksums 与 manifest，安全展开 portable，并在同一任务执行正式 Bootstrap。
- 已有受管 Sidecar identity 不同时，普通 `sync-sources` 必须继续失败。统一入口只展示一次短计划并取得一次确认，
  再以 fresh `plan_hash` 原子 apply；公开 manifest 不携带 Owner 时，仅在既有 clean checkout 与 Core binding
  root/commit 精确一致时保留私有 Owner，解绑不是隐含动作。
- `build_public_export.py` 只保留为首个公开 seed 的 provenance 工具；`public_active` 后不得再次从冻结私有工程导出。
  后续 `build_release_artifacts.py` 只从公开 commit 和精确指向该 commit 的 `v<Core>` tag 生成 Core wheel/sdist、portable
  bundle、SBOM、source manifest、checksums 和 release manifest。
- `public_artifact_verified` 不等于 public repository、Release、PyPI 或新任务采用；外部发布仍需独立授权和远端复读。
- 当前 `PUBLIC_AUTHORITY.json` 已把公开 `main` 固定为 `public_active`；旧私有工程源只读冻结。后续代码、规范、Issue、
  PR、tag 与 Release 只从公开仓库演进，不再执行私有 export 或双向同步。
- seed 阶段 release builder 要求 export receipt 与 tracked snapshot 精确相同；`public_active` 后改为验证 marker、
  初始 Release tag/commit 和祖先关系，后续版本直接从公开 Git 演进，不再刷新私有 export receipt。
- Tag workflow 只在 public repository 创建/恢复 draft 并上传、比对全部资产；它不持有管理员 Token，也不自动
  publish。阶段 C 只使用 `publish_release.py inspect` 生成绑定 commit、Changelog、immutable policy 与完整资产摘要的
  `plan_hash`；`apply --plan-hash <hash>` 重算同一计划，发布后逐资产验证 attestation 并回读
  non-draft/immutable。PyPI 不属于该首发链。
- 远端 tag 只能在版本化 Changelog、组件兼容行和包元数据一致后创建。先在目标公开 commit 上建立本地 annotated
  tag，并从该 clean tag/HEAD 执行完整 `build_release_artifacts.py`；只有本地发行构建成功后才能首次推送同一 tag。
  受保护远端 tag 从首次推送即 write-once，与 Release 是否仍为 draft 无关。同 commit 的 workflow 可重试；若修复改变
  source commit，删除 stale draft 并提高语义版本，禁止修改 ruleset 或更新/删除旧 tag。
- 本地 tag 构建与 CI draft 资产是两条不同证据通道：前者证明当前 commit 在操作者宿主可完整构建和消费；后者的
  GitHub 原始资产、SHA256SUMS 与 attestation 才是待发布字节。Windows 与 Ubuntu 独立构建的 archive hash 不默认相等，
  不得用本地 hash 替代 CI 资产逐字节读回，也不得用 CI 绿色替代 tag 首次推送前的本地构建能力门禁。

```powershell
python scripts/publish_release.py inspect --asset-dir dist/release --repository lly-personal/agent-memory-sidecar --tag v0.3.10 --expected-commit <full-sha>
python scripts/publish_release.py apply --asset-dir dist/release --repository lly-personal/agent-memory-sidecar --tag v0.3.10 --expected-commit <full-sha> --plan-hash <hash>
```

Inspect 零远端写入。Apply 仅在本次用户授权覆盖公开发布且 hash 仍 fresh 时执行；成功回执只证明
`public_published`，不能升级为本机部署、Skill 发现或真实新任务采用。

## Global 双目标事务

Global deploy/revoke/consolidate 先验证 Git source、本机 target、完整文件 hash 与 override，再按稳定顺序
锁定两文件。两份 managed block、revision 计划与外围字节都验证通过后才消费授权。任一步失败恢复两份
原始字节。

成功仅证明本机 `生效中`，并返回 `publication_required=true`。Agent 还需独立完成私有 Git commit、push 和
远端完整文件 hash 验证，之后才能声称跨设备分发完成。

## Legacy Store cutover

```powershell
python -m agent_memory_sidecar maintenance core-cutover --dry-run
python -m agent_memory_sidecar maintenance core-cutover --apply --plan-hash <hash> --approval-ref <current-ref>
```

Dry-run 零写入，给出 schema、表计数、复制/丢弃政策、artifact hash、备份目标与稳定 `plan_hash`。Apply 必须
获得一个新的当前授权：

1. 获取维护锁；普通 Hook 在锁期间 fail-open。
2. 创建永久保留的完整 SQLite backup 与 `.sha256`。
3. 在相邻临时库建立 Core schema。
4. 复制保留期事件/session、可关联授权消费、database namespace 与 global binding。
5. 使所有旧 proposal token 失效。
6. 验证 FK、schema fingerprint、计数、隐私边界和 integrity。
7. 用新 zipapp 自检临时库。
8. 替换 Store 与 Hook；失败时恢复旧 Store、Hook 与文件。

备份不参与自动 retention。没有单独 apply 授权时必须停在 dry-run。

## 验证边界

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -v
python scripts/check_doc_links.py
git diff --check
python -m agent_memory_sidecar doctor
```

自动化必须覆盖 schema、授权、容量、单/多规则 revision、旧 add-only token、双文件事务、迁移回滚、
compact no-write、result contract 和性能阈值。
Doctor 只证明配置与 artifact 一致；真实 Desktop 新任务才证明 deploy/adopt/revoke、跨项目、primary folder、
compact 与 Memories-off。Ambient 单卡/control 仍为 experimental，不阻塞 Core。
