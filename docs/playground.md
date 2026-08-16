# MEVA Public Verifier Playground (Stage 8B)

`examples/playground.py` is a command-line demonstration of MEVA's
**deterministic evidence verifier** — no AI model, no inference, no
network. It exists to let anyone see exactly how MEVA turns a claim plus
real recorded data into a verdict, using only the public v0.4 synthetic
dataset.

## Architecture

```
you (CLI args) -> MedicalClaim -> meva.verification.verifier.build_report()
                                        |
                          real, on-disk FHIR data for one
                          public synthetic patient (v0.4)
                                        |
                          SUPPORTED / CONTRADICTED / UNSUPPORTED / UNVERIFIABLE
                          + evidence + reason
```

`build_report()` is the exact same function the benchmark engine and the
live agent use — the playground doesn't reimplement or simplify
verification logic. It only wraps it in a small, self-contained CLI:

- `list-patients` — every public synthetic patient available
- `describe-patient <id>` — read-only counts of that patient's recorded data
- `verify --patient-id ... --category ... --assertion ... --value ...` —
  run one claim through the real verifier
- `demo` — four canonical examples, one per verdict

No web server, no frontend framework, no database — a single Python
script over MEVA's existing library code.

## What it does NOT do

- **No AI model inference of any kind.** Not qwen3:4b, not llama3.2:3b, not
  any cloud model. The playground only demonstrates the deterministic
  verification step — you supply the claim yourself.
- **No claim extraction.** You state a claim directly with `--category`,
  `--assertion`, `--value` (etc.) — there's no "type a sentence and let a
  model turn it into a claim" step here (that's `meva.extraction`, a
  separate, AI-assisted component — see `docs/decoupled-evaluation.md`).
- **No diagnosis, no treatment advice.** The verifier only checks whether a
  stated claim matches recorded data — never whether that data means
  anything clinically.
- **No real patient data.** Every patient the playground can query is one
  of the 21 locally-generated, entirely fictional v0.4 patients (see
  `data/synthetic/synthea/PROVENANCE.md`).

## Public synthetic patients available

**21** — all of `data/synthetic/synthea/patient-01.json` through
`patient-21.json`, the same public v0.4 dataset used throughout Stage
8A.1. `list-patients` returns all of them; any of their `patient_id`s work
with `verify` and `describe-patient`.

## Supported categories

`patient`, `allergy`, `medication`, `condition`, `observation`, `encounter`
— the same `CLAIM_CATEGORIES` MEVA's verifier has always supported (see
`docs/evidence-verification.md`). Nothing new was added for the playground.

## Supported assertion types

`present`, `absent`, `value`, `attribute`, `interpretation` — the same
`CLAIM_ASSERTIONS` documented in `docs/claim-extraction-contract.md`.
`interpretation` claims are always UNVERIFIABLE by design; the playground
doesn't special-case this.

## Example results (from `python3 examples/playground.py demo`, real v0.4 data)

**SUPPORTED** — a real, recorded allergy stated as present:

```json
{
  "claim": {"category": "allergy", "value": "Peanut", "assertion": "present", "patient_id": "c053e996-..."},
  "status": "SUPPORTED",
  "reason": "Matching allergy evidence was found for 'Peanut'.",
  "evidence": [{"source_tool": "get_allergies", "resource_id": "c053e996-...-1c16-...", "value": "Peanut (substance)"}]
}
```

**CONTRADICTED** — claiming "no allergies" for a patient who genuinely has some:

```json
{
  "claim": {"category": "allergy", "assertion": "absent", "patient_id": "c053e996-..."},
  "status": "CONTRADICTED",
  "reason": "2 allergy record(s) were found, contradicting the 'absent' claim.",
  "evidence": [{"value": "Allergic disposition (finding)", ...}, {"value": "Peanut (substance)", ...}]
}
```

**UNSUPPORTED** — a specific claim that is simply not on the real record:

```json
{
  "claim": {"category": "medication", "value": "Zzznonexistentdrug", "assertion": "present", "patient_id": "c053e996-..."},
  "status": "UNSUPPORTED",
  "reason": "No medication evidence matching 'Zzznonexistentdrug' was found in the retrieved records.",
  "evidence": []
}
```

**UNVERIFIABLE** — an invalid/unknown `patient_id`:

```json
{
  "claim": {"category": "allergy", "assertion": "absent", "patient_id": "00000000-0000-0000-0000-000000000000"},
  "status": "UNVERIFIABLE",
  "reason": "The referenced patient was not found, so this claim cannot be verified.",
  "evidence": []
}
```

## Provenance in every result

Every `evidence` entry carries a `source_tool` (which MCP tool retrieved
it) and a `resource_id` (the exact FHIR resource it came from) — see the
SUPPORTED example above: `source_tool: "get_allergies"`,
`resource_id: "c053e996-4c6...-1c16-154b75fef1f0"`. Nothing is asserted
without a traceable source; see `docs/evidence-verification.md` for the
full provenance model.

## Invalid-patient behavior

An unknown `patient_id` is never silently treated as "this patient has no
data" — it always returns **UNVERIFIABLE**, with an explicit reason
("The referenced patient was not found..."). This distinction (unknown
patient vs. genuinely empty evidence) has been a core MEVA invariant since
Stage 5 — the playground doesn't change it.

## Shared service layer

Both the CLI above and the browser sandbox below call the same reusable
functions in `meva.playground.service` — `list_patients`,
`describe_patient`, `verify_claim`, `observation_display_value`, and
`build_ready_made_examples`. Neither reimplements or duplicates the
other's logic, and neither implements any verification rule of its own —
`verify_claim` calls `meva.verification.verifier.build_report()` directly,
unmodified.

# Browser Sandbox (Stage 8C)

`streamlit_app.py` is a local, browser-based UI over the exact same
service layer — still **deterministic verification only, no AI model, no
network calls**. It is not yet deployed publicly (see "Not yet: a public
URL" below).

## Local setup

```bash
pip install -e ".[playground]"
streamlit run streamlit_app.py
```

This installs Streamlit as an **optional** extra — a developer who only
needs FHIR/MCP/benchmarking/verification never needs Streamlit installed
(`pip install -e .` alone stays lightweight). Streamlit is declared under
`[project.optional-dependencies]` in `pyproject.toml`, never as a core
dependency (enforced by `scripts/release_check.py` and
`tests/test_streamlit_app.py`).

The app opens at `http://localhost:8501` by default.

## Screenshots

Not included yet — no screenshots have been captured for this stage. This
section will be updated once the browser sandbox has a first real (local)
run-through documented visually.

## How the claim builder works

1. **Select a synthetic patient** from a searchable dropdown (all 21
   public v0.4 patients — name, gender, birth date, and full patient ID
   shown; no filesystem paths).
2. **Inspect the patient summary and evidence explorer** — allergy,
   medication, condition, observation, and encounter tabs, each showing
   MEVA-normalized data with resource IDs. A "Developer" expander shows
   the full normalized JSON, hidden by default.
3. **Build a claim** — pick a Category and Assertion, then fill in Value
   (and Attribute/Attribute value, for attribute claims). The form
   validates the same combinations the verifier itself supports (e.g.
   `present`/`value`/`attribute` need a Value; `absent` doesn't) before
   ever calling the verifier — see `_validate_form` in `streamlit_app.py`.
4. **Press "Verify claim"** — this calls `meva.playground.verify_claim`
   directly, the same function the CLI uses. No LLM, no NLP extraction, no
   network request happens on this click.
5. **Read the result** — Status (SUPPORTED/CONTRADICTED/UNSUPPORTED/
   UNVERIFIABLE), the claim text, the reason, and an evidence table with
   source tool + evidence value + resource ID for every fact used.
6. **Try an example** — six ready-made scenarios, each *discovered live*
   from the current v0.4 fixtures via `build_ready_made_examples()` (never
   typed from memory), covering all four verdicts plus one observation and
   one attribute example. Clicking one populates the patient selector and
   claim form; you still press "Verify claim" yourself — the result is
   never a hardcoded value.

## Status meanings (shown in-app)

| Status | Meaning |
|---|---|
| SUPPORTED | Retrieved evidence supports the structured claim. |
| CONTRADICTED | Retrieved evidence directly conflicts with the structured claim. |
| UNSUPPORTED | MEVA found no retrieved evidence supporting that factual assertion. |
| UNVERIFIABLE | MEVA's current deterministic rules cannot safely evaluate the claim. |

These are shown as plain status text (never color-only) with a short
explanation, per accessibility requirements — see `STATUS_EXPLANATIONS` in
`streamlit_app.py`.

## Observation display (presentation only)

A composite observation (e.g. Blood Pressure) has a `null` top-level
`value` in the underlying tool data — the real combined reading only
exists in a separate `blood_pressure` key (documented in
`docs/observation-audit.md` §6). The browser sandbox's Observations tab
shows the meaningful reading via `observation_display_value()`, a small
presentation-only helper in `meva.playground.service`. **This does not
change `meva.mcp.server`, the FHIR layer, or the deterministic verifier in
any way** — it's purely how one table cell is rendered. A claim you build
from that value still goes through the same unmodified verifier as
everything else.

## Encounter timestamp display (presentation only)

Each encounter's raw `start`/`end` timestamp carries whatever UTC offset
Synthea generated for that specific record — this genuinely varies
record to record for the same patient (e.g. `+07:30` for one encounter,
`+08:00` for another), which looked inconsistent/"wrong" when shown raw
in a table. The Encounters tab normalizes every timestamp to UTC for
display via `format_datetime_display()`, another small presentation-only
helper in `meva.playground.service`. **This does not change
`meva.fhir.encounters`, `meva.mcp.server`, or any verified/benchmarked
value** — `get_encounters()` still returns the original, unmodified
ISO-8601 string with its original offset; only the table cell rendering
is normalized.

## Privacy / synthetic-data notice (shown in-app)

- All patient data displayed is synthetic (Synthea-generated, entirely
  fictional).
- The sandbox never requires real personal or medical information.
- Visitors are explicitly asked not to paste real patient information.
- Claim text entered is used only to compute the displayed result — it is
  not logged, stored, or transmitted anywhere. No analytics, tracking, or
  cookies are present.

## Limitations

- Local only — not yet deployed to any hosting provider.
- No screenshots yet (see above).
- The "Advanced: MedicalClaim JSON" view is read-only in this stage — it
  displays the constructed claim but does not accept free-form JSON input
  (avoiding the need to validate/sanitize arbitrary user JSON before a
  future public deployment).
- Six ready-made examples, not an exhaustive catalog of every claim shape
  MEVA supports.

## Not yet: a public URL

Stage 8C prepares the repository for a future Streamlit Community Cloud
deployment (`requirements.txt`, `.streamlit/config.toml`) but **does not
deploy it**. Public hosted sandbox: **coming after release** — no URL
exists yet, and none is guessed or reserved here.
