# ADR 0057：将 Agent Memory 收敛为授权规则发布器

- Status: accepted
- Date: 2026-07-24
- Decision owners: user, project_docs

## 背景

现有实现已经把行为 owner 迁到 `AGENTS.md`，但 SQLite 仍保留通用 memory、runbook、revision、delivery 与
历史状态；公开状态仍把 legacy 行折算为用户状态。大型 `MemoryStore`、离线 release harness 和 editable Hook
运行时扩大了故障面，却不能增加后续任务采用规则的确定性。Ambient discovery 尚未取得真实稳定性证据，也不应
阻塞显式授权核心。

## 决策

1. 产品定义为“用户授权的协作规则发布器”，不是通用记忆库。
2. 稳定 Core 只包含显式授权、scope、deploy/list/edit/revoke；Ambient 保持 experimental。
3. Store 重建为七张职责单一的 Core 表，删除 legacy 行为与历史模型。
4. 公开 CLI 原子切换为 `rule list/deploy/revoke`、`setup`、`doctor`，不保留旧别名。
5. 七字段 proposal 的完整 hash 绑定授权；长期 target 只保存 `When / Do / Skip`。
6. Global mutation 同时更新 canonical source 与本机 actual target；Git 发布单独陈述。
7. Hook 从版本化、内容寻址的 immutable zipapp 加载，不再依赖 editable checkout。
8. legacy Store 通过单独授权的 dry-run/apply cutover 重建；迁移前完整 backup 永久保留。
9. 无生产调用者的 release/rollout/candidate harness 从生产包删除，证据由小型测试和真实 Desktop 场景提供。

## 备选方案

- 保留通用 Store：兼容成本低，但继续制造第二状态权威和不必要复杂度。
- 原地 `DROP TABLE`：实现短，但失败和旧版本回滚风险高。
- Hook 继续 editable：开发方便，但源码编辑会即时改变线上运行时。
- Global 只改 Git 源或只改本机：都会留下“分发完成”和“本机生效”之间的所有权缺口。

## 迁移与回滚

在隔离 worktree 完成实现和测试。cutover dry-run 后必须暂停等待新的明确授权。Apply 创建带 checksum 的完整
旧库 backup，在临时库完成迁移和 artifact 自检后才原子切换 Store 与 Hook。切换失败恢复旧库和旧 Hook；
旧 backup 与旧 artifact 不自动删除。真实 Desktop 验收通过前不把完成态推送到 `main`。

## 后果

- 状态只能由 proposal token 与实际 instruction target 计算。
- 撤销历史不再可查询；恢复旧历史只能人工读取迁移前 backup。
- public CLI、Skill 和活动契约必须同步迁移。
- 运行时和 Store schema 可以作为一个可验证部署单元回滚。
- Ambient 失败不再阻止稳定 Core，但也不得被描述为已完成。
