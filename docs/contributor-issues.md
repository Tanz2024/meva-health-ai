# Contributor starter issues

Some of these starter ideas have now been published as GitHub issues.
Check the live issue tracker first to avoid duplicate work:

https://github.com/Tanz2024/meva-health-ai/issues

The remaining items in this document are proposed contribution areas
that may be opened as issues later. See `docs/github-labels.md` for the
label set referenced below.

---

## A. Improve playground verification result cards

- **Difficulty:** good first issue
- **Labels:** `good first issue`, `playground`, `ui`
- **Problem:** The browser sandbox's result card (`streamlit_app.py`,
  "5. Result" section) could be visually clearer for a first-time visitor
  — e.g. better spacing, a clearer separation between the status banner
  and the evidence table, or a more scannable "Evidence used" table.
- **Expected output:** A visibly improved result card that still shows,
  unchanged: status (icon + colored alert box + text, never color alone),
  claim text, reason, evidence table (source tool, value, resource ID).
  No new AI logic, no change to `verify_claim()` or verifier semantics.
- **Likely files:** `streamlit_app.py` (the "5. Result" section, around
  `STATUS_DISPLAY`/`STATUS_EXPLANATIONS`).
- **Acceptance criteria:** All four statuses (SUPPORTED / CONTRADICTED /
  UNSUPPORTED / UNVERIFIABLE) still render correctly and distinctly; no
  status is communicated by color alone; existing `tests/test_streamlit_app.py`
  static-source checks still pass.
- **Tests/documentation expected:** No verifier logic changed, so no new
  `tests/test_verifier*.py` tests needed. If new session-state keys are
  introduced, add/adjust a static-source test in `tests/test_streamlit_app.py`
  confirming no forbidden imports were added.

---

## B. Improve category-specific claim-builder hints

- **Difficulty:** good first issue
- **Labels:** `good first issue`, `playground`, `documentation`
- **Problem:** `CATEGORY_VALUE_HINTS` in `src/meva/playground/service.py`
  gives one example per category. Some categories (e.g. `observation`)
  have several very different value shapes (a scalar reading like
  `Heart Rate: 72 /min` vs. a composite one like a blood pressure
  reading) that a single hint string can't fully convey.
- **Expected output:** Expanded or restructured hint text (still just
  presentation — a `dict[str, str]` or similar) that better represents
  the range of valid values per category, without ever implying a
  "correct" value for the currently selected patient.
- **Likely files:** `src/meva/playground/service.py` (`CATEGORY_VALUE_HINTS`),
  `streamlit_app.py` (wherever the hint is rendered), `examples/playground.py`
  if the CLI also gains hint text.
- **Acceptance criteria:** Every entry in `CLAIM_CATEGORIES` still has a
  hint; hints stay generic (not tied to one specific patient's data);
  `suggested_values()` behavior is unchanged.
- **Tests/documentation expected:** Update/extend `tests/test_playground.py`
  to assert every category in `CLAIM_CATEGORIES` has a non-empty hint.

---

## C. Add documentation example for creating a v0.4 benchmark case

- **Difficulty:** good first issue
- **Labels:** `good first issue`, `documentation`, `benchmark`
- **Problem:** `docs/benchmark-dataset.md` documents the case schema, but
  there's no fully worked, step-by-step example of adding one new case
  end to end (picking a patient, picking real evidence, writing the case
  JSON, validating it).
- **Expected output:** A new documented walkthrough (either a new file,
  e.g. `docs/adding-a-benchmark-case.md`, or a new section in
  `docs/benchmark-dataset.md`) showing the full process using one real,
  concrete synthetic patient from `data/synthetic/synthea/`.
- **Likely files:** `docs/benchmark-dataset.md` or a new `docs/*.md` file;
  references `examples/inspect_benchmark_data.py` and
  `meva.benchmark.validator.validate_dataset()`.
- **Acceptance criteria:** The walkthrough's example case is real and
  actually validates against real retrieved evidence (not fabricated);
  no benchmark data files are modified as part of this issue unless the
  worked example is also added as a real case (out of scope here — see
  issue G for adding new cases).
- **Tests/documentation expected:** Documentation only; no new tests
  required unless a real case is added (then see issue G's criteria).

---

## D. Add deterministic verifier edge-case tests

- **Difficulty:** good first issue
- **Labels:** `good first issue`, `testing`, `verifier`
- **Problem:** `src/meva/verification/verifier.py` is MEVA's core
  evidence-grounding logic. Edge cases (e.g. case-insensitive value
  matching boundaries, attribute claims with missing attribute metadata,
  multiple partially-matching evidence items) are valuable but not
  exhaustively covered.
- **Expected output:** New test(s) in `tests/test_verifier*.py` covering
  a specific, previously-uncovered edge case, with a clear assertion of
  expected status and reason.
- **Likely files:** `tests/test_verifier.py` or a new
  `tests/test_verifier_edge_cases.py`; read (do not modify)
  `src/meva/verification/verifier.py` and `src/meva/verification/models.py`
  first.
- **Acceptance criteria:** New test(s) pass against the *current*,
  unmodified verifier (this issue is about testing existing behavior, not
  changing it) unless the edge case reveals an actual bug — if so, that
  becomes a separate `bug`-labeled issue, not silently fixed here.
- **Tests/documentation expected:** The new test(s) themselves; no
  verifier code changes expected.

---

## E. Add FHIR Immunization resource support

- **Difficulty:** help wanted
- **Labels:** `help wanted`, `fhir`, `enhancement`
- **Problem:** MEVA currently supports allergy, medication, condition,
  observation, encounter, and patient resources. FHIR `Immunization`
  resources are not yet parsed, so claims about vaccinations can't be
  verified.
- **Expected output:** A new small parser module under `src/meva/fhir/`
  (following the existing pattern, e.g. `allergies.py`, `medications.py`),
  a corresponding `get_immunizations` MCP tool in `src/meva/mcp/server.py`,
  and `immunization` added to `CLAIM_CATEGORIES` if the verifier is to
  support claims about it.
- **Likely files:** `src/meva/fhir/immunizations.py` (new),
  `src/meva/mcp/server.py`, `src/meva/verification/models.py`
  (`CLAIM_CATEGORIES`), `src/meva/verification/verifier.py` (new category
  handling).
- **Acceptance criteria:** Immunization data present in the existing
  Synthea fixtures (`data/synthetic/synthea/`) parses correctly; a claim
  like "patient has an Influenza immunization on record" verifies
  correctly against real fixture data; existing categories/behavior
  unchanged.
- **Tests/documentation expected:** New tests in `tests/test_fhir_*.py`
  and `tests/test_verifier*.py`; update `docs/evidence-verification.md`
  and `docs/claim-extraction-contract.md` to document the new category.

---

## F. Add evidence explorer filtering/search

- **Difficulty:** help wanted
- **Labels:** `help wanted`, `playground`, `enhancement`
- **Problem:** The browser sandbox's Evidence Explorer tabs
  (allergy/medication/condition/observation/encounter) show all of a
  patient's records with no filtering — for patients with many
  observations this can be a long scroll.
- **Expected output:** A simple text-filter or search box per tab that
  narrows the displayed table by substring match on the visible columns,
  purely client-side/presentation — no change to what data is retrieved
  or how it's verified.
- **Likely files:** `streamlit_app.py` (Evidence Explorer tabs section).
- **Acceptance criteria:** Filtering only affects what's *displayed*; the
  underlying `RESOURCE_LOOKUPS`/MCP calls and any claim verification are
  unaffected; an empty filter shows all records exactly as before.
- **Tests/documentation expected:** A static-source test in
  `tests/test_streamlit_app.py` if new session-state or imports are
  introduced; no verifier or FHIR tests needed since no evidence logic
  changes.

---

## G. Add additional validated v0.4 synthetic benchmark cases

- **Difficulty:** help wanted
- **Labels:** `help wanted`, `benchmark`
- **Problem:** `benchmarks/v0.4/cases.json` has 53 cases. More cases
  (especially covering categories/assertions that are currently
  underrepresented) would make future model-comparison runs more robust.
- **Expected output:** New case(s) appended to `benchmarks/v0.4/cases.json`,
  each referencing only synthetic patients already in
  `data/synthetic/synthea/`, each validated against real retrieved
  evidence via `meva.benchmark.validator.validate_dataset()` before
  submission.
- **Likely files:** `benchmarks/v0.4/cases.json`; validate using
  `examples/inspect_benchmark_data.py`.
- **Acceptance criteria:** Every new case has a real `patient_id` from the
  existing public dataset, real `expected_evidence_facts` matching what
  the tools actually return, and passes `validate_dataset()`; no existing
  cases modified; no real/fabricated-as-real patient data introduced.
- **Tests/documentation expected:** `tests/test_benchmark_dataset*.py`
  (or equivalent) should still pass against the expanded file; mention
  the new case count in the relevant `docs/*.md` if it references "53
  cases."

---

## H. Normalize Blood Pressure tool output

- **Difficulty:** help wanted
- **Labels:** `help wanted`, `fhir`, `mcp`, `enhancement`
- **Problem:** The `get_observations` MCP tool output can expose
  `value=null` for composite observations (e.g. Blood Pressure), with the
  actual combined reading only present in a separate `blood_pressure`
  field. This was previously worked around at the *presentation* layer
  only (`observation_display_value()` in `src/meva/playground/service.py`,
  documented in `docs/observation-audit.md` §6) — the underlying tool
  output itself was never changed.
- **Expected output:** A considered fix at the MCP/FHIR layer itself (not
  just presentation) so `get_observations` returns a more consistently
  usable `value` for composite observations — **or**, if the maintainer
  decides the current two-field shape (`value` + `blood_pressure`) should
  stay for backward compatibility, clear documentation of why, plus
  keeping the existing presentation-only workaround. This issue is
  intentionally open on the *design* question — a PR should propose one
  approach and explain the tradeoff, not silently pick one.
- **Likely files:** `src/meva/fhir/observations.py`,
  `src/meva/mcp/server.py` (`get_observations`),
  `src/meva/playground/service.py` (`observation_display_value`, if it
  can be simplified/removed once the underlying data is fixed).
- **Acceptance criteria:** Whatever shape is chosen, it must not change
  any *verified* behavior for existing benchmark cases without those
  cases being re-validated; must not break `observation_display_value()`
  or any code currently depending on today's `value`/`blood_pressure`
  shape without updating all call sites; must be accompanied by a clear
  explanation of the chosen approach in the PR description.
- **Tests/documentation expected:** Update `tests/test_fhir_observations*.py`
  and any `tests/test_verifier*.py`/`tests/test_playground.py` tests that
  assert on today's shape; update `docs/observation-audit.md` to reflect
  the new state.
