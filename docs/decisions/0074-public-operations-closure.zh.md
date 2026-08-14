# ADR 0074：公开运维闭环采用显式来源切换与不可变发行解析

- 状态：Accepted
- 日期：2026-08-14
- 关联：[L1](../specs/axioms.md)、[L2](../specs/topology.md)、[L3](../specs/interface.md)、[Source Authority Cutover v1](../../specs/source-authority-cutover-v1.md)、[Public Distribution v1](../../specs/public-distribution-v1.md)

## 背景

公开 `main` 已成为唯一工程权威，但存量主机仍可能绑定旧私有 Sidecar 缓存；陌生主机又不能把 checkout、浮动
Marketplace 或一段人工复制命令当作发行权限。若直接放宽 `sync-sources`，普通同步会获得静默换源能力；若要求用户
自行寻找 Release 资产，则第一跳仍不自包含，且无法稳定验证 tag、commit 与资产摘要。

## 决策

1. 保留 `sync-sources` 的身份固定与 dirty fail-closed；新增一次性 `source-cutover`，以无写入 dry-run 的
   `plan_hash` 绑定当前/目标来源和 Owner 动作。
2. 存量 Owner 默认采用 `keep_owner`：公开 Sidecar 与独立私有 Owner 可以组合，但不存在第二个工程权威；从现有
   Owner 降级为 `public_core` 必须走另一个显式解绑决策。
3. Apply 只接受 fresh hash，先完整 staging，再原子切换，并复用 Core setup 的 Store/Hook/runtime 原子事务；任一
   失败恢复来源与 Bootstrap/Scout。
4. 冷启动 Anchor 使用公开 Release Resolver 获取 latest stable 或显式版本，验证 immutable Release、tag/commit、
   GitHub asset digest、`SHA256SUMS`、source manifest 与 portable 内嵌 manifest；不得回退 `main`、私有仓库或猜测资产。
5. 仓库 Marketplace 只是可发现入口，不是 source authority。新安装 Plugin/Skill 只从下一任务保证可加载。

## 结果与代价

来源切换比普通同步多一次 dry-run/apply，但用户只确认一个稳定 hash，不需要理解每个文件或手工回滚。公开冷启动
需要可访问 GitHub Release；本阶段不增加后台更新器、离线缓存协议、数据库、守护进程或 `--force`。当前主机通过不
代表第二台真实机器通过，跨主机资格继续保持未证明，直到独立设备完成验收。
