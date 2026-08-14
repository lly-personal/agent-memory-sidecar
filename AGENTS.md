# Agent Memory Sidecar Contribution Guidance

- Read `docs/specs/axioms.md`, then `docs/specs/topology.md`, then `docs/specs/interface.md` before high-impact design or workflow changes.
- Keep `AGENTS.md` as the only must-apply behavior owner; Hooks, Store, Git, Memories, tests, and release manifests are not substitutes.
- Define cross-component contracts before implementation and add regression tests for approval, scope, mutation, path, Store, CLI,
  Skill, Plugin, or package changes.
- Treat configured readiness, installed artifacts, public publication, model adoption, continuity, and product effect as separate evidence.
- Never commit runtime Stores, Hook configuration, credentials, private Owner contents, absolute personal paths, task/thread/event IDs,
  or generated cache files.
- Verify with `PYTHONPATH=src python -m unittest discover`, `python scripts/check_doc_links.py`, and `git diff --check`.
