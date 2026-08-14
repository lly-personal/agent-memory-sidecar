# Agent Memory Core v1 用户指南

- Status: active
- Owner layer: project_docs
- Last verified: 2026-08-13
- Evidence: [L3 接口规范](specs/interface.md)、[Core v1 contract](../specs/agent-memory-core-v1.md)、[ADR 0059](decisions/0059-bounded-behavior-set-evolution.zh.md)、[ADR 0070](decisions/0070-atomic-review-pack-rule-bundles.zh.md)

## 一句话

Agent Memory 把相对于现有项目与全局规范仍然必要、由你明确授权的协作规则发布到 Codex 实际加载的
`AGENTS.md`，让它能在后续任务中被采用、查看、演化和撤销。它不是通用知识记忆库或规则历史。

## 日常边界

普通工作保持安静。明确说“记住”且内容、范围无歧义时，该次表达就是授权；Agent 回显最终
`When / Do / Skip` 与范围后直接部署，不再要求第二次确认。

提出新规则前，Agent 会先检查实际规则和当前任务已经按项目 router 读取的 authority：

- 已经覆盖：显式“记住”时说明无需新增；普通任务保持静默。
- 修正旧规则：替换旧规则，而不是继续追加近似规则。
- 多条规则重叠：展示一张精确的归并前后对比，确认后一次替换。
- 项目事实、设计或当前状态：路由到对应项目 owner，不写入 managed block。

若规则内容或与现有规则的关系仍需推断，Agent 只显示澄清草案。草案不是 `待确认`，不会创建 token
或写文件。

Ambient discovery 是实验能力：任务完成后最多显示一张建议卡。只有卡片创建成功才显示；确认前只持久化
最长 24 小时、与七字段、修改前 target 和被替换规则绑定的 token，不保存 prompt、回复、卡片正文或
target 文档。

Global Owner Scout 的 Review Pack 可以一次精确选择一张或多张可确认卡。系统在一个最新 Owner 快照上联合检查
选中卡，使用一次授权把它们作为一个原子规则包提交：全部成功，或一条也不写。单卡只是大小为一的规则包。
如果 Owner 变化导致规则关系或最终正文发生实质变化，系统先显示一次刷新后的合并预览，不直接写入。未选择卡片
以后只需重新比对 Owner，不需要重新执行完整项目复盘，除非项目证据本身已经变化。

## 什么适合成为规则

规则必须能降低未来重复解释或纠正成本，并明确：

- `trigger`：何时适用；
- `action`：以后做什么；
- `skip_boundary`：何时必须跳过；
- `scope` 与 `instruction_target`：本项目或跨项目；
- `why` 与 `evidence`：当前授权为何合理。

一次性任务、猜测、敏感信息，以及本应进入代码、测试、项目文档或 Skill 的事实，不进入 Agent Memory。

## 作用域

- 本项目：写入 primary folder 根目录的 `AGENTS.md`；该 folder 不要求是 Git 仓库。
- 跨项目：同时写入绑定的完整 Git source 和本机 `~/.codex/AGENTS.md`。

从 secondary folder 发起的 project 操作若不属于授权事件的 primary folder，会拒绝。非空
`AGENTS.override.md` 会使对应规则显示为 `已停用`，不会伪装成生效。

## 查看、编辑、撤销

可以自然地要求：

- “查看本项目和跨项目规则。”
- “把 `rule_...` 修改为……”
- “撤销 `rule_...`。”

编辑是用新 `rule_id` 原子替换旧规则；归并会在一次事务中用一条新规则替换所有具名重叠规则。
撤销后规则从实际 target 删除，不建立长期撤销账本，因此以后不再出现在列表中。当前已经加载规则的
任务可能保留旧上下文；必须用新任务验证编辑、归并或撤销后的行为。

规则列表同时显示每个 target 的 managed block 已用、总预算、剩余字节、完整文档字节和规则数。8 KiB
是 Agent Memory managed block 的编辑预算，不是 Codex `AGENTS.md` 文件上限；完整文档较大不会授权
Sidecar 修改块外正文。

## 三种状态

- `待确认`：当前 scope 存在未过期 proposal token。
- `生效中`：实际 target 中存在可解析规则，且未被 override 屏蔽。
- `已停用`：撤销当次结果，或文件中的规则被 override 屏蔽。

SQLite 历史、Git commit、Hook 输出和 Agent 自述都不能单独产生 `生效中`。

## 失败时意味着什么

- `未保存`：授权、scope、时效、proposal、修改前 target 或被替换规则不匹配。
- `未部署`：instruction 漂移、override、权限、格式或容量检查失败；容量失败会报告修改前、预计和预算字节。
- `未证明`：文件已经部署，但还没有真实新任务的采用证据。

Global 操作返回 `publication_required=true` 时，本机部署可以已完成，但跨设备传播要等私有 Git commit、
push 和远端验证完成后才能声明。

Ambient 建议的准确率仍未证明，不影响显式授权 Core 的发布判断，也不能被描述为稳定能力。
