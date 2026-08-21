# SOP：同步并部署本机 Agent Memory

- Status: active
- Owner layer: operations_sop
- Applies when: 新设备冷启动、已有设备升级、迁移来源，或确认本机 Agent Memory 是否完整对齐。
- Avoid when: 只复盘项目、只修改规则、只配置 Scheduled，或执行 Release 发布。
- Contract: [Workstation Reconcile v2](../../specs/workstation-reconcile-v2.md)

## 用户入口

在已安装 Agent Memory Plugin 的 Codex Desktop 任务中只需发送：

```text
同步并部署本机 Agent Memory
```

用户不需要提供 Sidecar 路径、Owner 路径、版本、项目 ID、项目列表、安装顺序或底层命令。

## 标准链路

```text
解析并验证唯一不可变 Release
-> 构造 Core/Plugin/Bootstrap/Scout/source 期望身份
-> 读取实际 Marketplace/Plugin/source/runtime/Skills
-> 展示一个调和计划
-> 仅来源身份改变时取得一次确认
-> exact-hash 原子 apply 与失败补偿
-> 执行后 exact readback
-> 返回 reload_required
-> 用户刷新一次 Desktop 并新建任务
-> 同一句入口触发只读 consumer verification
-> ready
```

## Agent 执行规则

1. Anchor 必须先用 Resolver 验证 stable immutable Release、tag/commit、asset digest、checksums、release/source manifest
   与 portable bundle。失败停止，不回退 branch、checkout 或猜测资产。
2. 从 Resolver output 的 portable 运行 Bootstrap 2.0.0，执行 `workstation-reconcile --dry-run`。不得手工拼接多个安装命令
   后声称完整部署。
3. Fresh install、同一来源的 ref/version/hash 修复由本次部署请求覆盖；Sidecar 或 Marketplace source identity 改变时，
   只显示 renderer 生成的无路径、无 URL 计划，并等待一次确认。
4. Plugin 显式禁用时保持用户选择并显示阻断；不得自动启用。Marketplace/Plugin 状态不可读时失败关闭。
5. apply 必须使用 fresh `plan_hash`。Plugin/Marketplace、受管 source、Core/Owner、Bootstrap/Scout、Doctor 与最终读回属于
   同一补偿边界；任一失败都不能返回完成。
6. apply 成功只返回 `reload_required`。只要求一次 Desktop 刷新，不要求用户重新选择来源或执行命令。
7. 刷新后的新任务再次收到同一句入口时，若 dry-run 为 exact `noop`，执行只读 `--verify-consumer`。只有此时可返回
   `ready`；该检查必须重新读取 live Core/Doctor/Owner/Skills，不得复用历史完成回执。若出现漂移，回到调和计划。
8. 已发布的 Anchor 1.x 会调用旧命令名；当且仅当输入是 Resolver 的完整目录形态时，Bootstrap 2.0 自动把该命令路由
   到 v2 计划与事务。用户不需要先迁移 Anchor、重复部署或刷新两次。

## 用户可见状态矩阵

| 状态 | 已证明 | 未证明 | 用户动作 |
|---|---|---|---|
| `distribution_reconcile_blocked` | 已定位 Plugin/Marketplace 缺失、不可读或禁用 | source、主机物化、采用 | 只处理显示的唯一阻断 |
| `source_sync_blocked` | Release 与 distribution 读回可用 | source/host/采用 | 修复来源访问或 ambiguity 后重试 |
| `host_materialization_blocked` | distribution 与 source 已验证或已恢复 | 完整 Core/Skill/Doctor、采用 | 根据唯一错误重试，不手工补步骤 |
| `reload_required` | 当前主机 distribution/source/Core/Skills/Doctor exact | 当前任务模型采用、第二设备、连续性 | 刷新一次 Desktop，新建任务并发送同一句入口 |
| `ready` | 当前主机 exact，且新任务已加载 Bootstrap 2.0.0 | 第二设备、Scheduled、连续性、产品收益 | 可在目标工程新任务运行 Project Scout |

任何 blocked 状态都不得同时要求刷新 Desktop 或引导运行 Project Scout；先修复矩阵中第一层失效事实。

## 禁止的快捷路径

- 不用 Marketplace 页面显示“已安装”替代 Plugin ref/version/hash/enabled 读回。
- 不用新 Skill 文件、Doctor、测试或 Deployment Pack fixture 替代新任务模型采用。
- 不把当前主机结果外推到真实第二台设备。
- 不修改 Desktop 活跃项目 checkout，不创建/恢复 Scheduled，不写 Host Profile，不移除私有 Owner。
- 不增加 daemon、后台更新器、数据库、UI scraper 或第二行为 Owner。

## 验收清单

- Fresh host、exact no-op、旧 Plugin + 新 Skills、新 Plugin + 旧 source、Marketplace identity drift。
- Plugin cache 缺失、CLI 状态不可读、显式禁用、执行中失败、最终读回不一致。
- 任一失败后的 Marketplace/Plugin/source/Skill target 与执行前一致。
- apply 只到 `reload_required`；刷新后真实新任务才到 `ready`。
- 当前主机与真实第二设备证据始终分开。
