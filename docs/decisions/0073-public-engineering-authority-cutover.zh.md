# ADR 0073：公开工程权威切换与私有工程源归档

- Status: accepted
- Date: 2026-08-14
- Owner layer: project_docs
- Amends: ADR 0072 中“现有私有仓库继续作为工程源”的长期解释；该结论只适用于首次公开候选和首发资格阶段
- Extends: [L1](../specs/axioms.md)、[L2](../specs/topology.md)、[L3](../specs/interface.md)、[公开分发契约](../../specs/public-distribution-v1.md)、[公开权威切换契约](../../specs/public-authority-cutover-v1.md)

## 问题

ADR 0072 正确解决了“不能原地公开带历史和隐私的工程仓库”，但如果独立公开仓库永远只是私有工程源的发布镜像，
后续贡献、问题、修复、CI 与 Release 仍要在两个 Git 面之间搬运。这样会让同一公开产品形成两个可能漂移的工程真理源，
增加维护者和贡献者的判断成本，也与单一权威、奥卡姆约束和真实开源协作目标冲突。

公开仓库创建、发行物生成和研发权威切换还是三个不同事实。仓库可见或 Release 已发布都不能自动授权维护者停止
私有工程源，也不能证明公开入口已安装。

## 决策

1. 公开产品研发只允许 `private_engineering`、`public_candidate`、`public_active` 三个时期，并且每个时期恰有一个
   工程权威。`public_candidate` 期间私有仓库仍是唯一权威，公开仓库只是待验收快照。
2. 首次公开候选继续使用 ADR 0072 的白名单导出与 export receipt。该导出链是一次性引导和首发 provenance，
   不是长期同步协议；不增加双向镜像、后台同步或隐藏 upstream。
3. 公开工程权威激活必须同时具备：公开仓库与安全设置回读、首个 immutable Release、干净环境 artifact 安装、
   远端发布回读，以及单独的人类明确确认。发布、安装、采用、连续性和产品效果仍分别陈述。
4. 激活后由公开 `main` 唯一拥有公开代码、规范、测试、Issue、PR、CI、Tag 与 Release。当前私有工程仓库先写入
   最终指向说明，再冻结归档；不得继续修改或向公开仓库导出同一产品。
5. 激活提交用 `agent_memory_public_authority_v1` 的 `PUBLIC_AUTHORITY.json` 固定初始 Release、公开仓库 identity、
   私有工程 source commit 与初始 snapshot digest。它只为后续 release builder 区分首发 seed 与公开原生演进，
   不进入 Core Store、不成为行为 Owner，也不替代人类授权和远端回读。
6. 首发 Tag workflow 只在 public repository 上构建、证明、创建/恢复 draft、上传并核对完整资产，然后保持 draft。
   immutable-release 设置需要 Administration(read)，不得为自动 publish 向公共 CI 注入长期管理员凭据。正式 publish
   由另一次明确授权的管理员操作在发布前检查 immutable 设置，并在发布后逐资产验证和回读。当前私有仓库、Tag、
   Release 和 public visibility 本次不改变。
7. 可选私有 Global Owner 继续作为显式 commit-bound 后端；它不随权威切换公开，也不拥有公开 Core 的研发方向。

## 为什么不长期双轨

- 单向镜像仍需要持续判断哪边能接受修改，并会让公开 PR 无法成为事实源。
- 双向同步需要冲突解决、身份映射和额外权限，不能降低 Agent Memory 的核心连续性成本。
- 把私有证据继续混入公开工程会重新引入 ADR 0072 已消除的隐私和历史风险。
- 归档而不是删除私有仓库，可以保留审计与回滚证据，又不会维持第二个活跃工程源。

## 代价

- 首发前需要一次明确的法律、公开仓库、安全设置、Release 和安装验收。
- 权威切换后，私有发现必须脱敏后通过公开 Issue/PR 进入产品，不再能靠私有提交静默改变公开代码。
- 公开披露不可通过改回 private 完全撤销，因此创建公开仓库仍需要独立授权。

## 验收

- L1/L2/L3 与根契约对三个 authority epoch 使用一致名称和单一 owner 语义。
- 首发 seed 没有 `PUBLIC_AUTHORITY.json` 时，release builder 仍要求 export receipt 与完整 snapshot 精确一致。
- 后续公开提交只有在 marker schema、repository identity、初始 tag/commit 与祖先关系全部成立时才能构建 Release。
- Release workflow 在私有仓库不建 draft；在公开仓库只完成 draft 和全部资产核对，不自动 publish。管理员发布操作
  另行确认 immutable releases、publish 并回读。
- 本次设计实施不创建公开仓库、不选择或写入许可证、不打 Tag、不创建 Release、不修改本机 Store/Owner/Host Profile。
