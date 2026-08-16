# MEVA Decoupled Claim Extraction Evaluation

Stage 7D1 adds a second, clearly separate evaluation mode. It does **not**
replace or invalidate Stage 7C2's END_TO_END benchmark — both modes remain
official, and their numbers must never be silently combined.

## Why structured output is a confounding factor

MEVA's END_TO_END benchmark (Stage 7A–7C2) asks the tested model to do four
things in one pass: choose tools, retrieve evidence, answer the question in
prose, and encode its own answer into MEVA's structured `MedicalClaim`
schema. Stage 7C2 showed these can diverge sharply — `llama3.2:3b` answered
many questions in correct, sensible prose but produced zero valid structured
claims for half of them (`zero_claim_rate = 0.50`). An END_TO_END score
blends "did the model know the right answer" with "did the model correctly
format JSON," and a low score can't tell you which one failed.

## Two official modes

**END_TO_END** (Stage 7A–7C2, unchanged):

```
tested model -> answer + own structured claims -> deterministic verifier
```

**DECOUPLED** (Stage 7D1):

```
tested model -> natural-language answer
             -> fixed claim extractor -> extracted MedicalClaims
             -> deterministic verifier (same verifier, unchanged)
```

Every reported result is tagged `mode: "END_TO_END"` or `mode: "DECOUPLED"`.
No metric anywhere averages or blends the two.

## The fixed extractor

Stage 7D1 uses `qwen3:4b` as a single fixed local extractor for every
source model's answers, including qwen3:4b's own. This is **model-assisted
extraction, not deterministic parsing** — running the extractor twice on the
same input is not guaranteed to produce byte-identical output, even at
`temperature=0, seed=42` (see `docs/reproducibility.md` for what MEVA's
reproducibility settings do and don't guarantee for a local model). What
*is* fixed and controlled is that every source model's answers go through
the exact same extractor, with the exact same settings, so the comparison
between source models stays fair — only the final verification step
(`meva.verification.verifier.build_report`) is fully deterministic Python.

## Anti-leakage rule

The extractor receives **only**:

- the original question
- the patient_id
- the tested model's natural-language answer text

It never receives the FHIR bundle, `EvidenceFact` objects, MCP tool
results, the benchmark's expected evidence, the expected verification
result, or the tested model's own original structured claims. If the
extractor could see real evidence, it could "fix" a wrong answer by adding
correct information the tested model never actually said — which would
measure the extractor's knowledge, not the tested model's answer. See
`meva.extraction.extractor.ALLOWED_EXTRACTOR_INPUT_FIELDS` and
`tests/test_extraction_anti_leakage.py`.

Concretely: if a model answers "No blood pressure was found" and the real
FHIR record has 128/81 mmHg, the extractor must extract `assertion=absent,
category=observation, value=Blood Pressure` — the same (wrong) claim the
model actually made. It must **not** extract "Blood pressure is 128/81."
MEVA's unmodified deterministic verifier then correctly marks that claim
CONTRADICTED. The extractor's job is only to represent what was said, never
to correct it or consult outside knowledge.

## Why the verifier remains deterministic

Only the claim *extraction* step is model-assisted. Verification — matching
an extracted claim against real, freshly retrieved FHIR evidence — is the
exact same `meva.verification.verifier.build_report()` function used in
END_TO_END mode, completely unchanged. An LLM is never asked whether its own
(or another model's) claim was correct.

## Extractor quality vs. grounding metrics

Two clearly separate metric groups, both reported per source model:

**Extractor quality** (describes the fixed extractor's own behavior, not the
source model's answer quality): `extractor_schema_success_rate`,
`extracted_claim_validity_rate`, `zero_extracted_claim_rate`,
`extraction_error_rate`, `total_extracted_claims`.

**DECOUPLED grounding** (the same formulas as END_TO_END's grounding
metrics, run over extracted rather than self-generated claims):
SUPPORTED/CONTRADICTED/UNSUPPORTED/UNVERIFIABLE counts, Evidence Grounding
Score, Verifiable Claim Coverage.

A DECOUPLED score changing from a source model's END_TO_END score reflects a
change in **evaluation method** — it is never described as the tested model
itself "improving" or "getting worse."

## Extractor bias — an explicit limitation

The initial decoupled experiment uses qwen3:4b as the fixed claim extractor.
This may introduce extractor-specific bias and should be tested with
another extractor in future work. Because qwen3:4b is both a tested source
model and the fixed extractor, its own DECOUPLED numbers in particular
should be read with this in mind.

## Not yet proof of anything clinical

**Decoupled evaluation does not prove clinical correctness or safety.** It
isolates one engineering confound (structured-output formatting) from
another (answer content) — nothing here is a medical accuracy, diagnostic
accuracy, or clinical safety claim, in either mode.
