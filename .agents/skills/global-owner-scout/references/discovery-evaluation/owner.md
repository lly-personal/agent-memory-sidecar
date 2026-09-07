# 验收语料中的既有全局 Owner

仅用于本练习，不代表真实全局规则，也不授权任何持久化。

## owner:result-layers

When: Fresh evidence contradicts a completion claim.
Do: Revoke the affected result layer, preserve unaffected evidence, and route work to the first invalidated consumer.
Skip: An independently classified observation-only fault that cannot invalidate that result.

## owner:real-entry

When: A change is consumed through an entrypoint whose context can vary.
Do: Resolve the effective context from current authority and prove a faithful vertical slice before promotion.
Skip: A stable public interface that is itself the terminal consumer needs no separate surface run.
