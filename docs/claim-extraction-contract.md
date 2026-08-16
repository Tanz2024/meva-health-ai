# MEVA Claim Extraction Contract

This document is the authoritative definition of how a natural-language
answer maps to MEVA's existing `MedicalClaim` schema (`meva.verification.models.MedicalClaim`).
Stage 7D2.1 exists because Stage 7D2 showed that JSON schema validity alone
does not guarantee this mapping is followed faithfully — this contract is
what the extraction prompt (`src/meva/extraction/prompt.py`) is built from,
and what `data/extraction/dev_fixtures.json` / `holdout_fixtures.json` test
against.

No new claim schema is introduced. Every field below already exists on
`MedicalClaim`.

## Fields

| Field | Meaning |
|---|---|
| `text` | A short human-readable restatement of the claim (not matched by the verifier or the fidelity evaluator — free text). |
| `patient_id` | Always the patient_id given to the extractor. Never invented, never a different patient. |
| `category` | One of `patient`, `allergy`, `medication`, `condition`, `observation`, `encounter`. |
| `value` | See per-assertion rules below — meaning depends on `assertion`. |
| `assertion` | One of `present`, `absent`, `value`, `attribute`, `interpretation`. |
| `attribute` / `attribute_value` | Only set when `assertion == "attribute"` — see below. |

## Assertion semantics

### `present` — a specific named item exists

Use when the answer states that a specific allergy/medication/condition/
encounter item is on record.

> "Fish allergy is recorded."

```json
{"category": "allergy", "assertion": "present", "value": "Fish"}
```

### `absent` — global (category-wide)

Use when the answer states that an ENTIRE category has no records — not
naming any specific item.

> "No allergies are recorded."

```json
{"category": "allergy", "assertion": "absent", "value": null}
```

`value` is `null` for a global absent claim — there is no specific item to
name.

### `absent` — item-specific

Use when the answer states a NAMED item is absent (the question asked about
a specific item, and the answer says it isn't there).

> "No Penicillin allergy is recorded."

```json
{"category": "allergy", "assertion": "absent", "value": "Penicillin"}
```

The distinguishing signal is whether the answer names a specific item. If it
does, `value` must be that item's name, even though the assertion is
`absent` — this is what separates item-specific absence from category-wide
absence, and is the single most common Stage 7D2 fidelity failure to avoid.

### `value` — a specific recorded value

Use for a concrete recorded value (typically an observation reading, or a
patient demographic value) — not "this item exists" but "this item's value
is exactly X."

> "Heart rate is 72 bpm."

```json
{"category": "observation", "assertion": "value", "value": "Heart Rate: 72 bpm"}
```

**Canonical value representation**: for an observation with a name and a
reading, `value` must be `"<Observation Name>: <reading with units>"` (e.g.
`"Heart Rate: 72 bpm"`, `"Body Temperature: 37.2 degrees Celsius"`) —
matching the format MEVA's own tool output uses (see
`meva.verification.evidence`), which is what the verifier's normalizer
compares against. For a blood pressure reading, use the systolic/diastolic
text exactly as stated (e.g. `"128/81 mmHg"`), optionally prefixed with
`"Blood Pressure: "`. For a patient demographic fact (e.g. gender, birth
date), `value` is just the stated value (e.g. `"female"`) with
`category="patient"`.

Do not use `assertion="present"` for a stated numeric/demographic value —
that is what `assertion="value"` is for. Do not use `assertion="value"` for
a named item's mere existence (e.g. an allergy) — that is what
`assertion="present"` is for.

### `attribute` — a metadata field of an already-identified item

Use when the answer states a property of an item that is itself identified
by `value` (which item), plus `attribute` (the field name) and
`attribute_value` (the claimed value of that field).

> "The Fish allergy has low criticality."

```json
{"category": "allergy", "assertion": "attribute", "value": "Fish", "attribute": "criticality", "attribute_value": "low"}
```

Known attribute fields (see `meva.verification.evidence`): allergy
`criticality`/`clinical_status`; medication `status`/`intent`; condition
`clinical_status`/`onset`. Use exactly these field names when the answer
states one of them; do not invent new attribute names.

### `interpretation` — an opinion/judgement, never verified

Use ONLY when the answer states an actual clinical judgement or opinion
(e.g. "this looks concerning") — MEVA's verifier always marks these
UNVERIFIABLE by design (see `docs/evidence-verification.md`). Do not convert
an objective, checkable fact into an `interpretation` just because it seems
easier — a claim that could be `present`/`absent`/`value`/`attribute` must
use that assertion, not `interpretation`.

## Multi-claim rule

One independently verifiable factual proposition becomes one `MedicalClaim`.
Do not collapse multiple facts into one vague claim, and do not split one
fact into multiple redundant claims.

> "Fish and Mold allergies are recorded."

→ two claims: `Fish present`, `Mold present`.

> "Fish allergy is active with low criticality."

→ up to three claims: `Fish present`, `Fish clinical_status=active`,
`Fish criticality=low` — each is independently checkable against evidence,
so each gets its own claim.

## Anti-repair rule (unchanged from Stage 7D1)

The extractor represents what the answer says, never what is actually true.

> "No blood pressure observation was found."

→ `{"category": "observation", "assertion": "absent", "value": "Blood Pressure"}`

— even when real FHIR evidence contains a recorded blood pressure. The
extractor never sees FHIR evidence (see "Anti-leakage," below) specifically
so it cannot "fix" a wrong answer. MEVA's unmodified deterministic verifier
is responsible for catching the resulting contradiction.

## Uncertainty policy

`MedicalClaim` has no field that represents "the answer hedged this
statement" — there is no uncertainty flag on the schema. Given that, the
policy is:

**An uncertain/hedged proposition ("may," "might," "possibly," "appears
to," "it's unclear whether...") produces ZERO claims for that proposition.**
It is never converted into a definite `present`/`absent`/`value`/`attribute`
claim. This is a deliberate limitation, not an oversight: representing
"maybe X" as "X" would let a hedge silently become a certain claim, and
representing it as a certain claim of the opposite (or of non-existence)
would be equally wrong. Zero-claims-for-that-proposition is the only
option that doesn't fabricate certainty the answer didn't have. A future
stage could add an explicit `certainty` field to `MedicalClaim` if this
limitation needs to be lifted — that is out of scope for Stage 7D2.1.

## Anti-leakage (unchanged from Stage 7D1)

The extractor's input is exactly `question`, `patient_id`, `answer_text` —
never FHIR data, `EvidenceFact` objects, MCP tool results, expected
benchmark evidence, expected verification status, or the source model's own
original structured claims. See `meva.extraction.extractor.ALLOWED_EXTRACTOR_INPUT_FIELDS`
and `tests/test_extraction_anti_leakage.py`.

## Deterministic post-extraction validation (not repair)

After the model returns claims, MEVA may **reject** a claim that doesn't
satisfy the schema (missing a required `value`, an `attribute` claim
missing `attribute`/`attribute_value`, an unrecognized `category`). This is
the only allowed post-processing:

**Allowed:** reject an invalid claim (drop it, count it as invalid).

**Not allowed:** guess a field's intended value, fill in a missing value,
infer an omitted claim, correct a category/assertion the model got wrong,
or consult FHIR evidence to "complete" a claim. See
`meva.extraction.extractor._claim_is_valid` — it only returns True/False, it
never mutates a claim.
