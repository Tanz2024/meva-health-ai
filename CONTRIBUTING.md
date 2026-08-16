# Contributing to MEVA

Thanks for your interest in MEVA. This guide covers setup, testing, and how
to contribute to the areas that matter most right now.

## Setup

```bash
git clone https://github.com/Tanz2024/meva-health-ai
cd meva-health-ai

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
pytest
```

The full offline test suite should pass with no AI model installed — most
contributions (verifier logic, FHIR parsing, benchmark cases, the sandbox
UI) never need Ollama. Two optional extras exist for specific work:

- `pip install -e ".[playground]"` — needed only if you're working on the
  Streamlit browser sandbox (`streamlit_app.py`). You can also try the
  [live hosted sandbox](https://meva-health-aigit-exbml8bjbokk28zs6amu3h.streamlit.app/)
  or the CLI playground (`examples/playground.py`) without installing anything extra.
- [Ollama](https://ollama.com) + `ollama pull qwen3:4b` (etc.) — needed only
  if you're working on the agent loop, claim extraction, or multi-model
  comparison. Not required for most contributions.

## Running tests

```bash
pytest                    # full suite
pytest tests/test_x.py    # one file
pytest -k "keyword"       # filter by name
```

No test in `tests/` should require Ollama or any network access. If you add
a test that does, it belongs in an `examples/` script instead, run manually.

## Branch naming

Short, descriptive, lowercase-with-hyphens: `fix-observation-value-format`,
`add-fhir-condition-parser`, `docs-update-readme`. No strict enforced
convention beyond that.

## Pull request process

1. Fork, branch, make your change.
2. Run `pytest` — it must pass.
3. Fill out the PR template (`.github/PULL_REQUEST_TEMPLATE.md`).
4. Open the PR against `main`. Describe *why*, not just *what* — link an
   issue if there is one.
5. Be responsive to review feedback. Small, focused PRs move faster than
   large ones.

## Contribution areas

### Adding FHIR resource support

MEVA's FHIR layer lives in `src/meva/fhir/`. Each resource type (allergies,
medications, conditions, observations, encounters) has its own small
parser module — follow that pattern for a new resource type. Add a
corresponding MCP tool in `src/meva/mcp/server.py` if the model should be
able to retrieve it.

### Adding benchmark cases

Benchmark datasets live in `benchmarks/<version>/cases.json`. **Every case
must use only synthetic Synthea patient data already in `data/synthetic/`
— never real patient data, and never fabricated-but-labeled-as-real data.**
Use `meva.benchmark.validator.validate_dataset()` (see
`examples/inspect_benchmark_data.py`) to check a new case against real
retrieved evidence before adding it. See `docs/benchmark-dataset.md` for
the full case schema (`category`, `case_type`, `expected_evidence_facts`,
`difficulty`, etc.).

### Adding a local model adapter

MEVA currently supports any Ollama-served model via
`src/meva/models/registry.py` (`MODEL_REGISTRY`). Adding a new model means
registering it there with its `ModelConfig` — see `docs/model-comparison.md`
for the fairness rules this must follow (same prompts, same schema, no
per-model tuning of the official comparison).

### Adding deterministic verifier tests

`src/meva/verification/verifier.py` is MEVA's core "never trust the model's
self-report" logic. New tests in `tests/test_verifier*.py` that cover an
edge case (a new assertion type interaction, a normalization edge case,
etc.) are always welcome — this is one of the highest-value places to
contribute test coverage.

### Improving the sandbox (CLI or browser)

`src/meva/playground/service.py` holds the reusable logic behind both
`examples/playground.py` (CLI) and `streamlit_app.py` (browser) — neither
duplicates the other, and neither implements its own verification rules.
UI polish, clearer claim-builder guidance, and evidence-explorer
improvements are welcome; see `docs/playground.md` for how the four modes
(public hosted sandbox, local browser sandbox, local CLI, full local AI)
relate to each other.

### Documentation

Clarifications, fixed typos, better examples, and improved explanations in
`docs/` are genuinely useful contributions, not just "nice to have."

### Realistic entry points if you're new here

See **[`docs/contributor-issues.md`](docs/contributor-issues.md)** for a
set of concretely scoped starter tasks (each with expected files, behavior,
and tests) — several are marked "good first issue." A few quick examples:

- Add a deterministic verifier edge-case test
- Add a new synthetic benchmark case (with real evidence-fact validation)
- Improve an existing `docs/*.md` file's clarity
- Improve MCP tool error handling/messages
- Improve the CLI or sandbox UI output of a `playground`-related script

We can't promise contributors will show up for any of these — they're
listed as realistic starting points, not guarantees.

## What we will not accept

- Real patient data, in any form, anywhere in the repository.
- Paid/cloud AI API integrations (MEVA is local-inference-only by design).
- Diagnosis or treatment-recommendation functionality.
- Changes that weaken the deterministic verifier's independence from the
  model being evaluated (e.g. letting an LLM judge its own claims).

## Code of Conduct

By participating, you agree to follow `CODE_OF_CONDUCT.md`.
