# MEVA Baseline Results — Benchmark v0.3

This is MEVA's detailed public benchmark report for dataset version v0.3.
It summarizes results already produced and saved during Stages 7C1–7D2.2 —
see each linked doc for full methodology. Nothing in this document was
regenerated for publication; all numbers here trace back to specific saved
result files, listed at the end.

**This is an engineering/research benchmark of tool-use, structured-output
adherence, and evidence-grounding behavior. It is not a clinical accuracy,
safety, or diagnostic evaluation. See "Scope and safety" in the README.**

## Benchmark identity

- Benchmark version: **v0.3**
- MEVA version: **0.1.0**
- Synthetic patients: **18** real Synthea-generated patients (Apache-2.0
  generator; see `THIRD_PARTY_NOTICES.md` for the sample-data licensing
  caveat), plus 1 intentional invalid-patient sentinel ID
- Total cases: **56**
- Case types: **52 AGENT**, **4 VERIFIER_CHALLENGE** (run once, never scored
  per-model — see `docs/benchmarking.md`)
- Categories: allergy (8), medication (8), condition (8), observation (10),
  patient (5), empty_evidence (4), invalid_patient (2), multi_tool (7),
  verifier_challenge (4)
- Difficulty labels (engineering complexity, not medical difficulty):
  simple (31), multi_fact (4), multi_tool (7), negative (12), error (2)

Full dataset details: `docs/benchmark-dataset.md`. Dataset validation logic:
`meva.benchmark.validator`.

## Models evaluated

| Model | Ollama tag | Digest | Parameter size | Quantization | License |
|---|---|---|---|---|---|
| qwen3:4b | `qwen3:4b` | `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7` | 4.0B | Q4_K_M | Apache License 2.0 |
| llama3.2:3b | `llama3.2:3b` | `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` | 3.2B | Q4_K_M | Llama 3.2 Community License (not OSI-approved) |

Both run locally through Ollama at `temperature=0, seed=42`; `think` is
enabled for qwen3:4b's tool-calling phase (disabled for its final structured
answer) and disabled entirely for llama3.2:3b (it doesn't support Ollama's
`think` parameter — see `docs/model-comparison.md`).

## Evaluation modes

MEVA reports two distinct evaluation modes — never combined into one score
(see `docs/decoupled-evaluation.md`):

- **END_TO_END**: the tested model answers AND encodes its own answer into
  MEVA's structured `MedicalClaim` schema, in one pass.
- **DECOUPLED**: the tested model answers in prose only; a separate FIXED
  extractor (qwen3:4b, `temperature=0, seed=42, think=false`) converts that
  saved prose into structured claims, which are then verified identically.

## Retrieval metrics (END_TO_END, 52 AGENT cases each)

| Metric | qwen3:4b | llama3.2:3b |
|---|---|---|
| Tool recall | 1.000 | 0.981 |
| Tool precision | 1.000 | 1.000 |
| Exact tool match | 1.000 | 0.962 |
| Evidence recall | 0.810 | 0.738 |

## Structured-output metrics (END_TO_END)

| Metric | qwen3:4b | llama3.2:3b |
|---|---|---|
| Structured claim validity | 0.917 | 0.087 |
| Verifiable claim coverage (corrected) | 0.656 | 0.120 |
| Zero-claim rate | 0.173 | 0.500 |

### A note on the verifiable-coverage correction (Stage 7C2.1)

The **original** Stage 7C2 aggregate `verifiable_claim_coverage` calculation
used an unweighted **per-case mean** of each case's own coverage ratio —
which silently excluded zero-claim cases from the denominator instead of
counting them as 0% coverage. This produced 0.804 (qwen3:4b) / 0.058
(llama3.2:3b) in the original saved report. The implementation was audited
(Stage 7C2.1) and corrected to the **documented micro-average formula** —
`(SUPPORTED + CONTRADICTED + UNSUPPORTED) / total_emitted_claims`, computed
from the whole run's totals — producing the corrected **0.656 / 0.120**
reported everywhere in this document. **The original (uncorrected) result
file was preserved, not deleted or silently replaced** — both are still in
the repository's `results/` directory (gitignored, so not part of the
published repo, but the correction methodology and both numbers are
documented transparently here and in `docs/model-comparison.md`'s revision
history). This history is disclosed deliberately, not hidden.

## Grounding metrics — END_TO_END vs DECOUPLED

| Metric | qwen3:4b E2E | qwen3:4b DECOUPLED | llama3.2:3b E2E | llama3.2:3b DECOUPLED |
|---|---|---|---|---|
| Evidence Grounding Score | 83% | 89% | 70% | 80% |
| Verifiable claim coverage | 0.656 | 0.990 | 0.120 | 0.987 |
| Supported | 68 | 85 | 7 | 59 |
| Contradicted | 8 | 8 | 1 | 10 |
| Unsupported | 6 | 3 | 2 | 5 |
| Unverifiable | 43 | 1 | 73 | 1 |

**Read grounding score together with coverage, always.** A high grounding
score computed over very few verifiable claims (as in llama3.2:3b's
END_TO_END row) looks better than it is — most of that model's raw output
wasn't checkable at all. See `docs/decoupled-evaluation.md`.

**DECOUPLED is not "the model got better."** It is a different evaluation
method — the same saved prose run through a fixed extractor instead of the
model's own (often broken) structured output. Claim recovery under this
method: qwen3:4b 13/52 cases (25%), llama3.2:3b 51/52 cases (98%) — llama's
prose was usually fine; its own JSON formatting was the primary failure.
Grounding failures were also independently **preserved** across both
methods in 8 qwen3:4b cases (all observation-category) — decoupling does
not erase a genuine wrong answer.

## Extractor validation (Stage 7D2 / 7D2.1)

The fixed extractor (qwen3:4b) is **not perfect** — its DECOUPLED coverage
numbers above (0.99 / 0.99) describe how much of its *output* the verifier
could check, not how *accurately* it represents the source answer. Semantic
extraction fidelity was separately measured against hand-authored fixtures,
with prompt development and a held-out evaluation set kept strictly
separate (`docs/claim-extraction-contract.md`):

| Metric | Development (10 fixtures) | Holdout (14 fixtures, unseen during development) |
|---|---|---|
| Schema success | 1.000 | 1.000 |
| Claim precision | 1.000 | **0.929** |
| Claim recall | 1.000 | **0.813** |
| Claim F1 | 1.000 | **0.867** |
| Exact claim-set match | 1.000 | 0.857 |
| Negative-claim preservation | 1.000 | 1.000 |
| Attribute claim accuracy | 1.000 | 0.750 |

The holdout numbers — not the perfect development numbers — are the honest
estimate of extractor reliability. **Do not read the 99% DECOUPLED coverage
figures above as "99% extraction accuracy"** — they measure something
different (verifier-checkable output volume, not semantic correctness).

## Observation category — an independently audited finding

Both models scored unusually low on the observation category:
**qwen3:4b 20%, llama3.2:3b 0% grounding (n=10 cases each)**. Stage 7D2.2
independently audited every observation case against MEVA's real,
deterministic FHIR/tool layer and found:

- all 10 expected facts were genuinely present and traceable in the
  synthetic FHIR data
- all 10 were within the default tool retrieval limit (no truncation)
- no extraction or verification bug was found
- **18 of 20 model-case pairs are genuine model grounding errors** — this
  finding remains valid, not an artifact of the benchmark or evaluation code

One non-blocking tool-output-shape issue was documented (Blood Pressure
observations currently expose a `null` top-level `value` field, with the
actual reading in a separate `blood_pressure` key) as a plausible
contributing factor for 4 of qwen3:4b's 8 failures — flagged as future work
(`ROADMAP.md`), not fixed retroactively. Full detail: `docs/observation-audit.md`.

**This is a benchmark-behavior finding, not a clinical performance
statement.**

## Latency (this machine, Darwin arm64; not portable across hardware)

| | qwen3:4b | llama3.2:3b |
|---|---|---|
| Median total latency (END_TO_END) | 51.4s | 8.3s |
| Median extraction latency (DECOUPLED, per answer) | 6.2s | 5.7s |

Extraction latency is the fixed extractor's own cost, kept separate from —
never added to — the source model's own inference latency.

## Limitations

- Single machine, single run per configuration — no repeated-trial variance
  reported.
- Only two source models compared; only one fixed extractor (qwen3:4b, also
  one of the two source models) validated so far — a documented
  extractor-bias caveat throughout (`docs/decoupled-evaluation.md`).
- 56-case dataset, 18 unique patients — not a large-scale clinical dataset.
- All grounding/coverage/validity metrics measure engineering behavior
  (tool use, JSON schema adherence, evidence matching) — none measure
  medical correctness, diagnostic accuracy, or clinical safety.

## Source result files (not published in the public repo; `results/` is gitignored)

- `results/comparisons/comparison-v0.3-full-20260815-230131.json` (original, uncorrected)
- `results/comparisons/comparison-v0.3-full-20260815-230131-corrected.json` (corrected, Stage 7C2.1)
- `results/extraction/extractor-fidelity-20260816-114026.json` (original Stage 7D2 gate-failing audit)
- `results/extraction/extractor-fidelity-dev-20260816-115004.json`, `extractor-fidelity-holdout-20260816-115042.json` (Stage 7D2.1)
- `results/extraction/decoupled-v0.3-full-20260816-121147.json` (full 104-answer decoupled run)

## Further reading

- `docs/benchmarking.md` — the benchmark engine
- `docs/benchmark-dataset.md` — dataset construction and validation
- `docs/evidence-verification.md` — the deterministic verifier
- `docs/decoupled-evaluation.md` — why two evaluation modes exist
- `docs/claim-extraction-contract.md` — the extraction schema contract
- `docs/observation-audit.md` — the observation-category audit
- `docs/reproducibility.md` — what MEVA's reproducibility settings do and don't guarantee
- `docs/model-comparison.md` — multi-model comparison methodology
