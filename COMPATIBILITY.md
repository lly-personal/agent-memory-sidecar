# Component Compatibility

| Release lane | Core | Plugin | Bootstrap | Scout | Review Pack | Python |
|---|---:|---:|---:|---:|---:|---|
| v0.5.3 | 0.5.3 | 1.7.3 | 2.3.1 | 5.10.0 | v6 | 3.11–3.13 |
| v0.5.2 | 0.5.2 | 1.7.2 | 2.3.1 | 5.10.0 | v6 | 3.11–3.13 |
| v0.5.1 | 0.5.1 | 1.7.1 | 2.3.1 | 5.10.0 | v6 | 3.11–3.13 |
| v0.5.0 | 0.5.0 | 1.7.0 | 2.3.0 | 5.10.0 | v6 | 3.11–3.13 |
| v0.4.0 | 0.4.0 | 1.6.0 | 2.2.5 | 5.10.0 | v6 | 3.11–3.13 |
| v0.3.16 | 0.3.16 | 1.6.0 | 2.2.4 | 5.9.2 | v6 | 3.11–3.13 |
| v0.3.15 | 0.3.15 | 1.5.4 | 2.2.3 | 5.9.1 | v6 | 3.11–3.13 |
| v0.3.14 | 0.3.14 | 1.5.4 | 2.2.2 | 5.9.0 | v6 | 3.11–3.13 |
| v0.3.13 | 0.3.13 | 1.5.4 | 2.2.2 | 5.9.0 | v6 | 3.11–3.13 |
| v0.3.12 | 0.3.12 | 1.5.3 | 2.2.1 | 5.8.0 | v5 | 3.11–3.13 |
| v0.3.11 | 0.3.11 | 1.5.2 | 2.2.0 | 5.7.0 | v4 | 3.11–3.13 |
| v0.3.10 | 0.3.10 | 1.5.1 | 2.1.0 | 5.7.0 | v4 | 3.11–3.13 |
| v0.3.9 | 0.3.9 | 1.5.1 | 2.0.1 | 5.6.0 | v4 | 3.11–3.13 |
| v0.3.8 | 0.3.8 | 1.5.0 | 2.0.0 | 5.6.0 | v4 | 3.11–3.13 |
| v0.3.7 | 0.3.7 | 1.4.0 | 1.9.0 | 5.6.0 | v4 | 3.11–3.13 |
| v0.3.6 | 0.3.6 | 1.4.0 | 1.9.0 | 5.6.0 | v4 | 3.11–3.13 |
| v0.3.5 | 0.3.5 | 1.3.0 | 1.8.0 | 5.5.0 | v4 | 3.11–3.13 |
| v0.3.3 | 0.3.3 | 1.2.1 | 1.7.1 | 5.5.0 | v4 | 3.11–3.13 |
| v0.3.2 | 0.3.2 | 1.2.1 | 1.7.0 | 5.5.0 | v4 | 3.11–3.13 |
| v0.3.1 | 0.3.1 | 1.2.0 | 1.7.0 | 5.5.0 | v4 | 3.11–3.13 |
| v0.3.0 | 0.3.0 | 1.1.0 | 1.6.0 | 5.5.0 | v4 | 3.11–3.13 |
| Historical rollback | 0.2.0 | n/a | n/a | n/a | n/a | See tag |

The Python wheel/sdist contain Core only. Plugin, Bootstrap, and Scout ship in the portable bundle. A row is publishable only when
the release manifest, package metadata, Plugin manifest, Skill contracts, archive names, and installed-runtime smoke agree.
In v0.3.12, Scout 5.8 replaces Project/Review Pack v4 with v5 discovery provenance and
dispositions; v4 payloads are not accepted as v5 and must be regenerated from evidence. Delivery v1 is unchanged. Bootstrap 2.2.1
materializes the matching Scout version. The existing frozen Skill 4 compatibility lane remains governed by its QDR.
The v0.3.13 and v0.3.14 lanes keep Project v5 and Delivery v1. Review Pack v6 requires the exact installed Core selection preview;
v5 packs must be re-prepared against fresh Owner bytes before offering confirmation. Scout 5.9 needs Core preview support.
Core 0.3.14 fixes UTF-8 input for Chinese previews on Windows when Python UTF-8 mode is disabled.
Core 0.3.15 and Scout 5.9.1 clarify engineering and user-acceptance boundaries without changing rule or delivery contracts;
Bootstrap 2.2.3 installs the matching Scout.
Core 0.3.16 also accepts the exact full selection with uniformly Markdown-escaped `@` separators; rule/bundle wire formats and
scope, freshness, capacity and atomicity checks are unchanged. Plugin 1.6.0 owns the optional Engineering Contract Review methods.
Bootstrap 2.2.4 ends installation delivery before optional user-initiated consumer verification; Scout 5.9.2 documents method handoff.
Core 0.4.0 adds scalar `rule_preview_v1` and emits `rule_bundle_preview_v2` with per-rule and full-block capacity measurements.
Scout 5.10.0 accepts both preview v1 and v2 and distinguishes their reported failure layers; older Scouts cannot consume v2.
Bootstrap 2.2.5 installs the matching components together. Rule revision bundles remain v2, Review Pack remains v6, and existing
approval, scope, atomicity, 1 KiB rule and 8 KiB block budgets remain unchanged. Plugin 1.6.0 content is unchanged.
Missing or older runtime support preserves cards and removes unavailable confirmation actions. A compatibility row alone does not
prove publication, host deployment, independent discovery recall, or user acceptance.
Scout 5.6 keeps Review Pack v4 and adds the separate `global_owner_scout_delivery_v1` task-surface contract.
Scout 5.7 keeps Review Pack v4, adds `global_owner_scout_terminal_v1`, and moves the user front door from a manually created
worktree task to automatic host-managed isolation from the current project task.
Bootstrap 2.2 upgrades Deployment Pack to v3 and gates `ready` on a complete read-only observation of Desktop-visible project-level
same-name Skills; drift and bounded coverage remain explicit and never mutate project checkouts.
`requires-python >=3.11` expresses install eligibility; the table records the versions actually supported and tested. A newer Python
version is not claimed supported until it enters this matrix, even if its installer accepts the package metadata.

`v0.3.4` is an unpublished Git tag. Its release build stopped before artifact creation, so it is not an installable release lane.
`v0.3.6` is a protected unpublished Git tag. Its stale draft was withdrawn after a post-tag release-process repair; the tag was
not moved, and the corrected public lane advances to `v0.3.7`.

Core 0.5.0 adds whole-document global instruction synchronization for Codex and Pi. Bootstrap 2.3.0 preserves its verified Owner
snapshot during workstation reconciliation, and Plugin 1.7.0 exposes the shared release-bound Anchor. Scout remains 5.10.0;
Pi instruction distribution does not install Codex Hooks or prove model adoption.

Core 0.5.1 installs the generated Skill with its own Core command entry and verifies execution without source injection.
Bootstrap 2.3.1 renders UTF-8 receipts and distinguishes entry conditions from actual Scout execution.
Plugin 1.7.1 carries the updated release identity; Engineering Contract Review and Scout behavior are unchanged.

Core 0.5.2 scopes runtime self-test evidence and cleanup to its own probe session. Event retention and unrelated runtime activity
no longer invalidate successful capture. Plugin 1.7.2 carries the release identity; Bootstrap and Scout remain unchanged.

Core 0.5.3 clarifies fresh authority reads, interpreter discovery and no-write failure handling in the generated memory Skill.
Plugin 1.7.3 carries the release identity. No approval, Store, Bootstrap or Scout contract changes are included; Desktop adoption
and complete user journeys remain distinct from these source and packaging guarantees.
