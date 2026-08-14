# Privacy

Agent Memory Core stores bounded prompt-event envelopes, one-time approval references, runtime installation identity, and optional
instruction-binding metadata on the local workstation. It does not upload the Core Store, task transcripts, Review Packs, host
project inventories, or private Global Owner contents as part of normal operation.

Public source is built from an allowlist into a new repository root. Engineering history, host evidence, private instructions,
local databases, caches, credentials, and task identifiers are outside that boundary. The exporter rejects physical filesystem
aliases, binary/NUL-bearing files, common credential forms, thread URIs, personal home paths, and caller-supplied private literals.

Removal requires an explicit local uninstall or manual removal after Codex is closed. Do not delete an entire Codex home or project
directory. Preserve any instruction file you still use, and treat old Core Store backups as private local data.

Security issues involving unexpected data capture or disclosure should follow [SECURITY.md](SECURITY.md).
