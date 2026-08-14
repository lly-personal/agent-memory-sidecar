# ADR 0066：Scout 执行终态与可见输出完整性

- 状态：Accepted
- 日期：2026-08-10
- 取代：ADR 0065 中未定义长运行工具恢复和最终正文完整性证明的执行语义
- 保留：主机动态注册、项目判断权、中文双投影 Review Pack、只读 Scout、人工授权与零自动 Owner 写入

## 背景

首轮 v5 Scheduled 运行证明，契约合法的 Project Card 并不等于用户已经得到完整可判断的结果。三个项目都在
原生任务索引调用返回运行中 cell 后停止恢复，并把“结果尚未取回”误报为 Session 不可用；其中两个项目还先
请求了超过已验证宿主上限的数量。另一次运行虽然内部卡片通过校验，但 renderer 的动态导入失败，最终回复由模型
手工压缩，造成卡片内容和动作不守恒。

这些失败发生在执行和呈现边界，不应通过恢复中央传输链、增加数据库或继续扩充 Scheduled Prompt 解决。可复用
执行方法仍由 Skill 拥有，Scheduled Task 只选择时间、项目绑定、证据窗口和资源配置。

## 决策

Skill 5.1.0 保持 `global_owner_scout_project_v4` 与 `global_owner_scout_review_pack_v3`，增加两个硬门禁：

```text
原生任务调用取得明确终态
-> 所有选中自然任务读取到窗口边界或 EOF
-> Project / Review Pack 通过结构校验
-> 确定性 renderer 成功
-> 最终回复逐字保持 renderer 输出
-> 可见输出 verifier 证明正文 hash、卡片、动作和 wrapper 守恒
-> 才能记为有效运行
```

### 原生任务执行协议

1. 首次且唯一的任务索引请求上限固定为 `50`；不得用更大请求探测能力，也不得在首个调用未终态时发起第二次
   索引调用。
2. 长运行调用使用最长 60 秒的初始 yield。若返回 `cell_id`，必须对同一 cell 最多连续执行两次、每次 60 秒的
   wait，直到取得明确终态。
3. `Script running` 只表示结果尚未取回，不得解释为 unavailable、timeout 或 degraded。未恢复 cell、非法参数或
   执行序列中断统一失败为 `execution_protocol_failed`。
4. 只有原生工具返回明确终态错误，才允许 `degraded / native_index_terminal_failure`；明确宿主上限形成
   `bounded / native_index_host_cap`。
5. 相关自然任务使用原生分页读取到证据窗口边界或 EOF；宿主已验证分页上限为 `turnLimit=10`、单项输出上限为
   `maxOutputCharsPerItem=20000`，不得请求更大值。记录发现、选择、完整读取、页数、排除理由和并发快照。

### 确定性可见输出

Review Pack 必须从 Skill `scripts` 目录直接执行 `render_review.py`，通过 stdin 传入已验证对象。不得用动态 import
改变模块搜索路径，也不得在 renderer 失败后由模型手工翻译、压缩、补写或重组 Markdown。

renderer 输出完整中文正文、包含正文 SHA-256/卡片数/逐卡动作计数向量与动作总数的回执，以及唯一且位于末尾的 Scheduled Inbox
wrapper。`verify_visible_output.py` 重新验证最终回复；任一正文变更、卡片或动作丢失、多个 wrapper、原始 JSON、
手工尾注或截断均使整次运行失败为 `render_integrity_failed`。确认平台容量不足时使用
`output_budget_exceeded`，不得显示部分卡片。

verifier 是最后一个工具调用。通过后不得再调用其他 Skill、工具或独立 Agent Memory 审计；Review Pack 与回执
已经构成人工记忆审阅终态，任何更高层审计保持静默，唯一 Inbox wrapper 必须是最终可见字节。

所有 Python helper 使用 `python -B`。Bootstrap 原子安装排除 `__pycache__`、`.pyc` 与 `.pyo`；Scout 前后复核个人
Skill 缓存指纹。运行中新建或修改字节码缓存属于外部写入并失败关闭，不允许由 Scout 自行删除来掩盖。

## 证据与有效运行

2026-08-10 之前的三次 v5 Scheduled 结果均为历史无效运行，三个 Host Enrollment 保持 `0/14`。单个项目只有在
普通 worktree 盲测中同时证明任务索引终态、选中任务完整分页、renderer 成功、可见输出 verifier 通过和只读
工作区不变后，才恢复该项目的 Scheduled Task。修复后的首次有效 Scheduled 运行计为 `1/14`。

首轮普通前向测试进一步证明：非法 `turnLimit=20` 会被正确失败关闭；实际 final 必须由外部验收读取后再次验证，
因为内部 verifier 通过后仍可能被后置 memory 审计追加尾注。PDG 的实际 final 守恒；Sidecar 需修复分页参数，飞书
需移除 wrapper 后尾注，二者分别重跑且不影响已通过项目。Sidecar 重跑还发现 helper 默认生成字节码缓存会破坏
外部零写入，因而进一步固定 `python -B` 与无缓存安装。

非法索引上限、未恢复 cell 或 renderer 不一致首次出现即暂停对应项目。只有明确宿主索引终态不可用，才沿用连续
三次降级后暂停的能力观察规则。一个项目失败不阻塞其他已通过项目。

## Owner 与边界

- 项目线程继续拥有项目事实、证据等级、因果、双投影和 Owner 建议。
- Central 仍只可按需追加跨项目注释，不是传输、可见性或确认门禁。
- 单项目证据显示实际独立项目支持数和覆盖边界，不使用固定项目总数作分母。
- 不新增服务、数据库、候选 Inbox、transcript parser、跨主机同步、自动 Owner 写入或第二行为 Owner。

## 验收

1. validator 拒绝首次索引上限不是 50、非终态调用伪装为 degraded、没有明确终态失败的 degraded，以及不符合
   `complete/bounded/degraded` 的终态枚举组合。
2. renderer 与可见输出 verifier 覆盖 0、1、3、24 卡、降级、失败、无候选、Owner 漂移、容量失败和篡改。
3. 最终正文 SHA-256、Project Card 数、Review Card 数、可见卡数和逐卡动作数守恒，只有一个末尾 wrapper。
4. 三个普通 worktree 盲测逐项目通过后才恢复对应自动化；活跃工作区和既有隔离 worktree 保持原状。
5. 三个项目仍从 `0/14` 开始；无效、降级、截断或不可见结果不计数。

## 平台依据

- [Scheduled tasks](https://learn.chatgpt.com/docs/automations)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)

## 回滚

暂停受影响项目的 Scheduled Task，恢复 Skill 5.0.0、automation Prompt 与本 ADR 对应的 L1/L2/L3/canonical
model 变更。Host Profile、历史结果和未确认卡片不迁移；无数据库回滚。
