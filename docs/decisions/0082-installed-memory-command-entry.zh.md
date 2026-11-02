# ADR 0082：普通任务使用随 Skill 安装的 Core 入口

- 状态：Accepted
- 日期：2026-11-02
- 范围：Core 安装投影、Doctor、Bootstrap 回执与实际入口回归；不改变授权、Owner 或 Store 契约。

## 需求与反证

用户应在明确协作偏好后完成一次授权，并在普通项目继续查看、修订或撤销规则，无需定位 Python 包或重复安装。
实际故障表现为安装与 Doctor 成功，但 Skill 调用全局命令时找不到 `agent-memory`。隔离复现证明，setup 与
Doctor 依赖的临时 `PYTHONPATH` 掩盖了普通消费者缺失的可执行入口。PR #45 的中文回执又在非 UTF-8 管道下
触发 `UnicodeEncodeError`。两者都必须通过实际进程验证，不能以文件存在或内部函数返回替代。

## 原生能力核验与选择

核验日期为 2026-11-02；本机 Codex CLI 为 0.166.0。官方 [Skill 机制](https://learn.chatgpt.com/docs/customization/overview)
直接支持随 Skill 携带并按需运行 `scripts/`。因此采用这一现有入口，将现有 Core 源码作为安装投影随 Skill
原子安装；源码仍只有 `src/agent_memory_sidecar`，没有手工维护副本、服务或新的运行数据库。

对照过的其他原生入口：

- [Plugin onboarding](https://developers.openai.com/plugins/build/plugins) 可调用包内 setup Skill，能改善初次发现；
  但它不自动提供 Core 命令，也不能证明当前宿主上的后续调用。本次不增加第二个 setup 入口。
- 同一官方文档提供 Plugin hooks、`PLUGIN_ROOT` 与 `PLUGIN_DATA`。这些变量属于 Hook 执行上下文，不能假定
  普通工具命令也具有它们；安装或启用 Plugin 也不等于已信任 Hook。迁移现有事件入口不是本次故障的必要修复。
- [原生 MCP](https://developers.openai.com/plugins/concepts/skills) 可提供结构化工具，但本次工作只需本地 Core；
  引入服务器、连接配置和另一套工具入口不能消除现有授权与发布责任，增加的实体没有当前验收需求。
- wheel 的 console script 继续支持 CLI-only 安装；将它设为 Desktop 的隐式前置条件会重新引入包环境和 PATH 依赖。

## 决定与验收

1. 生成的 Skill 指向自身 `scripts/agent-memory.py`，保留实际项目 cwd、活动 CODEX_HOME 和原有操作参数。
   使用宿主已存在的 Python 3.11+；不修改 PATH，不安装第三方依赖，不要求用户搬运内部路径。
2. Skill 内容身份覆盖入口和 Core 文件，沿现有原子安装及回滚交付。Doctor 在项目目录移除源码环境变量后
   执行这个入口；空输出或失败都不能成为就绪证据。
   日常入口只开放 rule、proposal 和 doctor；安装、迁移和指令分发继续从已验证 Bootstrap 执行，避免将安装
   副本误当发行源码而覆盖来源身份。既有目录替换存在短暂切换窗口，不承诺并发升级期间无中断调用。
3. 普通入口回归在隔离 Owner/Store 中执行查询、未授权拒绝、显式部署、修订、撤销及提案确认，退出码、JSON
   与 Owner 读回共同判定。模拟项目路径含空格，不依赖全局 console script。
4. Bootstrap 输入输出明确使用 UTF-8；回归强制非 UTF-8 默认管道，检查中文回执与直接 renderer 完全一致。
5. 回执分别报告安装、入口条件与 Scout 实际运行。源修复、CI、发行、主机部署、后续自然采用各有独立证据。

这些测试证明运行入口与确定性操作，不证明模型在所有自然场景都会选对 Skill，也不证明长期采用、第二台设备
或 Scout 全流程。出现新的宿主原生能力或实际消费反证时，重新比较必要实现，不以本 ADR 固定实现手段。
