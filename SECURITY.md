# Security Policy

## Supported versions

Security fixes are provided for the latest published release. Unreleased source snapshots and historical tags are not supported
distribution channels.

## Reporting a vulnerability

Please use GitHub private vulnerability reporting for this repository. Do not open a public issue for a suspected vulnerability,
credential exposure, authorization bypass, path-containment failure, or supply-chain problem.

Include the affected version or commit, operating system, entrypoint, minimal reproduction, observed impact, and whether the issue
can write outside the authorized instruction or Store target. Do not include real secrets, private rule contents, prompt text, or
personal filesystem paths.

Maintainers will acknowledge a complete report within 7 calendar days, provide an initial assessment within 14 days, and coordinate
disclosure after a fix or documented mitigation is available. These are response targets, not a warranty or service-level agreement.

## Security boundary

Agent Memory writes user-authorized rules to scoped `AGENTS.md` targets and stores bounded event metadata locally. Reports involving
approval reuse, scope confusion, symlink/reparse/hardlink escape, Store permissions, release-source substitution, or leaked private
Owner contents are security relevant. Model-quality disagreements without an authorization or containment impact are ordinary bugs.
