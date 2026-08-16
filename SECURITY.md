# Security Policy

## Reporting a vulnerability

If you find a security issue in MEVA (e.g. a path-traversal risk in the
MCP tool layer, an injection vector in benchmark/config loading, or a
dependency vulnerability), **please report it privately using GitHub's
Private Vulnerability Reporting feature on this repository**
(`https://github.com/Tanz2024/meva-health-ai/security/advisories/new`) —
do not open a public issue or pull request describing the vulnerability.
No public email address is published for this project.

Please include:

- A description of the issue and its potential impact
- Steps to reproduce
- Any relevant logs (with secrets/paths redacted)

We'll acknowledge your report and work with you on a fix and disclosure
timeline.

## Scope

MEVA is a local-first research/engineering tool. Relevant security concerns
include (but aren't limited to):

- Path traversal or unauthorized file access in `src/meva/mcp/registry.py`
  or anywhere else that resolves a filename from user/model input
- Injection issues in benchmark case loading or CLI argument handling
- Dependency vulnerabilities in `mcp`, `langgraph`, `langchain-core`, or
  `pydantic`

## Out of scope / not applicable

- MEVA does not handle real patient data, authentication, or network
  services beyond talking to a locally-run Ollama instance — many
  traditional web-app security concerns (session management, auth bypass,
  etc.) don't apply here.
- Vulnerabilities in Ollama itself, or in a model's own weights/behavior,
  should be reported to those projects directly, not here.

## Please do not

**Do not include real patient data in a security report, issue, or pull
request, under any circumstances** — this project's synthetic-data-only
policy applies to all content submitted here, including bug reports.
