# Component Compatibility

| Release lane | Core | Plugin | Bootstrap | Scout | Review Pack | Python |
|---|---:|---:|---:|---:|---:|---|
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
