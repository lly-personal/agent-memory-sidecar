# ADR 0071：所见即所签规则包与物理目标 containment

- 状态：Accepted
- 日期：2026-08-13
- Owner layer：user / project_docs
- 扩展：[ADR 0070](0070-atomic-review-pack-rule-bundles.zh.md)

## 背景

ADR 0070 已把同一 Review Pack 中的一张或多张卡收敛为一次原子规则包，但 `rule_revision_bundle_v1`
仍有三个断裂：规则包按输入顺序逐项应用，等价选择可能得到不同结果；一次性 approval 只证明回复新鲜，
没有证明用户回复中确实选择了被执行的卡；instruction 与 Store 路径在解析后访问，无法排除链接、重解析点或
多硬链接把写入导向授权边界之外。

这些问题不能靠恢复“每次只确认一张卡”规避。用户面对的是同一次复盘得出的一个候选集合；只要所有选中项
共享同一 Fresh owner、scope 和 target，就应允许一次精确选择并完成一次事务。安全边界应绑定所见操作，
而不是把系统缺少的绑定成本转嫁为重复复盘和重复确认。

## 决策

1. Review Pack 的写入契约升级为 `rule_revision_bundle_v2`。每项除 seven-field proposal 与 `supersedes`
   外，固定携带 `card_id`、`project_claim_hash` 和 `selection_token`；bundle 固定携带完整
   `target_before_sha256`。
2. `selection_token` 由卡片 ID、项目 claim、proposal hash、排序后的 superseded IDs、instruction target 和
   target before hash 确定性派生，用户可见形式取 SHA-256 的前 128 bit。它不是秘密，不进入 Store。
3. 确认回复的唯一 canonical 形式为 `确认 <card_id>@<selection_token>[、...]`，多个选择按 `card_id`
   排序。用户可以删除整个 `card_id@token` 对来减少选择。Core 必须校验当前 prompt hash 与该 canonical
   文本完全一致；不一致返回 `approval_content_mismatch`，不写文件且不消费 approval。
4. 规则包是无序集合，不是命令序列。Core 先在同一 Fresh before 上验证全部项，再统一移除所有被替换规则，
   最后按原始位置和稳定 rule ID 插入替换/归并/新增结果。相同集合的任何排列必须得到相同 after bytes、
   revision hash、receipt 或错误。
5. 写入边界同时包含逻辑 owner 与物理对象。读写前和原子替换前都必须以 `lstat` 类语义拒绝 owner 控制面内的
   符号链接、Windows junction/reparse point、非普通文件和多硬链接；不得先 `resolve()` 再丢失链接事实。
   操作系统拥有的顶层目录映射不属于用户可控制的 owner 漂移，不得让 macOS 等标准宿主布局系统性误拒绝。
6. Core Store 目录和文件必须在创建与打开后收敛到私密权限。POSIX 只允许当前用户；Windows 允许当前用户、
   SYSTEM 与 Administrators 的等价 SID/SDDL 表示，但任何其他 allow ACE 都失败关闭。验证按授权语义，
   不要求固定 ACE 数量或固定字符串形式。

## 信任边界

- Agent 仍负责从项目事实形成 proposal、判断 owner 与关系；Core 不做语义理解。
- Review Pack token 只证明用户看到并选择了确定操作，不证明 proposal 语义正确，也不是 HMAC、签名或长期凭证。
- Hook 仍只传输当前 opaque approval ref 与固定 capability；不解析 prompt、不保存卡片正文。
- 显式自由文本“记住”仍由 Agent 回显完整 `When / Do / Skip` 后直接部署；本 ADR 不把它改造成 Review Pack。

## 验收标准

1. 链式替换、归并和新增的所有输入排列结果一致；不适用集合也返回一致错误且零修改。
2. 修改卡片、token、proposal、superseded 集合、target before 或 prompt 任一字段都失败，approval 保持可用。
3. 多卡 canonical 回复只消费一个 approval、只进行一次文件事务，并返回逐卡 receipt。
4. instruction 或 Store 位于 symlink/junction/reparse/multi-hardlink 时拒绝；正常目标保持既有原子回滚能力。
5. POSIX Store 为目录 `0700`、文件 `0600`；Windows DACL 受保护，且不向当前用户、SYSTEM 与 Administrators
   之外的主体授予访问。

## 非目标与回滚

不新增表、服务、签名基础设施、长期卡片正文、自动批准、逐卡生命周期或重复复盘。`v1` 不作为活动兼容别名；
回滚使用 Git 历史或已发布的不可变版本，不在工作树保留双轨实现。
