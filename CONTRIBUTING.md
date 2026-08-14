# Contributing

Thank you for improving Agent Memory Sidecar.

Before changing behavior, read `docs/specs/axioms.md`, `docs/specs/topology.md`, and `docs/specs/interface.md` in that order. Cross-
module contracts belong in `specs/`; rationale belongs in `docs/decisions/`; implementation must remain a projection of those owners.

## Development

Use Python 3.11–3.13 and the standard library unless a dependency is separately justified. From the repository root:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -v
python scripts/check_doc_links.py
git diff --check
```

Changes to CLI, Hook, installation, approval, filesystem, Store, Skill, Plugin, or packaging surfaces require regression tests at the
real consumer boundary. Do not commit local Store files, Hook configuration, absolute paths, task IDs, credentials, generated caches,
or private Global Owner contents.

## Pull requests

Keep one coherent behavior change per pull request. Explain the user-visible problem, owner/spec change, failure behavior, tests, and
unproven result layers. A passing test or Doctor report does not prove later-task model adoption or product effect.

By contributing, you agree that your contribution is distributed under the repository's Apache-2.0 license. See [LICENSE](LICENSE).
