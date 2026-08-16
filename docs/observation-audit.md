# MEVA Observation Category Sanity Audit (Stage 7D2.2)

## Why this audit was performed

Stage 7D2's full 104-answer decoupled evaluation showed unusually poor
observation-category grounding: qwen3:4b 20% (n=10), llama3.2:3b 0% (n=10) —
markedly worse than every other category for both models. Before publishing
these numbers, this audit checks whether that reflects genuine model
behavior or a benchmark/retrieval/extraction/verification bug. This is an
**offline audit only** — no model was rerun. Everything below was
reconstructed from `results/comparisons/comparison-v0.3-full-20260815-230131-corrected.json`,
`results/extraction/decoupled-v0.3-full-20260816-121147.json`, and direct,
fresh calls to MEVA's existing deterministic FHIR/tool layer
(`meva.mcp.server.get_observations`) against the same static synthetic data.

## 1. Observation case count

**10** v0.3 AGENT cases have `category == "observation"`:
`observation-01` through `observation-10`, one per patient, each asking for
"the first recorded" blood pressure / body height / heart rate / body
weight / respiratory rate.

## 2. Cases audited (all 10)

| case_id | patient_id | vital | resource_id | expected value |
|---|---|---|---|---|
| observation-01 | 6895f047... | Blood Pressure | 078aa38b... | 128/81 mmHg |
| observation-02 | 363f50e2... | Body Height | c55fa7a8... | 48.2 cm |
| observation-03 | c28b00a3... | Blood Pressure | c35ab0b4... | 129/83 mmHg |
| observation-04 | faac724a... | Heart Rate | eb9076fe... | 88 /min |
| observation-05 | d8e3a701... | Blood Pressure | 655de2d0... | 108/81 mmHg |
| observation-06 | 2798ae24... | Body Weight | fe49874d... | 4.1 kg |
| observation-07 | 423a9252... | Respiratory Rate | 43c9421c... | 16 /min |
| observation-08 | a57b5df9... | Body Height | 947b4489... | 190.7 cm |
| observation-09 | 7d5e31d3... | Heart Rate | a626ffd3... | 93 /min |
| observation-10 | e4c43a21... | Blood Pressure | d21c91e2... | 121/77 mmHg |

Both source models' saved answers, extracted claims, and verification
statuses for every case are in the "Failure classification" table below.

## 3. Expected FHIR evidence — verified independently

For every case, a fresh call to `meva.mcp.server.get_observations(patient_id,
limit=100)` (the full available set, bypassing the model-facing default
limit) confirmed:

- the patient exists and `get_observations` returns successfully
- the expected observation's `resource_id` is present in the result
- the expected value (e.g. `"128/81 mmHg"`, `"48.2 cm"`) matches exactly via
  `meva.verification.normalizer.values_match` (case/whitespace-normalized
  equality — no fuzzy matching)

**Result: 10/10 expected facts verified traceable to the real synthetic FHIR
bundle, with matching values.** The benchmark dataset's `expected_evidence_facts`
are not the source of the problem.

## 4. Retrieval-limit / truncation findings

`get_observations` defaults to `limit=20` (of up to 100+ available for some
patients) and does **not** sort by date — it returns Observation resources
in the order they appear in the FHIR bundle. This raised a real concern: if
the target vital fell outside the first 20 bundle-order observations, a
model could genuinely never see it, and "hallucination" would be an unfair
description.

A direct call to `get_observations(patient_id, limit=20)` for every case
confirmed the expected observation's bundle-order position:

| case_id | total available | position (bundle order) | in first 20? |
|---|---|---|---|
| observation-01 | 99 | 6 | yes |
| observation-02 | 29 | 1 | yes |
| observation-03 | 29 | 6 | yes |
| observation-04 | 81 | 7 | yes |
| observation-05 | 57 | 5 | yes |
| observation-06 | 75 | 3 | yes |
| observation-07 | 56 | 8 | yes |
| observation-08 | 58 | 1 | yes |
| observation-09 | 56 | 7 | yes |
| observation-10 | 56 | 6 | yes |

**Result: no truncation issue for any case.** Every expected observation was
well within the default 20-item result (positions 1–8), assuming the agent
called `get_observations` with its default `limit` — MEVA's tool schema
doesn't require the model to specify one, and both models' saved logs show
`exact_tool_match=True` for every observation case (i.e., they called
exactly `get_observations`, the required tool). No log of the exact
arguments used at inference time was persisted (only tool *names* are saved
to `BenchmarkResult.tool_calls`, not arguments), so this default-limit
assumption cannot be verified from saved data alone — it is the only
reasonable assumption given the tool's own default and the absence of any
evidence to the contrary, and is flagged here as exactly that: an
assumption, not a certainty.

## 5. Observation normalization audit

Compared claim values against evidence for Blood Pressure, Heart Rate,
Respiratory Rate, Body Weight, and Body Height. `values_match()` performs
case-insensitive, whitespace-normalized, substring-tolerant comparison
(unchanged, Stage 1–7 behavior) — e.g. a claim value of `"Body Height: 48.2
cm"` correctly matches an evidence value of `"48.2 cm"` because the shorter
string is a normalized substring of the longer one. No normalization bug
was found for any of the 5 vital types; no fuzzy medical-synonym matching
was introduced or is needed.

## 6. A genuine tool-output shape finding (not a scoring bug)

For all 4 Blood Pressure cases, `get_observations`'s returned dict has:

```json
{"id": "...", "name": "Blood Pressure", "value": null,
 "components": [{"name": "Diastolic...", "value": "81 mm[Hg]"}, {"name": "Systolic...", "value": "128 mm[Hg]"}],
 "blood_pressure": "128/81 mmHg"}
```

The **top-level `"value"` field is `null`** for a composite (blood-pressure)
observation — the actual combined reading only exists in a `"blood_pressure"`
key that MEVA's server layer (`meva.mcp.server.get_observations`) appends
after `"components"`. Every other vital type in this dataset (Heart Rate,
Respiratory Rate, Body Weight, Body Height) has a normal, populated
top-level `"value"` field.

This is **not a scoring bug** — the data genuinely is present in the tool
result, `blood_pressure_text()` correctly computes it
(`meva.fhir.observations.blood_pressure_text`), and MEVA's verifier
correctly used it to mark the "absent blood pressure" claims CONTRADICTED.
But it is a plausible, real contributing factor to why a model reading a
long JSON tool result might report "no blood pressure was found" — the
field most naturally associated with "the value" is `null`, and the actual
reading is a secondary key a model has to know to look for. This is
documented here as a finding for future tool-output-shape improvement, not
applied as a fix in this stage (see "Do not change code yet," Stage 7D2.2 §9).

**Proposed fix (not applied):** populate `Blood Pressure`'s top-level
`"value"` with the combined `"128/81 mmHg"` reading (or otherwise ensure
`"value"` is never `null` when data exists), in
`meva.mcp.server.get_observations` / `meva.fhir.observations.get_observations`.

## 7. Absence-claim verification is category-wide, not item-specific

`meva.verification.verifier._verify_observation` (and `_verify_presence_category`
for allergy/medication/condition, the same existing pattern) verifies an
`assertion="absent"` claim against **all** facts in that category — "no
blood pressure was found" is checked as "are there zero observations at all
for this patient," not "is there specifically no blood-pressure
observation." This is pre-existing, documented behavior (unchanged by this
audit), not a Stage 7D2.2 finding of a new bug. It did not affect any
verdict in this dataset: every patient audited here genuinely has multiple
observations (including the target vital), so every "absent" observation
claim is correctly CONTRADICTED either way. Flagged here for completeness,
per item 7 of the audit instructions ("record this distinction").

## 8. Failure classification (deterministic, no LLM judge)

| case_id | qwen3:4b | llama3.2:3b | classification |
|---|---|---|---|
| observation-01 (BP) | absent -> CONTRADICTED | absent -> CONTRADICTED | TRUE_MODEL_GROUNDING_ERROR (both) — contributing factor: BP `value:null` tool-shape ambiguity (§6) |
| observation-02 (Height) | value -> SUPPORTED | absent -> CONTRADICTED | qwen: none (correct). llama: TRUE_MODEL_GROUNDING_ERROR — plain populated value field, position 1, no tool-shape excuse |
| observation-03 (BP) | absent -> CONTRADICTED | absent -> CONTRADICTED | TRUE_MODEL_GROUNDING_ERROR (both) — same BP contributing factor |
| observation-04 (HR) | absent -> CONTRADICTED | absent -> CONTRADICTED | TRUE_MODEL_GROUNDING_ERROR (both) — plain populated value field, no tool-shape excuse |
| observation-05 (BP) | absent -> CONTRADICTED | absent -> CONTRADICTED | TRUE_MODEL_GROUNDING_ERROR (both) — BP contributing factor |
| observation-06 (Weight) | absent -> CONTRADICTED | absent -> CONTRADICTED | TRUE_MODEL_GROUNDING_ERROR (both) |
| observation-07 (Resp. rate) | absent -> CONTRADICTED | absent -> CONTRADICTED | TRUE_MODEL_GROUNDING_ERROR (both) |
| observation-08 (Height) | value -> SUPPORTED | absent -> CONTRADICTED | qwen: none (correct). llama: TRUE_MODEL_GROUNDING_ERROR |
| observation-09 (HR) | absent -> CONTRADICTED | absent -> CONTRADICTED | TRUE_MODEL_GROUNDING_ERROR (both) |
| observation-10 (BP) | absent -> CONTRADICTED | absent -> CONTRADICTED | TRUE_MODEL_GROUNDING_ERROR (both) — BP contributing factor |

No case in this category was classified as RETRIEVAL_TRUNCATION,
EXTRACTION_ERROR, VERIFIER_FORMAT_MISMATCH, BENCHMARK_EXPECTATION_ERROR,
UNVERIFIABLE_BY_CURRENT_RULES, or OTHER — every expected fact was correctly
retrievable, correctly retrieved (assumption noted in §4), correctly
extracted (DECOUPLED extraction reproduced each source answer's claim
exactly, with no repair or invention — see
`results/extraction/runs/decoupled-full-run1.json`), and correctly verified.

### Classification counts

| Classification | Count (of 20 model-case pairs) |
|---|---|
| TRUE_MODEL_GROUNDING_ERROR | 18 (qwen: 8, llama: 10) |
| No error (SUPPORTED, correct) | 2 (qwen: 2, llama: 0) |
| RETRIEVAL_TRUNCATION | 0 |
| EXTRACTION_ERROR | 0 |
| VERIFIER_FORMAT_MISMATCH | 0 |
| BENCHMARK_EXPECTATION_ERROR | 0 |
| UNVERIFIABLE_BY_CURRENT_RULES | 0 |
| OTHER | 0 |

## Interpretation

**qwen3:4b's 20% (2/10) observation grounding remains valid.** Both
successes (Body Height, a simple populated-value field) and all 8 failures
(4 Blood Pressure + 2 Heart Rate + Body Weight + Respiratory Rate) reflect
genuine model behavior given data that was correctly retrieved and
presented — not a benchmark, retrieval, extraction, or verification bug.
The 4 Blood Pressure failures have a documented, plausible contributing
factor (§6) worth fixing in a future stage, but the underlying claim ("no
blood pressure was found") is still factually false relative to the
evidence the model had access to, so CONTRADICTED remains the correct
verdict.

**llama3.2:3b's 0% (0/10) observation grounding remains valid.** llama
failed even the two straightforward Body Height cases that qwen answered
correctly (single populated value field, no composite-observation
ambiguity), indicating a broader grounding weakness in this category for
llama3.2:3b specifically, not an artifact of the BP tool-shape issue.

## Recommendation

**Safe to proceed to Stage 8.** No bug was found that invalidates the
Stage 7C2/7D2 published grounding numbers for the observation category. One
legitimate tool-output-shape improvement was identified (§6) and is
recommended as a documented follow-up item for a future stage — it was
deliberately **not** applied in Stage 7D2.2, per the instruction to
document root causes rather than modify verification/benchmark code during
an audit.
