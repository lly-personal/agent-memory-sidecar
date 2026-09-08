# Component Compatibility

| Release lane | Core | Plugin | Bootstrap | Scout | Review Pack | Python |
|---|---:|---:|---:|---:|---:|---|
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
