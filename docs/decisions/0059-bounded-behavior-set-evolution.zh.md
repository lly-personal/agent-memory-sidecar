# ADR 0059：Managed rules 采用有界行为增量集合

- Status: accepted
- Date: 2026-07-27
- Decision owners: user, project_docs
- Implementation authorization: confirmed after Stage A; Core、Skill、安装与只读试点已获授权

## 背景

Core v1 把必须执行的规则发布到实际 `AGENTS.md`，并用单规则 1 KiB、managed block 8 KiB 防止无界
instruction 增长。真实工程已经出现 16 条规则占用 8,185/8,192 字节的饱和状态；其中多条规则围绕
第一性原理、authority、UI/UX、纵向切片、真实验收和运行安全重复分裂，部分内容也已由项目自身
`AGENTS.md` 与 L1–L3 持有。

现有 Skill 虽然禁止持久化 project-owned facts，但 proposal 前没有强制读取实际 rules、比较当前已读取
authority 或判断语义关系。Repository 只能按完全相同的 `rule_id` no-op，`--supersedes` 只能替换一条，
`rule list` 也不报告容量。因此 8 KiB 最终只表现为诚实的写入失败，不能帮助规则集在持续协作中演化。

## 决策

Agent Memory 的 managed block 定义为 `bounded_behavior_delta_set`：相对于现有全局与项目 authority
仍然必要的已授权行为增量，而不是会话事件或只增不减的规则历史。

1. Agent/Skill 在创建 proposal 前读取实际 global/project rules，并只比较当前 instruction chain 与项目
   router 已要求读取的 owner；不自动扫描整个项目。
2. 候选只允许分类为 `already_covered`、`add`、`replace`、`consolidate` 或 `route_to_owner`。
   前者和后者不创建 token、不写 managed block。
3. 新纠正优先替换或归并现有规则。多规则归并必须展示精确 before/after 并获得一次明确确认，模型不能
   自动删除。
4. Sidecar 执行 `rule_revision_v1`：hash 绑定 seven-field proposal、instruction target、完整 target
   before hash 和排序后的 superseded IDs；文件事务一次写入完整结果。
5. `--supersedes` 扩展为可重复参数。所有 ID 必须唯一、存在且属于同一 target；新规则进入最早被替换
   位置，其余顺序与块外字节保持不变。
6. managed block 预算保持 8 KiB。`rule list` 报告 managed、budget、remaining、完整文档字节和规则数；
   完整文档大小不授权 Sidecar 修改块外正文。
7. 不增加表。现有 proposal hash 列保存新 revision hash；旧 add-only token 保持可确认，但不能在确认时
   附加 superseded IDs。

## 为什么

扩容只能延迟再次饱和，不能阻止同一行为被不同措辞持续追加。有界行为增量集合把容量、单一 authority
和用户授权统一到一个最小模型：模型负责发现关系，用户决定行为变化，确定性服务只执行被确认的精确
规则集修订，实际 `AGENTS.md` 继续是唯一行为 owner。

该方案复用现有 Agent、Skill、Rule Service、Authorization Ledger 和文件事务，不需要第二规则存储、
后台清理器或自然语言路由器。8 KiB 继续作为模型判断失败时的最后背压。

## 备选方案

- 立即提高到 16/32 KiB：掩盖重复捕获并扩大 instruction 上下文，拒绝。
- TTL、LRU 或按使用频率自动清理：低频安全规则可能价值最高，且未经用户授权删除，拒绝。
- 把规则正文迁入 SQLite 后按需召回：恢复第二行为权威与概率性 must-apply，拒绝。
- 自动把全部规则摘要成一条：会丢失 trigger 与 skip boundary，且无法证明语义等价，拒绝。
- Sidecar 自动改写块外项目规范：越过编辑所有权，拒绝。

## 兼容与失败

- 单值 `--supersedes`、公开命令名、`agent_memory_result_v1`、退出码、七字段和七表 Schema 保持兼容。
- 旧 proposal token 只有在 `supersedes` 为空时按旧 proposal hash 确认；任何编辑或归并都必须重新创建
  绑定 revision 的 token。
- superseded IDs、target before hash、scope、容量或 global parity 任一不匹配都在写入前拒绝。
- 文件或数据库提交失败恢复完整原文，不消费授权，不产生部分归并。

## 验收

- authority 已覆盖的候选产生零 token 和零新增字节。
- 单规则修订不增加规则数量；多规则归并顺序稳定且一次原子完成。
- 容量错误返回 before/projected/budget，8,192 字节边界不变。
- LF/CRLF、项目/global 双目标、override、漂移、故障恢复和外围字节保护均有自动化覆盖。
- 真实 Desktop 新任务证明新增、修订、归并和撤销后的行为，而不是用文件缩小或测试代替采用。
- 首个饱和工程只生成只读归并预览；真实改写需要后续单独授权。

## 重新决策

只有在 authority 去重和规则集演化投入使用后，仍有多个工程因真正独立、高价值规则超过 8 KiB，
并且真实 Desktop 证明靠近块尾的规则仍可靠采用时，才重新评估扩容或目录级 scope 拆分。
