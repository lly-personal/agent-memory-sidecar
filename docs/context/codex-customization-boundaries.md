# Codex Customization Boundaries

- Status: active
- Owner layer: project_docs
- Applies when: 判断长期行为应属于 AGENTS.md、Skill、Hook、Memories、Git、Store 还是测试。
- Avoid when: 只需读取局部源码且不涉及 owner 选择。
- Last verified: 2026-07-24
- Evidence: [L1](../specs/axioms.md)、[L2](../specs/topology.md)、[L3](../specs/interface.md)

## 当前边界

- `AGENTS.md`：必须执行的长期行为唯一权威；项目/global 层级和 override 决定实际加载结果。
- Skill：管理“记住、修改、忽略、查看、撤销”的对话流程，不拥有运行时行为。
- Hooks：只传输有界 event envelope、opaque approval ref 和固定 capability；不做 prompt 语义、授权或规则查询。
- Memories：可关闭的辅助背景；召回失败不能改变强制规则。
- Rule Service/Store：确定性校验、一次性授权与安装元数据；不是行为 owner。
- 公开发行物：只分发 Core 与版本化 Plugin/Skill；不包含行为 Owner、主机状态或私有证据。
- 私有 Git：用户自有完整 global instruction 文档的可选分发 owner；不决定本机是否生效，也不随公开物发布。
- Tests/Doctor/Desktop 验收：分别证明机制、配置与行为，不创造行为事实。
- MCP/tools：提供能力，不承载仓库长期策略。

## 选择规则

必须影响后续任务的协作规则写入实际 `AGENTS.md`。重复流程写入 Skill 或操作文档；平台事实写入 context；
设计理由写入 ADR；回归风险写入测试。不要为一个意图建立两个行为 owner，也不要用 Hook、Memories、SQLite
或 Git parity 代替 instruction adoption。
