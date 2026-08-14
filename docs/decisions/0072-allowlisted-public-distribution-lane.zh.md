# ADR 0072：白名单公开分发通道与可选私有 Owner

- Status: accepted
- Date: 2026-08-13
- Owner layer: project_docs
- Supersedes: 直接把现有私有仓库及其完整历史切换为 public 的方案
- Amends: ADR 0069 的私有 Sidecar `main` / repo marketplace source authority；公开通道只接受 portable release 中的
  commit-bound source manifest，不保留浮动分支兜底
- Amended by: [ADR 0073](0073-public-engineering-authority-cutover.zh.md)；私有工程源持续拥有研发权威只适用于首发候选期，
  首发验收和人工切换后由公开 `main` 唯一接管
- Extends: [L1](../specs/axioms.md)、[L2](../specs/topology.md)、[L3](../specs/interface.md)、[公开分发契约](../../specs/public-distribution-v1.md)

## 问题

当前仓库同时承载稳定 Core、Plugin/Skill、主机 Bootstrap、私有 Global Owner 集成、历史 ADR、真实运行证据和
个人主机诊断材料。把仓库原地切换为 public 会把产品源码公开与历史/隐私公开绑定成一个不可逆动作，并且当前
安装链仍会从浮动 `main` 拉取两个源。即使 Core 测试通过，这也不能证明陌生用户能够依法复用、从不可变来源安装，
或在没有私有凭据时完成最小闭环。

## 决策

1. 首发候选期现有仓库继续作为私有工程与证据源；公开发布只来自 `public_source_export_v1` 白名单源导出，再从
   独立公开仓库已存在且指向 `HEAD` 的版本 tag 生成 release artifact。两个阶段不得合并证据层。首发后的长期
   工程权威由 ADR 0073 负责，导出器不是持续镜像协议。
2. 导出只复制显式登记的 Core、当前规范、当前测试、必要 Plugin/Skill、治理文件和发布工作流；未选中文件默认留在
   私有源，已声明的 allowlist pattern 若为空则失败关闭。历史证据、私有 `AGENTS.md`、主机路径、任务 ID、凭据形态
   和私有 Owner identity 不进入公开树；实例特定 deny literal 由不随导出发布的调用参数提供。`path/**` 由导出器
   自己解释为全部后代普通文件，不委托给 Python 版本相关的尾部 `**` glob 语义。
3. Python wheel/sdist 是 `Core-only` 分发物。Plugin/Skill 是独立版本化的 portable bundle；二者共享 release
   manifest、兼容矩阵和 SHA-256 清单，但不假装为同一个 Python wheel。
4. 公开 Bootstrap 的 Sidecar 来源必须同时绑定 release ref 与完整 commit SHA。Global Owner 是可选私有后端；
   未配置时 Core project scope、只读 Scout 和 Doctor 可以安装，global mutation/Owner parity 明确 unavailable，
   不搜索替代 Owner、不要求私有凭据。
5. 许可证表达式与完整许可证文件是导出硬门。没有用户选择的许可证时只允许验证“正确阻断”，不得生成可发布物、
   创建 public 仓库、tag、Release 或 registry 包。
6. 公开导出只证明 `public_artifact_verified`。只有从 release artifact 在干净环境安装并通过 CLI/Skill smoke，才能
   提升为 `public_install_verified`；真实新任务采用、跨设备连续性和产品效果仍按原证据阶梯独立证明。

## 为什么不是原地公开

- 原地历史清洗需要重写全部 Git 引用、协调所有 clone 并证明没有遗漏，风险高于生成一个最小公开事实集。
- denylist 无法证明未来新增的私有文件不会漏出；allowlist 让新增文件默认不进入公开树，发布所需新增文件必须显式登记。
- 将私有 Owner 复制进公开仓库会制造第二行为权威并泄漏个人规则；完全删除 Owner 又会破坏已有私有部署。可选
  后端同时保留两者边界。

## 代价

- 首发候选期私有工程仓库与公开分发仓库是两个 Git 面，需要 manifest、内容清单和兼容矩阵证明来源关系；
  ADR 0073 的切换完成后不得继续双轨演进。
- 新增公开文件必须显式进入 allowlist；这是有意的发布背压，不是自动同步缺陷。
- 正式发布仍需一次明确的许可证选择和独立 public/release 授权。

## 验收

- commit-bound source manifest 拒绝 ref/commit 漂移，并允许 `canonical_owner=null`。
- public source export 对空 allowlist pattern、物理 alias、隐私模式、缺许可证和脏源码失败关闭；未选中文件留在私有源。
- 同一递归 allowlist 在 Python 3.11–3.13 选择相同文件集，遇到目录 alias/reparse 不跟随也不静默跳过。
- public release build 对未登记的公开提交文件、origin/ref/HEAD 漂移、版本不一致和不可重建 artifact 失败关闭。
- wheel/sdist clean install、portable bundle 内容、manifest/checksum、三平台 Python 3.11–3.13 和真实 CLI help 均有证据。
- 当前私有工作树、远端可见性、Global Owner、Host Profile、Store 与 Scheduled 状态不因导出而改变。
