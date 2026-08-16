# GitHub label taxonomy

Recommended labels for the `meva-health-ai` GitHub repository. These are
not yet created on GitHub — this file documents the proposed set for
review before publishing (see `docs/contributor-issues.md` for the issues
that would use them).

| Label | Description |
|---|---|
| `good first issue` | Small, self-contained, well-specified — a good entry point for a first-time contributor. |
| `help wanted` | Larger or more open-ended than a "good first issue," but still concretely scoped; extra hands welcome. |
| `bug` | Something behaves incorrectly relative to documented/intended behavior. |
| `enhancement` | A new capability or improvement, not a bug fix. |
| `documentation` | Changes to `docs/`, `README.md`, docstrings, or other written material only. |
| `playground` | The CLI playground (`examples/playground.py`) or browser sandbox (`streamlit_app.py`) / `meva.playground`. |
| `fhir` | FHIR resource parsing (`src/meva/fhir/`) or synthetic data handling. |
| `mcp` | The MCP tool layer (`src/meva/mcp/`) that the model uses to retrieve evidence. |
| `benchmark` | Benchmark datasets, cases, or the benchmark engine (`benchmarks/`, `src/meva/benchmark/`). |
| `verifier` | The deterministic verifier (`src/meva/verification/`) — MEVA's core evidence-grounding logic. |
| `testing` | Test coverage, test infrastructure, or CI. |
| `local-ai` | Ollama/model-adapter related work (`src/meva/models/`, agent loop, claim extraction). |

No specific colors are required — GitHub's defaults or repository-owner
discretion are both fine.
