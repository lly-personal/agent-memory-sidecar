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
3. apply 必须在发布前重算并消费同一 hash；发布后用一次原生 Release 验签的已验证结果核对全部资产，并回读 non-draft、immutable 与
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

## 2026-11-02：删除同一发行的重复验签

用户指出发布、部署和验收耗时与预期不符。取证先分开工具运行、CI 和 Agent 编排：本轮 PR/main CI 的最长 job
分别为 214/255 秒，Release CI 的 job 执行窗口为 46 秒，其中构建步骤为 12 秒；本机部署 dry-run 为 1.35 秒、apply 为 9.55 秒。
普通项目的安装后规则查询为 0.12 秒、Doctor 为 0.27 秒。这些是各自运行窗口，不能相加为用户等待时间。
本次 Agent 还发生过猜错路径、merge 模式和 tag 参数的操作错误；这部分成本应由执行者纠正，不能归咎于 CI。

调研材料与取舍：

- [Tw93 的 CI 提速原帖](https://x.com/HiTw93/status/2116797957454401746) 提倡拆分实际耗时、删除重复工作并实测结果。
  本轮采用这个方法，没有把帖中的检查数量、缓存或并发配置当成所有项目的固定门槛。
- [21 条实践](https://tw93.fun/2026-10-29/practice.html) 和其 [V2EX 讨论](https://www.v2ex.com/t/1252719)
  强调项目回归与按项目沉淀。讨论中的宿主规则读取差异只是线索，不能变成未验证的通用事实；作者个人的逐次确认
  偏好也不替代本工程已有的整批授权。
- [客户端原生能力与借力](https://tw93.fun/2026-10-22/desktop.html) 提醒以用户结果选择实现；本轮没有为优化增加服务。
  [Waza 的实际 CI](https://github.com/tw93/Waza/blob/main/.github/workflows/test.yml) 保留 main 每次检查，不能从文章推导出
  “合并前通过就删除 main 验证”。本仓库最近 15 次运行没有同一 PR 新旧运行重叠，暂不新增取消运行配置。

改变决定的直接证据是 [GitHub 原生 Release 验签](https://cli.github.com/manual/gh_release_verify) 已返回所有资产的
已验证 statement。对照 [gh 2.102.0 verify](https://github.com/cli/cli/blob/v2.102.0/pkg/cmd/release/verify/verify.go)
和 [verify-asset](https://github.com/cli/cli/blob/v2.102.0/pkg/cmd/release/verify-asset/verify_asset.go)，两者使用相同的
tag digest 和签名验证器，后者再次取证和验签，只额外匹配本地文件摘要。原发布器对 7 个资产重复了这段工作。

因此删掉逐资产原生命令，仅消费本轮 `verificationResult.statement`：核对类型、repository/tag/purl、annotated tag
对象摘要和全部唯一资产的名称/SHA-256；网络调用结束后重读本地文件，并与授权计划比较。空结果、未验证 envelope、
错误身份、遗漏、重复、额外资产、错误算法、摘要变化和本地输入漂移均失败；不缓存跨发布验签结果。

在同一主机、gh 2.102.0、同一 v0.5.2 的 7 个 CI 资产上，旧路径 8 次原生验签为 48.63 秒，新路径 1 次为 5.37 秒
（含本地 tag 与全资产比对），本次减少约 89%。这是一次配对观测，网络条件和其他发行仍待验证，不是 SLA 或完整
发布周期提速比例。真实验收是已发布资产的只读验证；下一次发布的完整 apply 仍需其自己的终态回读。

验收保留原有发布、回滚边界和全部兼容矩阵，并增加上述反例回归。通用层已有按规模执行、消融与有效证据复用的
规则；本次将具体改变归入本 ADR 和既有发布契约，不新增全局规则、第二套流程或维护服务。
