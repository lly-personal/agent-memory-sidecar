# Agent Memory Sidecar Contribution Guidance

- The north star is cross-session key memory continuity: high-value event -> one explicit user confirmation -> approved scoped
  revision -> later-task behavior change -> revoke.
- Read `docs/specs/axioms.md`, then `docs/specs/topology.md`, then `docs/specs/interface.md` before high-impact design or workflow changes.
- Treat natural project continuation and ordinary Git requests as ordinary project work. Do not invoke Agent Memory governance,
  readiness, trace, or lifecycle machinery solely because the current directory is this repository.
- Keep `AGENTS.md` as the only must-apply behavior owner; Hooks, Store, Git, Memories, tests, and release manifests are not substitutes.
- Define cross-component contracts before implementation and add regression tests for approval, scope, mutation, path, Store, CLI,
  Skill, Plugin, or package changes.
- For substantial design, research, or governance work, use the current public owner documents and evidence: state which facts changed
  the judgment, which assumptions were challenged, which claims remain unproven, and the resulting decision. Historical archives can
  explain provenance but cannot override public `main`; any still-live rationale must return through a public change.
- Treat configured readiness, installed artifacts, public publication, model adoption, continuity, and product effect as separate evidence.
- Never commit runtime Stores, Hook configuration, credentials, private Owner contents, absolute personal paths, task/thread/event IDs,
  or generated cache files.
- For session-facing changes, perform a real Codex Desktop new-task check when available. Hook or `additionalContext` evidence alone
  proves transport, not model adoption.
- Verify with `PYTHONPATH=src python -m unittest discover`, `python scripts/check_doc_links.py`, and `git diff --check`.
