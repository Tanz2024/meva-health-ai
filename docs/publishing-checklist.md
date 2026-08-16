# Publishing Checklist — Status

Stage 8E1 filled in all resolvable metadata below with real values supplied
by the maintainer. Nothing here was guessed or invented.

## Resolved (Stage 8E1)

| Field | Value | Files |
|---|---|---|
| **Public author name** | Tanzim Bin Zahir | `CITATION.cff` |
| **GitHub username/organization** | `Tanz2024` | `.github/ISSUE_TEMPLATE/config.yml` |
| **Repository name** | `meva-health-ai` | — |
| **Repository URL** | `https://github.com/Tanz2024/meva-health-ai` | `README.md`, `CONTRIBUTING.md`, `CITATION.cff` (`repository-code`, `url`) |
| **Public contact email** | *None published, by maintainer's request* | `CODE_OF_CONDUCT.md` now directs conduct reports to GitHub (issues / maintainer profile) instead of an email address |
| **Security contact** | *No email — GitHub Private Vulnerability Reporting only* | `SECURITY.md` and `.github/ISSUE_TEMPLATE/config.yml` point to `https://github.com/Tanz2024/meva-health-ai/security/advisories/new` |
| **ORCID** | *None* (declined) | Omitted entirely from `CITATION.cff` — no placeholder or field left behind |

## Still deferred (by design, not oversight)

| Field | Status | Why |
|---|---|---|
| **`date-released` in `CITATION.cff`** | Intentionally omitted (not fabricated) | CFF 1.2.0 does not require this field. It will be added when the actual `v0.1.0` GitHub Release is published — see `CHANGELOG.md`, which also stays `[0.1.0] - Unreleased` until then. |
| **Screenshots** (`docs/images/`) | Not yet captured | Automated capture was attempted in Stage 8D and found impractical in that environment (headless Chrome couldn't render Streamlit's WebSocket-driven UI). Four manual screenshots are still needed — see `docs/playground.md` and the Stage 8D report for the exact list. Not a blocker for the first push. |
| **Repository description** (GitHub "About" field) | Set directly on GitHub, not stored in a repo file | Suggested draft: "Open-source framework for evaluating whether AI agents retrieve and faithfully use medical evidence from synthetic FHIR records — deterministic verification, no real patient data." |
| **GitHub topics** | Set directly on GitHub, not stored in a repo file | Suggested starting set: `fhir`, `healthcare-ai`, `llm-evaluation`, `benchmark`, `synthetic-data`, `model-context-protocol` (matches `pyproject.toml` keywords) |
| **Authors in `pyproject.toml`** | Not currently present | Optional — only matters if/when this is published to PyPI |

## Known packaging note (not a blocker, documented for awareness)

Stage 8D's package build (`python -m build`) confirmed the built wheel
contains only the `meva` Python package — it does **not** bundle
`data/synthetic/synthea/`, `benchmarks/`, `streamlit_app.py`, or
`.streamlit/config.toml` (all repo-root-relative, not package data).
`meva.mcp.registry.DATA_DIR` is computed relative to the installed
package's own file location, so a wheel installed outside a repository
checkout would find zero patients. **This is current, intentional scope**
— MEVA has always been documented as "clone the repo, then install" (see
README Quick Start), never as a standalone PyPI library.

## What this checklist intentionally does NOT include

- The Synthea sample-data licensing question — already resolved in Stage
  8A.1 (see `docs/historical-sample-data-provenance.md` and
  `THIRD_PARTY_NOTICES.md`), not a publishing blocker.
- The git tag / GitHub Release itself — created only when explicitly
  decided, not automated by any script here.
