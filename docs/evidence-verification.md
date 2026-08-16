# MEVA Evidence Verification

This is MEVA's core feature. It's not a smarter chatbot — it's a
deterministic checker that catches when a local AI's answer doesn't
actually match the real medical evidence it retrieved.

## The core idea

An LLM should never be the judge of its own answer. So MEVA splits the
work into two very different kinds of code:

```text
FHIR evidence
      ↓
Local AI answer               <- the model (qwen3:4b) does this part
      ↓
Structured claims
      ↓
Deterministic MEVA verification   <- plain Python does this part, no AI involved
      ↓
Supported / Contradicted / Unsupported / Unverifiable
```

The verification step (`src/meva/verification/verifier.py`) is ordinary
`if`/`else` Python code comparing strings. It never asks the model
"was your answer correct?" — it checks the model's claims against the
same real FHIR data MEVA's tools returned.

## What is a claim?

A **claim** (`MedicalClaim`) is one small, specific factual statement
extracted from the AI's answer — e.g. "the patient has a Fish allergy."
Each claim has:

- `category` — what kind of thing it's about (`allergy`, `medication`, `condition`, `observation`, `encounter`, or `patient`)
- `assertion` — `present` (something exists), `absent` (nothing is recorded), `value` (an exact recorded value), `attribute` (a metadata field of an already-identified item — see below), or `interpretation` (an opinion/judgement — always unverifiable)
- `value` — the specific thing being claimed (e.g. `"Fish"`), when relevant
- `attribute` / `attribute_value` — only used with `assertion="attribute"` (added in Stage 7B.5): which metadata field (e.g. `"criticality"`) and what value it's claimed to have (e.g. `"low"`)

## What is evidence?

**Evidence** (`EvidenceFact`) is a fact built directly from a real,
successful MEVA tool call — never invented. If `get_allergies()` returns
an allergy, that becomes one `EvidenceFact`. If a tool call fails
(e.g. unknown patient), no evidence is created for that patient at all —
the failure is tracked separately (`PatientNotFoundError`), so an
unknown patient can never accidentally look like "no allergies recorded."

## What is provenance?

**Provenance** means every verdict shows exactly which evidence produced
it — the source tool and the original FHIR resource ID. This answers
"why did MEVA say that?" instead of asking you to trust a black box.

## Attribute-level evidence (Stage 7B.5)

Stage 7B's benchmarking exposed a real gap: MEVA's tools already return
metadata about an item — an allergy's `criticality` and `clinical_status`,
a medication's `status` and `intent`, a condition's `clinical_status` and
`onset` — but the verifier only ever checked an item's primary name/value.
So when a model correctly stated "this allergy's criticality is low," MEVA
had no way to check it and scored it UNSUPPORTED even though it was true.

`EvidenceFact` now carries an `attributes: dict[str, str]` field, populated
only from fields MEVA's tools already return (never fabricated). A claim
with `assertion="attribute"` names the item (`value`, e.g. `"Fish"`), the
field (`attribute`, e.g. `"criticality"`), and the claimed value
(`attribute_value`, e.g. `"low"`). The verifier looks up the matching
evidence item and its `attributes[attribute]`:

- Field present and matches → **SUPPORTED**
- Field present but doesn't match → **CONTRADICTED**
- Field not present in MEVA's evidence at all (e.g. a made-up field like
  `"severity"`) → **UNVERIFIABLE** — MEVA never guesses whether an
  unsupported field would have matched.

## Why MEVA does not guess unsupported attributes or categories

Two closely related rules, both deliberate:

1. If a claim asks about a metadata field MEVA's tools don't return
   (anything outside `criticality`/`clinical_status`/`status`/`intent`/`onset`),
   MEVA reports UNVERIFIABLE rather than trying to infer an answer from
   the item's name or other fields.
2. If a model mislabels a claim's `category` (e.g. tags an allergy claim
   as `category="patient"`), MEVA does **not** try to guess the intended
   category and re-route it. It verifies the claim exactly as labeled —
   which usually means UNVERIFIABLE or a failed match. This keeps a
   genuine model structured-output mistake visible as a real finding,
   instead of being silently "fixed" into a better-looking score.

## Structured claim validity

Beyond verification status, MEVA also tracks whether the model's raw
claim JSON was well-formed *before* any claims get silently dropped:

- `claim_schema_valid` — parses into a `MedicalClaim` at all
- `claim_category_valid` — `category` is one of MEVA's known categories
- `claim_value_present_when_required` — `value` is filled in for
  `present`/`value`/`attribute` assertions
- `claim_attribute_valid` — `attribute` and `attribute_value` are both
  set when `assertion="attribute"`

`structured_claim_validity_rate` = valid claims / total raw claims the
model produced (`None` if it made zero claims). A malformed claim is
still dropped from verification, never repaired — this rate exists to
make that failure mode visible and measurable, not to paper over it.

## The four verification statuses

- **SUPPORTED** — the claim matches retrieved evidence.
  _"Fish allergy recorded"_ + evidence contains Fish → SUPPORTED.

- **CONTRADICTED** — retrieved evidence directly conflicts with the claim.
  _"No allergies recorded"_ + evidence has 7 allergies → CONTRADICTED.

- **UNSUPPORTED** — the claim asserts something specific, but no
  retrieved evidence backs it up. _"Patient takes Aspirin"_ + evidence
  only shows Metformin → UNSUPPORTED. (Different from CONTRADICTED:
  MEVA isn't claiming Aspirin is impossible, just that there's no
  evidence for it.)

- **UNVERIFIABLE** — MEVA can't safely judge this with its current
  rules. This includes any `interpretation` claim (e.g. "this blood
  pressure is dangerous") — MEVA reports recorded facts, never clinical
  judgements, so those are always UNVERIFIABLE by design, not "checked
  and passed."

## Evidence Grounding Score

```text
verifiable_claims = supported + contradicted + unsupported
(UNVERIFIABLE claims are excluded entirely — they're neither counted for nor against)

grounding_score = supported / verifiable_claims, as a percentage
if verifiable_claims == 0: score = "N/A"
```

Example: 3 supported, 1 contradicted, 0 unsupported → 4 verifiable
claims → 75%.

**This is called an "Evidence Grounding Score," not a "clinical
accuracy," "medical safety," or "diagnostic accuracy" score.** MEVA has
not been clinically validated. It measures one narrow thing: how well
an AI's stated claims match the specific FHIR records MEVA retrieved —
nothing more.

## Limitations

- Normalization is intentionally conservative (casing, whitespace, and
  known Synthea display suffixes like `(substance)` only). It does not
  understand medical synonyms — "MI" vs "myocardial infarction" would
  not match.
- Verification only covers the categories and assertion types described
  above. Anything else (unrecognized category, absent-claims for
  patient demographics, etc.) is UNVERIFIABLE.
- The local 4B model sometimes needs a carefully worded final prompt to
  reliably fill in every claim field — MEVA validates and silently
  drops any malformed claim rather than crashing, but a dropped claim
  simply isn't verified at all (it won't appear as a false SUPPORTED).
- MEVA never verifies diagnosis, treatment, or prescription
  recommendations — an AI statement like "the patient should take X"
  is always unsupported/unverifiable and is never endorsed.
