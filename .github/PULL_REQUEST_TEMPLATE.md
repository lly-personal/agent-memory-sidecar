## Problem and user-visible result

Describe the repeated problem and the smallest behavior change.

## Owner and contract

Name the L1/L2/L3, detailed spec, or ADR changed. Explain why no second behavior owner is introduced.

## Verification

- [ ] `PYTHONPATH=src python -m unittest discover`
- [ ] `python scripts/check_doc_links.py`
- [ ] `git diff --check`
- [ ] Installed/package consumer checked when applicable
- [ ] No private paths, prompts, rules, credentials, task IDs, Store files, or cache artifacts added

## Evidence boundary

State the highest result layer actually proven and what remains unproven.
