# ADR 0083：多宿主三阶能力阶梯与 L3 宿主确认门槛

- 状态：Accepted
- 日期：2026-11-16
- 范围：Codex、Pi、Claude Code、Antigravity 的跨宿主能力分层与准入门槛；不新增 Pi/Claude/Antigravity 规则写入代码或 Hook。

## 背景

Agent Memory Core 的完整行为闭环依赖“可核验的宿主原生授权边界”。当前三类宿主的原生能力不对称：

- **Codex Desktop**：具备原生 `UserPromptSubmit` / `compact` Hook 绑定、Core SQLite `approval_consumptions` 与本机 `AGENTS.md` 事务写入能力，已承载完整三阶能力。
- **Pi**、**Claude Code** 与 **Antigravity**：当前已具备只读或确定性指令投影所需上下文入口，但尚无统一、不可伪造的宿主原生规则确认原语。

同时，Scheduled Scout 实验保持独立暂停（`PAUSED / 0 of 14`），不作为交互式项目理解或日常规则验收的前置条件。

## 三阶能力阶梯（Multi-Host Capability Ladder）

| 阶梯 | 能力名称 | 目标作用域与行为 | Codex | Pi | Claude Code | Antigravity |
| --- | --- | --- | --- | --- | --- | --- |
| **L1** | 全局规范按需同步 | 通过 `instructions sync` 把 canonical Git 已发布内容完整物化到宿主全局指令并逐宿主回读 | 已支持（`~/.codex/AGENTS.md`） | 已支持（`AGENTS.md` + Registry） | 已支持（显式接入用户级 `CLAUDE.md` + Registry） | 已支持（显式接入观测 `GEMINI_HOME` 下双文件 `config/rules/*.md`、`<=24,000 B` 硬门禁 + Registry） |
| **L2** | 只读 Scout / 工程审阅 | 通过 `inspect-native` 与作用域受限 SDK 冻结只读项目图谱与工程建议（Project v8 / Pack v9） | 已支持（主路径 Project v7 / Pack v8） | 候选（工程建议、只读 `observed_only`） | 候选（工程建议、只读 `observed_only`） | 候选（工程建议、只读 `observed_only`） |
| **L3** | 规则审批与受控写入 | Core proposal / bundle token、`approval_consumptions` 消费及 `AGENTS.md` managed block 原子事务修订 | 已支持（完整 Core CLI + Hooks） | **阻断（ADR Gate）** | **阻断（ADR Gate）** | **阻断（ADR Gate）** |

## L3 强制 ADR 门槛（Pi / Claude Code / Antigravity）

在通过新的正式 ADR 批准之前，严禁为 Pi、Claude Code 或 Antigravity 实现任何规则写入路径、proposal/confirm 状态机或宿主 Hook：

1. **不可伪造原生确认原语（Unforgeable Host-Native Confirmation Primitive）**：未来提案或规则集修订必须绑定来自宿主运行时边界、工具调用或用户界面无法由自由对话文本伪造的原生确认原语及当前 event/session identity。
2. **禁止关键词/自然语言匹配替代授权**：明确禁止用正则表达式、模型自述“用户已同意”或宽松自然语言关键词命中充当写入批准。
3. **证据与能力分层报告**：L1/L2 的配置一致性或包发现结论不得跨级声称为 L3 规则写入或自然任务采用证明。
