# QDR 0001: Scout v4 compatibility adapter in the portable bundle

- Status: accepted debt
- Owner: Global Owner Scout
- Introduced: 2026-08-13
- Review by: Core 0.4 planning

The active Scout 5.5 validator and renderer retain `validate_output_v4.py` and `render_review_v4.py` so an already-created private
pre-enrollment task can finish without changing its visible contract mid-run. Bootstrap never creates a new v4 task, and the public
entrypoint always emits Project v4 / Review Pack v4.

This adapter adds legacy vocabulary and code to the portable public bundle. It may be removed when all supported private hosts have
either migrated or explicitly accepted that frozen v4 tasks are no longer resumable. Removal must delete the two adapter files, the
active dispatch branches, their migration test, and this QDR in one change; do not leave renamed backups.
