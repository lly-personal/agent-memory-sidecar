# Threat model

## Trust boundary

Core provides deterministic scope, target-identity, physical-containment, one-time authorization, atomic-write, and bounded-storage
guards. The Agent remains responsible for semantic interpretation: deciding whether a user statement asks to remember a rule and
constructing the candidate's trigger, action, skip boundary, rationale, evidence, instruction target, and scope.

Bundle confirmation binds the exact visible selection, card hashes, target before-state, and one approval consumption. A malicious
prompt or repository instruction can still try to persuade the Agent to form the wrong candidate; Core cannot prove human intent
from natural language alone.

## Defended threats

- reuse or replay of an approval reference;
- mutation of a different target or a changed target-before state;
- partial writes across a confirmed multi-card bundle;
- symlink, junction, reparse-point, hardlink, or ancestor-alias traversal for sensitive files;
- release source drift between repository, ref, and commit;
- accidental inclusion of private engineering history or unselected files in the public source tree.

## Out of scope

An administrator or process that can replace the interpreter, Git executable, operating-system trust store, Codex runtime, or files
after verification is outside the in-process boundary. Public release, adoption, and product effectiveness require separate evidence
and are not implied by source tests or local artifact construction.
