# ADR 0070：Review Pack 精确多选与原子规则包

- 状态：Accepted
- 日期：2026-08-13
- Decision owners：user、project_docs
- 取代：ADR 0060、0063、0064、0067、0068、0069 中“用户逐卡逐轮确认并复用单规则修订链”的部分
- 保留：Project Card 不可改写、只读 Scout、人工最终授权、Fresh Owner、单一行为 Owner、七表 Store 与证据分层

## 背景

一次真实交互复盘产生四张可确认卡。用户在一条消息中明确确认四张卡，但宿主只产生一个一次性 approval ref；
Agent 先部署第一张，再循环复用同一 ref。Core 正确拒绝第二次消费，循环停止，最终形成“一张已部署、一张被拒、
两张未尝试”的部分状态。该结果证明单次授权账本按设计工作，也证明“每消息一张卡”没有形成低摩擦、统一的
用户闭环。

历史逐卡方案的目的，是复用现有单规则接口、避免批量授权面、候选数据库和第二治理状态。然而 Core 的真正
不变量是精确授权、Fresh target、一次消费和文件事务原子性；它并不要求一次操作只能包含一条规则。L1 将产品
定义为一次明确授权后的 scoped ruleset revision，`FileTransactionCoordinator` 也已经能够对 project 单目标或
global 双目标执行全成或全不成的完整文件事务。

## 决策

Review Pack 允许用户在一条消息中精确选择一张或多张可确认卡。选中集合构成一个
`rule_revision_bundle_v1` 操作；单卡是大小为一的规则包，不再维护另一套用户心智。

```text
validated Review Pack
-> user selects exact confirm-eligible card IDs
-> one Fresh target/parity read
-> joint relation and inter-card conflict recomputation
-> aggregate target before/after
-> one approval consumption
-> one atomic instruction transaction
-> all selected rules deployed, or zero Owner changes
```

规则包只接受同一 Review Pack、scope 和 instruction target 的卡。每项包含完整 seven-field proposal 与它替换或
归并的 rule IDs；所有 proposal 必须唯一，superseded sets 不得重叠且必须存在于同一个 Fresh before snapshot。
bundle revision hash 绑定 bundle 内容、instruction target、完整 before hash 和完整 after hash。

确认处理器必须使用 target-scoped `rule list`，并在同一 Fresh snapshot 上联合重算选中卡及其相互关系。若任何
关系、规则正文、superseded set 或 Owner 去向发生实质变化，不执行 mutation；只显示一个更新后的聚合
before/after，再请求一次确认。不得循环调用单规则 deploy、派生子授权或保留部分成功。

成功后，未选择 Project Card 的项目证据和 `project_claim_hash` 保持不变；只有 integration preview 过期。用户
以后选择它们时只重新读取 Owner 并 rebase，不重新执行项目 Session 发现，除非项目证据本身出现新反例或变化。

## 接口与状态

- 新增公开确定性操作：`rule deploy-bundle --from-json ... --approval-ref ...`。
- `rule list` 新增可选 `--target global_agents|project_agents`，防止无关 target 故障阻断 Fresh 预检。
- `rule_revision_bundle_v1` 只进入当前请求 hash 和授权消费，不新增 Store 表、proposal 正文、候选 Inbox 或长期状态。
- Bundle 成功回执逐项返回 `deployed/replaced/consolidated`；任何失败返回整包未部署。
- Global bundle 仍只证明本机双目标 `instruction_deployed`；Git publication、后续采用和产品效果分别证明。

## 用户界面

Renderer 保留每张卡的独立 `确认/修改/留在项目/改做 Skill/忽略`，并在至少两张卡可确认时展示一个包含精确
card IDs 的“一次确认多张”命令。用户可以删除不想选择的 ID。确认不得与 edit、routing 或 ignore 混在同一消息。

该设计遵循“所见即所签”：用户看到并选择完整卡片集合；操作唯一性绑定整个规则包，而不是强迫每个条目单独
往返。批次写入遵循通用原子变更原则：任一项不能应用时不留下部分结果。

## 非目标

- 不自动确认全部推荐项。
- 不跨 scope 或 instruction target 建立分布式事务。
- 不增加候选数据库、长期 Review Pack 状态、后台治理、自然语言 router 或第二 Owner。
- 不把 Project Card 合并成一条规则；语义去重仍由 Agent 在写前判断。

## 验收

1. 一张卡通过 bundle 路径保持兼容。
2. 多张 add/replace/consolidate 在一个 before snapshot 上生成一个 after，并只消费一次 approval。
3. 重复 proposal、重叠 supersedes、stale target、容量失败、global parity、第二文件写入失败和数据库提交失败均为
   整包零变化且不消费授权。
4. Renderer/visible verifier 守恒每张卡动作及唯一批次动作；漂移时不显示批次确认。
5. 真实同任务多卡确认只产生一个 Core mutation 和一个准确回执，不再出现 rejected 与 not_attempted 混报。

## 外部原则校验

- OWASP Transaction Authorization：用户应识别并确认重要操作内容，授权凭证对操作唯一；规则包是一个完整操作。
- RFC 5789：一组修改应原子应用，任一修改失败则整组不应用。
- GOV.UK Check answers 与 W3C Error Prevention：提交前集中检查、修改和确认，避免要求用户重做整个流程。

## 回滚

恢复 Scout 5.3.0、Bootstrap 1.3.0、单规则 CLI 与本 ADR 之前的 L1/L2/L3。没有 Store migration；已经原子部署的
规则仍由实际 `AGENTS.md` 拥有，按普通 revoke/edit 流程处理。
