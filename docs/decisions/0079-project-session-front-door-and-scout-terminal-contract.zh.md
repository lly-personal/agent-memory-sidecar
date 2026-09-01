# ADR 0079：项目任务前门、自动隔离投影与确定性 Scout 终态

- 状态：Accepted
- 日期：2026-09-01
- Owner layer：user / project_docs
- 扩展：[ADR 0068](0068-interactive-project-scout-primary.zh.md)、[ADR 0076](0076-task-scoped-review-pack-delivery.zh.md)；自动隔离
  executor 的资源策略以本 ADR 为准，不再承诺继承父任务上的临时 model/thinking override。
- 平台依据：[Codex Git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)

## 背景

真实项目任务验收暴露了三个相互放大的断点：正式入口要求用户先自行新建 worktree；Skill 在执行十余分钟后才检查
当前环境；没有 host output root 时，失败回执又要求先拥有一个成功的 Delivery manifest。另一个原生任务分页终态
错误虽然只截断部分 Session 覆盖，当前枚举却只能把它压成整个 `execution_protocol_failed`，从而删除已经由项目
Owner、ADR、Git、测试或验收独立支持的卡片。

这不是安装漂移：现场安装的 Skill 与 helper 字节和公共源一致。它证明设计把隔离实现、用户入口、覆盖分类和交付
终态分给了用户、模型自由文本与多个 helper，缺少一个可执行的前门状态机。

官方 Codex 文档把 Local 定义为前台、worktree 定义为互不干扰的独立 checkout，并说明 Codex 可以从当前分支连同
未提交变化创建 managed worktree。由此，worktree 是执行隔离原语，不应成为用户必须提前理解和完成的业务前置。

## 决策

### 一个用户入口，两个内部角色

正式调用仍然只有 `$global-owner-scout 复盘当前项目`，但允许用户直接在当前绑定的目标 Git 项目任务中发送。
入口先执行前置 preflight，且必须发生在任务索引、线程分页、Owner 比较和项目深挖之前：

1. Fresh 解析当前 Desktop 项目绑定、Git 资格、当前 Local/worktree 上下文与只读基线；
2. 通过 `python -B scripts/scout.py inspect-context` 生成无路径 `global_owner_scout_preflight_v1` Git/只读快照；
3. 已在独立 worktree 时原地继续；
4. 该正式调用授权恰好一个只读 executor；位于 Local 时使用宿主原生项目任务创建能力，把当前 working-tree state 与
   同一正式调用作为初始 prompt 自动投影到隔离任务并继续，用户不重复输入；
5. 宿主没有该能力、项目非 Git 或绑定不可验证时，在 preflight 直接返回确定性阻断终态。

投影成功后，前门任务只返回宿主原生 created-task surface，使用户可直接进入唯一 executor。它是 `routed` 证据，
不是复盘完成、Review Pack 已形成或用户表面已验收的证据；完整结果只在 executor 任务产生。

原项目任务是 `project_session_front_door`，负责意图、项目绑定和自动路由；隔离任务是
`isolated_review_executor`，负责完整只读复盘与 Review Pack。不得创建需要二次续传的空子任务、用 shell 手工创建 worktree、猜测路径或要求用户
复制 prompt。Local 中不得先运行部分 Scout 再晚检查 worktree。

### 覆盖错误按消费者精确降级

`native_thread_pages_terminal_failure` 表示任务索引已取得终态，但至少一个已选择自然任务的分页返回明确终态错误。
它要求 `status=degraded`、`truncated=true`、`fully_read_task_count < selected_task_count`，并保留由其他正式证据独立
支持的卡片。未恢复运行中 cell、非法参数或执行序列中断仍是 `execution_protocol_failed`；该状态可以保留此前已经
证明的 index 终态，但不得声称线程分页完成，也不得生成卡片。

### pre-manifest 失败也有确定性终态

新增 `global_owner_scout_terminal_v1`。它精确包含：

```text
contract_version, status, phase, reason_code, project_state, confirmation_eligible
```

它只表示本次没有形成完整可确认 Review Pack，`confirmation_eligible` 固定为 `false`。任何发生在 Delivery manifest
形成之前的 preflight、Session 协议、隐私/契约、只读、output root、renderer 或预算阻断都必须把该对象交给活动 runtime dispatcher 的
`render-terminal`，不得手写 Markdown，也不得错误调用需要 Delivery manifest 的 `render-receipt`。
manifest 形成后的 queued/opened/host-open failure 继续使用 manifest-bound receipt，不能倒流到 Terminal v1。

### 一个活动 helper 前门

Skill 的所有活动 Python 操作只通过 `python -B scripts/scout.py <operation>`。dispatcher 复用现有 validator、Owner
resolver、renderer、visible verifier 与 delivery 实现；冻结的 v4 文件仅作为明确的历史兼容路径保留。模型不再从
多个相邻脚本名推断下一步入口。

## 验收

1. Local clean、Local dirty、已在 worktree 三种入口都在任何任务索引前完成 preflight；前两种自动投影，后一种原地执行。
2. 用户只发送一次正式调用；内部隔离任务不得要求重述项目、路径、版本、候选或协议。
   前门的 created-task surface 只报告路由，不升级复盘结果层。
3. 明确 thread-page 终态失败生成 degraded Review Pack，并守恒其他正式证据支持的卡片；未终态/非法调用仍失败且无卡。
4. 缺少 output root 或早期失败不依赖 Delivery manifest，能生成可验证、无路径、不可确认的 Terminal v1 receipt。
5. Skill 活动文档只调用 `scout.py`；旧 helper 仅由 dispatcher 或兼容实现引用。
6. Source/测试通过不证明安装或模型采用。commit-bound Bootstrap 安装后，必须用新的真实 Desktop 项目任务分别验证
   Local clean、Local dirty、already-worktree、thread-page failure 和 missing-output-root 五条垂直切片。

## 非目标与回滚

本决策不允许项目内报告文件、系统临时目录 fallback、长期 Review Pack 状态、跨任务文件桥、自动确认、Owner 写入或
Scheduled 激活。若宿主缺少自动 worktree fork，入口诚实阻断，不把用户手工建 worktree重新定义为产品成功路径。
回滚必须同时恢复 L1/L2/L3、Skill、dispatcher、Terminal v1 和覆盖枚举；只删除某一层会重新制造心智断裂。
