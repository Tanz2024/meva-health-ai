# MEVA Benchmarking

Stage 7A turns MEVA's single-question verification pipeline (Stage 6/6.5)
into a small, reproducible benchmark framework, orchestrated with
[LangGraph](https://github.com/langchain-ai/langgraph). Stage 7B expands
the dataset (12 → 40 cases, `v0.1` → `v0.2`) and adds richer, more
precise metrics plus a dataset validator. Stage 7B.5 fixes a real
verifier coverage gap Stage 7B found, and expands the synthetic patient
population and dataset again (`v0.2` → `v0.3`, 40 → 56 cases, 3 → 18
patients) for future multi-model comparison. All three stages still use
exactly one local model (`qwen3:4b`) — this is about running many
questions consistently and measuring them precisely, not comparing
models yet.

## Architecture

```text
Benchmark Case
    ↓
LangGraph Workflow   (load_case -> run_agent -> verify_answer -> calculate_metrics -> finalize_result)
    ↓
Local MEVA Agent      (meva.ai.agent — unchanged from Stage 6.5)
    ↓
FHIR/MCP Evidence     (meva.fhir / meva.mcp — unchanged)
    ↓
Structured Claims
    ↓
Deterministic Verification   (meva.verification — unchanged)
    ↓
Benchmark Result
```

No FHIR parsing, tool logic, or verification rule lives in the
benchmark package — every node just calls the existing modules.

## What is a benchmark case?

A `BenchmarkCase` is one fixed question, plus what a correct run should
look like: which patient it's about, which MEVA tools it should need
(`expected_tools`), what evidence a human can check it against
(`expected_evidence`, for traceability), and — when known —
`expected_status` (SUPPORTED/CONTRADICTED/UNSUPPORTED/UNVERIFIABLE).

## Why MEVA uses synthetic patients

Every case in `benchmarks/v0.1/cases.json` references one of the three
official Synthea patient bundles already in `data/synthetic/synthea/`
(see `docs/synthetic-data.md`). Nothing here is invented — each case's
`expected_evidence` was read directly from the actual FHIR bundle before
being written into the case, so any case can be manually re-checked
against the source data.

The 12-case v0.1 dataset:

| Category | Count | Notes |
|---|---|---|
| allergy | 2 | Fish, Mold — both on the same rich patient |
| medication | 2 | Loratadine, Epinephrine |
| condition | 2 | one present (pharyngitis), one genuinely absent |
| observation | 2 | blood pressure, body height |
| empty_evidence | 1 | a patient with zero recorded allergies |
| invalid_patient | 1 | a patient ID that doesn't exist |
| contradiction | 1 | see below |
| multi_tool | 1 | requires two tool calls to fully answer |

### The "contradiction" case is special

A live model can't reliably be made to answer *incorrectly* on demand —
asking it to "pretend" would itself be a fabricated test. So the one
`contradiction` case skips the live model entirely: it feeds a
deliberately wrong, hand-written claim ("no allergies recorded" for a
patient with 7) straight into the same verification step every other
case uses. This proves MEVA's deterministic verifier — not the AI —
is what catches the error, and it's fully offline/reproducible by
construction. See `src/meva/benchmark/graph.py`.

## Stage 7B: v0.2 dataset and richer metrics

Stage 7A's 12-case `v0.1` dataset stays exactly as it was — it's still
the quick smoke-test suite. Stage 7B adds `benchmarks/v0.2/cases.json`,
a 40-case dataset with structured evidence and two distinct case types.

### v0.2 case types: AGENT vs VERIFIER_CHALLENGE

- **AGENT** (37 cases) — runs the normal local-model pipeline, exactly
  like every v0.1 case. This is what tests the model.
- **VERIFIER_CHALLENGE** (3 cases) — bypasses the live model entirely
  and feeds a deliberately wrong or tricky hand-written claim straight
  into MEVA's deterministic verifier (the same mechanism as v0.1's
  single `contradiction` case, generalized). **These must never be
  reported as evidence of model performance** — they test MEVA's
  verification code, not Qwen or any other model.

### v0.2 category distribution (40 cases)

| Category | Count | Notes |
|---|---|---|
| allergy | 6 | 6 of the 7 real allergies on the one patient who has any |
| medication | 6 | 2 real medications (asked about from different angles) + 2 genuine-absence cases + 2 field-specific questions |
| condition | 6 | 1 real condition (asked from different angles) + 2 genuine-absence cases |
| observation | 7 | objective recorded values only — never "is this healthy?" |
| patient | 3 | gender, birth date, name — no calculated age |
| empty_evidence | 3 | patients with zero recorded allergies/medications |
| invalid_patient | 2 | a patient ID that doesn't exist |
| multi_tool | 4 | requires 2 different tools to fully answer |
| verifier_challenge | 3 | CONTRADICTED, UNSUPPORTED, and UNVERIFIABLE(interpretation) challenges |

Only 3 synthetic patients exist in the fixture data, and only one of
them has any allergies/medications/conditions — so several cases in the
same category necessarily reuse the same underlying FHIR resource from
different question angles (e.g. asking about a medication's name, then
its status, then its intent). This is documented explicitly rather than
padded out with invented facts (see `benchmarks/v0.2/manifest.json`,
`"limitations"`).

### Structured expected evidence

v0.2 cases can carry `expected_evidence_facts`, a list of
`{category, value, source_tool, resource_id}` objects — each one
generated directly from the real bundle (see
`examples/inspect_benchmark_data.py`) and checked by
`src/meva/benchmark/validator.py` before being committed. v0.1's
loose `expected_evidence: list[str]` field still works unchanged.

## Tool metrics

Stage 7A's simple `tool_selection_correct` (expected_tools ⊆ actual
tools called) is kept as a **legacy/superset metric** for backward
compatibility, but Stage 7B replaces it as the primary signal with five
more precise metrics, computed per AGENT case:

```text
required_tool_recall  = |expected ∩ unique(actual)| / |expected|         (None if nothing was expected)
tool_precision        = |expected ∩ unique(actual)| / |unique(actual)|   (None if no tools were called)
exact_tool_match      = (unique(actual) == expected)                    (as sets)
tool_overcall_count   = |unique(actual) - expected|
tool_overcall_rate    = (cases with tool_overcall_count > 0) / evaluated AGENT cases   (aggregate-level only)
```

### Duplicate tool calls

Calling the same tool 3 times isn't wrong, but it's wasteful — MEVA
tracks it without penalizing the answer's correctness for it:

```text
unique_tool_calls    = |unique(actual)|
total_tool_calls     = |actual|            (a list, duplicates included)
duplicate_tool_calls = total_tool_calls - unique_tool_calls
```

## Evidence recall

For cases with `expected_evidence_facts`, MEVA checks how many of those
specific facts actually turn up in the case's real tool-call results:

```text
evidence_recall = (expected facts found in the actual tool results) / (total expected facts)
```

Matching reuses MEVA's existing conservative normalizer
(`meva.verification.normalizer.values_match`) — no fuzzy/semantic
medical matching is introduced. If a case has no `expected_evidence_facts`
at all, `evidence_recall` is `None` ("unavailable"), never a guessed 0
or 1.

## Evidence Grounding Score (again)

Same formula as Stage 6, just applied per-case and across the whole
run:

```text
verifiable = supported + contradicted + unsupported   (unverifiable excluded)
score = supported / verifiable, as %   (or "N/A" if verifiable == 0)
```

The benchmark-level `overall_evidence_grounding_score` uses the same
formula over every claim from every completed case.

## Latency reporting

Every case's `RunMetrics` (from Stage 6.5 — Ollama's own reported
`total_duration`, never invented) is summed into tool-call latency and
structured-answer latency, then combined into total latency.
Benchmark-level results report the **median** of each across all
completed cases — median rather than mean, since one slow case
shouldn't overwhelm the reported number, and Ollama runs occasionally
have outlier "warm-up" latency the first time a model is (re)loaded.

## Reproducibility settings

Every benchmark run records the exact generation settings used
(`temperature=0`, `seed=42`, `tool_call_think=true`,
`final_structured_think=false`) alongside the model name and benchmark
dataset version, in the saved JSON report — Stage 6.5's defaults are
kept unchanged, not silently altered for benchmarking.

## Why checkpointing will matter later

The graph is compiled with LangGraph's `InMemorySaver` checkpointer for
now — enough for a single process run and for offline unit tests, since
nothing needs to survive a restart yet. As the benchmark dataset grows
and cases take longer (each case can take 1–3 minutes on a small local
model), a **persistent** checkpointer (e.g. writing to disk) would let
a long benchmark run be resumed from where it left off after a crash or
interruption, instead of re-running every case from the start. The
graph is already structured per-case (each case gets its own
`thread_id`) specifically so that swap is a config change, not a
redesign.

## Result reporting: agent vs. verifier, never combined

`aggregate_metrics()` returns three separate sections —
`dataset` (case counts), `agent` (tool recall/precision/exact-match/
over-call rate/duplicate calls/evidence recall/Evidence Grounding
Score/latency, computed only over AGENT cases), and
`verifier_challenge` (expected vs. achieved verification status per
challenge, and a success rate, computed only over VERIFIER_CHALLENGE
cases). These are never merged into one number — a model's tool-calling
skill and MEVA's verifier correctness are different things, and
blending them would make both misleading.

## Dataset validation

`src/meva/benchmark/validator.py` checks every case *before* a
benchmark runs: unique case IDs, known categories/case types, valid
MEVA tool names, patient existence matching the case's intent (a
`category="invalid_patient"` case must reference a truly nonexistent
patient; every other case must reference a real one),
`expected_evidence_facts` actually present in the real bundle,
VERIFIER_CHALLENGE cases carrying an `injected_claim`, and a keyword
check against diagnosis/treatment-flavored question wording. A broken
dataset fails fast with a specific message per problem, rather than
producing a confusing or misleading run.

### Duplicate detection

`validate_dataset()` also fingerprints every case on
`(patient_id, category, expected_tools, expected_evidence resource IDs,
normalized question text)` — purely deterministic fields, no
embeddings or LLM involved. Two cases sharing that exact fingerprint
are **exact duplicates** and fail validation. Two cases with identical
question wording but a different fingerprint (e.g. same phrasing
reused for a different category) only produce a **warning** — possibly
redundant, but not necessarily wrong, so a human should look rather
than have it silently blocked or silently allowed.

## Stage 7B.5: benchmark validity and v0.3

Stage 7B exposed two problems that had to be fixed before benchmark
scores could be trusted for model comparison:

1. **Verifier coverage gap.** The local model correctly stated an
   allergy's `criticality` and `clinical_status` as separate facts, but
   MEVA's verifier only checked an allergy's *name* — so those true
   statements were scored UNSUPPORTED, artificially lowering the
   Evidence Grounding Score. See `docs/evidence-verification.md` for
   the fix (attribute-level evidence/claims/verification).
2. **Patient diversity gap.** v0.2's 40 cases used only 3 synthetic
   patients — enough to prove the pipeline works, not enough diversity
   for meaningful multi-model comparison later.

### v0.3 dataset

15 more official Synthea synthetic patients were added (18 total, up
from 3 — same source repository, see `docs/synthetic-data.md`), and
`benchmarks/v0.3/cases.json` (56 cases) replaces v0.2 as the
comparison-ready suite. v0.1 and v0.2 are both left exactly as they
were.

| Category | Count |
|---|---|
| allergy | 8 |
| medication | 8 |
| condition | 8 |
| observation | 10 |
| patient | 5 |
| empty_evidence | 4 |
| invalid_patient | 2 |
| multi_tool | 7 |
| verifier_challenge | 4 |

52 AGENT + 4 VERIFIER_CHALLENGE cases, spread across **19 unique
patient IDs** in AGENT cases (18 real synthetic patients + the
intentional invalid-patient sentinel) — well past the "at least 10
distinct patients" target.

### Engineering difficulty label

Every case now carries a `difficulty`: `simple` (one tool, one fact),
`multi_fact` (one tool, 2+ facts — the attribute-verification
regression cases live here), `multi_tool` (2+ tools), `negative`
(absence/empty-evidence), or `error` (invalid patient). This is an
**engineering complexity label, not a medical difficulty judgement** —
`aggregate_metrics()`'s `by_difficulty` groups pass/fail/error counts
by it, so results can be compared by task complexity later without
implying anything is medically "easy" or "hard."

### Structured claim validity rate

`aggregate_metrics()["agent"]["structured_claim_validity_rate"]` is the
mean, across AGENT cases, of each case's fraction of raw model claims
that were well-formed (valid schema, known category, required
value/attribute fields present) — see
`docs/evidence-verification.md`, "Structured claim validity." A
malformed claim is still dropped from verification, never repaired;
this metric exists to make that failure visible, not to hide it.

## Limitations

- This is a **software/research benchmark**, not a clinical validation
  study. Neither `overall_evidence_grounding_score` nor any tool metric
  says anything about diagnostic or clinical correctness — 40 cases is
  an engineering benchmark sample, not sufficient for clinical
  validation or statistical claims about model reliability.
- Only 3 synthetic patients exist in the fixture data; several cases in
  the same category necessarily reuse the same underlying FHIR resource
  from different question angles rather than drawing from many
  different patients.
- `tool_overcall_rate`/`tool_overcall_count` are measured but not
  penalized in pass/fail scoring — only `required_tool_recall`
  (whether every needed tool was called) affects whether a case passes.
- Evidence recall matching is conservative (MEVA's existing normalizer
  only) — a fact phrased very differently from the FHIR display text
  would be marked not-found rather than fuzzy-matched.
- Latency is highly hardware-dependent (see `docs/reproducibility.md`)
  — numbers from this dataset are only meaningful as a relative,
  same-machine comparison over time.
- Attribute-level verification (Stage 7B.5) covers only fields already
  present in MEVA's tool output (allergy criticality/clinical_status,
  medication status/intent, condition clinical_status/onset) — a claim
  about any other metadata field is UNVERIFIABLE, by design, not a bug.
- Only one synthetic patient (patient-03) has any recorded allergies —
  even with 18 total patients, all allergy cases necessarily involve
  that one patient. Medication and condition cases have much better
  patient spread (9 and 13 patients respectively have data).
