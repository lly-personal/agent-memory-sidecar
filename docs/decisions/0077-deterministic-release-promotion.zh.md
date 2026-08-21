# ADR 0077：不可变 Release 发布采用确定性检查计划与终态回读

- 状态：Accepted
- 日期：2026-08-21
- 关联：[L1](../specs/axioms.md)、[L2](../specs/topology.md)、[L3](../specs/interface.md)、[Release Promotion v1](../../specs/release-promotion-v1.md)、[Public Authority Cutover](../../specs/public-authority-cutover-v1.md)

## 背景

Tag workflow 已有意停在完整 draft，避免把管理员权限放入公共 CI；但从 draft 到 immutable Release 只剩自然语言步骤。
这造成两个相反风险：Agent 可能把 draft 误报为发布完成，也可能在用户已授权整批发布时仍逐步追问。`v0.3.6`
准备过程中还实际发现 Changelog 保留 `unreleased` 文案，说明资产完整不等于用户可见发布内容已就绪。
后续修复合入后又发现 `release-tag-immutability` ruleset 从 tag 首次远端创建即禁止 update/delete，且维护身份不可旁路；
因此“draft 仍可修改”等价于“tag 也可重建”的假设不成立。

## 决策

1. 保持 CI 的现有最小权限和 draft-only 边界，不增加管理员 Token、环境服务、数据库或自动发布。
2. 新增独立 `publish_release.py`：inspect 只读绑定 Git/tag/commit、Changelog、immutable policy、local/remote asset
   digests 与目标终态，并输出稳定 `plan_hash`。
3. apply 必须在发布前重算并消费同一 hash；发布后逐资产验证 Release attestation，并回读 non-draft、immutable 与
   publication timestamp，才生成 `public_published` receipt。
4. 发布与工作站部署、Skill 自动发现、真实新任务采用继续分层验收。一次整批授权可连续执行所有已声明步骤；只有
   来源身份替换或新的不可推导破坏性范围才再次停下确认。
5. 远端 release tag 从首次 push 即 write-once。Tag 只能在最终版本 PR 合入、clean main 同步且本地 tag 构建通过后
   首次推送；同 commit 可重试 draft workflow，任何 source repair 必须撤回 stale draft 并提高语义版本，不修改 ruleset。
6. 本地 tagged build 与 Ubuntu CI draft 是独立证据通道。前者证明本地构建能力，后者的原始 Release asset digest 与
   attestation 证明实际待发布字节；跨宿主 archive hash 不假定相等，任何完成声明都必须标明所依赖的通道。

## 结果与代价

发布者只面对一个计划和一个终态回执，不再手工拼接命令或自行判断中间状态；代价是 GitHub CLI 与 Administration
read 权限成为显式前置条件。发布动作本身不可回滚，因此任何 post-mutation 验证失败都必须报告“远端当前状态未知或
不合格”，不得把失败包装成仍可安全重试的 draft。修复已发布内容只能提高语义版本。
这一约束会消耗一次错误分配的版本号，但把安全规则保持为常量，也让 Tag、Release 与 source commit identity 始终单值。
