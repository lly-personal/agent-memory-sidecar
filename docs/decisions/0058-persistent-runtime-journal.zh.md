# ADR 0058：短生命周期 Runtime 使用 PERSIST rollback journal

- Status: accepted
- Date: 2026-07-24
- Owner layer: project_docs
- Extends: [Core v1 ADR](0057-agent-memory-core-v1.zh.md)、[L2 Runtime 拓扑](../specs/topology.md)、[Core v1 契约](../../specs/agent-memory-core-v1.md)

## 背景

Core v1 已将 Desktop Hook 切换到不可变 zipapp，但最终性能门禁仍出现 Windows 尾延迟：
Hook subprocess p95 曾达到 1440.53 ms、690.33 ms 和 195.09 ms，且相同 Core 事务也出现过
15.54 ms 的 p95。对同一事务负载进行 journal mode 对照后，`DELETE` 的中位数约 4.47 ms、
p95 约 5.27 ms，但最大值达到约 2173 ms；`PERSIST` 的中位数约 5.67 ms、p95 约 6.06 ms，
最大值约 9.88 ms。

SQLite 的 `DELETE` 模式在事务结束时删除 rollback journal；`PERSIST` 通过清零 journal header
使其失效，适合删除或截断文件代价较高的环境。Core v1 Hook 是每次提示启动一次的短生命周期进程，
因此需要减少事务结束阶段的文件系统尾延迟，同时保持 rollback journal 的原子性与崩溃恢复语义。

## 决策

1. `CoreDatabase(runtime=True)` 在首次业务读写前设置并验证
   `journal_mode=PERSIST` 与 `synchronous=NORMAL`。
2. Runtime policy 使用命名常量表达；阈值和 journal policy 不散落到调用者。
3. 无法进入 `PERSIST` 时返回 `runtime_journal_mode_unavailable`；无法保持 `NORMAL` 时返回
   `runtime_synchronous_unavailable`。不得静默回退。
4. Hook 保持 fail-open；immutable artifact 自检通过真实 runtime capture 验证 policy，失败时
   `setup` 不激活新 artifact。
5. 非 runtime 连接不主动设置 journal mode，Core Schema、公开 CLI 和 JSON contract 均不改变。
6. zipapp 构建器先把 Runtime Python 源码换行规范化为 LF，再写入归档并计算 SHA-256。

## 备选方案

- 放宽 10 ms / 150 ms 门槛或过滤慢样本：会把未通过的真实证据包装为成功，拒绝。
- 使用 WAL：短生命周期进程会引入 checkpoint 以及 `-wal`、`-shm` 文件生命周期，增加额外状态面。
- 常驻 daemon 或 IPC：可能降低启动成本，但会新增生命周期控制面、安装与恢复故障面。
- native launcher 或第三方打包器：增加工具链和依赖，只在当前假设被证伪后重新评估。

## 验收

- LF 与 CRLF checkout 生成相同 artifact 字节和 SHA-256。
- runtime 连接实际返回 `persist` 与 `normal`，重开连接后重新应用并验证。
- commit、rollback、FK 和 integrity 行为保持正确；Core Store 仍严格只有七张表。
- 原始性能测试不修改阈值、样本或统计逻辑，连续五次通过后再运行完整测试套件。
- 安装后 Hook、Doctor、规则解析和 global 完整文档一致性通过，之后才能推送完成态。

## 回滚与重新决策

旧 immutable artifact 保留。回滚稳定化提交并重新执行 `setup --apply` 即可恢复上一 Runtime；
本决策不迁移 Schema 或业务数据。

如果安装 LF 规范化 artifact 并启用 `PERSIST` 后，原始性能测试在两次完整干净运行中仍失败，则本决策
不足以解释或解决尾延迟：停止推送，不降低门槛，另行比较 native launcher 与长生命周期 Runtime。
