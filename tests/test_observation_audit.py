"""Stage 7D2.2 — observation category sanity audit regression tests.

Confirms the findings in docs/observation-audit.md against MEVA's real,
deterministic FHIR/tool layer (no LLM, no Ollama): every v0.3 observation
case's expected evidence is genuinely present and within the default
retrieval limit, the Blood Pressure tool-output-shape quirk is documented
and stable, and the BP "absent" contradiction example is valid.

Stage 8A.1 note: v0.3's patients were removed from the public dataset
(unlicensed synthea-sample-data provenance — see
docs/historical-sample-data-provenance.md), so this module's live
re-verification against v0.3's specific cases is no longer possible. The
audit's conclusions remain valid and are permanently recorded in
docs/observation-audit.md; this module is skipped rather than silently
repointed to different patients, since it was specifically about proving
those exact historical cases were sound, not a generic behavior check
(generic absent/observation verifier behavior is covered in
tests/test_verification.py and tests/test_benchmark_validator.py against
the current public dataset).
"""

import json
from pathlib import Path

import pytest

from meva.mcp import server as mcp_server
from meva.verification.evidence import build_ledger
from meva.verification.models import MedicalClaim
from meva.verification.normalizer import values_match
from meva.verification.verifier import build_report

pytestmark = pytest.mark.skip(
    reason="v0.3's patients were removed in Stage 8A.1 (unlicensed synthea-sample-data "
    "provenance); this module's live re-verification is no longer possible for this "
    "historical dataset. See docs/observation-audit.md for the preserved findings."
)

CASES_PATH = Path(__file__).resolve().parent.parent / "benchmarks" / "v0.3" / "cases.json"


def _observation_cases():
    cases = json.loads(CASES_PATH.read_text())
    return [c for c in cases if c["category"] == "observation"]


# --- expected observation actually returned to the model (no truncation) ----

def test_all_observation_cases_expected_fact_within_default_limit():
    cases = _observation_cases()
    assert len(cases) == 10
    for case in cases:
        expected = case["expected_evidence_facts"][0]
        returned = mcp_server.get_observations(case["patient_id"], limit=20)
        returned_ids = {o["id"] for o in returned}
        assert expected["resource_id"] in returned_ids, (
            f"{case['case_id']}: expected resource_id not in the default-limit(20) result — "
            f"would indicate a genuine retrieval-truncation issue"
        )


def test_all_observation_cases_expected_value_matches_real_evidence():
    cases = _observation_cases()
    for case in cases:
        expected = case["expected_evidence_facts"][0]
        returned = mcp_server.get_observations(case["patient_id"], limit=20)
        match = next(o for o in returned if o["id"] == expected["resource_id"])
        actual_value = match.get("blood_pressure") or match["value"]
        assert values_match(expected["value"], actual_value), (
            f"{case['case_id']}: expected value '{expected['value']}' does not match "
            f"real tool output '{actual_value}'"
        )


# --- resource IDs traceable to the real synthetic FHIR bundle ----------------

def test_observation_resource_ids_traceable_via_evidence_ledger():
    cases = _observation_cases()
    for case in cases:
        expected = case["expected_evidence_facts"][0]
        ledger = build_ledger(case["patient_id"])
        facts = ledger.facts_for("observation")
        matching = [f for f in facts if f.resource_id == expected["resource_id"]]
        assert matching, f"{case['case_id']}: expected resource_id not found via build_ledger()"
        assert values_match(expected["value"], matching[0].value)


# --- documented Blood Pressure tool-output-shape quirk (not a scoring bug) --

def test_blood_pressure_top_level_value_is_null_documented_quirk():
    """Regression test for docs/observation-audit.md §6 — confirms the current
    (documented, unfixed) tool-output shape: composite BP observations have a
    null top-level 'value', with the real reading only in 'blood_pressure'."""
    cases = _observation_cases()
    bp_cases = [c for c in cases if c["expected_evidence_facts"][0]["value"].count("/") == 1
                and "mmHg" in c["expected_evidence_facts"][0]["value"]]
    assert len(bp_cases) == 4  # observation-01, 03, 05, 10

    for case in bp_cases:
        expected = case["expected_evidence_facts"][0]
        returned = mcp_server.get_observations(case["patient_id"], limit=20)
        match = next(o for o in returned if o["id"] == expected["resource_id"])
        assert match["value"] is None  # the documented ambiguity
        assert match["blood_pressure"] == expected["value"]  # but the data is genuinely present


def test_non_blood_pressure_observations_have_populated_top_level_value():
    """Contrast case for the BP quirk — every other vital type has a normal, populated
    top-level 'value' field, so the ambiguity is specific to composite (BP) observations."""
    cases = _observation_cases()
    non_bp_cases = [c for c in cases if not (
        c["expected_evidence_facts"][0]["value"].count("/") == 1 and "mmHg" in c["expected_evidence_facts"][0]["value"]
    )]
    assert len(non_bp_cases) == 6

    for case in non_bp_cases:
        expected = case["expected_evidence_facts"][0]
        returned = mcp_server.get_observations(case["patient_id"], limit=20)
        match = next(o for o in returned if o["id"] == expected["resource_id"])
        assert match["value"] is not None


# --- the BP "absent" contradiction example is valid --------------------------

def test_bp_absent_claim_correctly_contradicted_by_real_evidence():
    """The exact Stage 7D1/7D2 example: 'No blood pressure was found' when a real
    BP reading exists must be CONTRADICTED — confirms the verdict is not a scoring bug."""
    patient_id = "6895f047-ab31-c293-b335-374256e01eb1"  # observation-01
    claim = MedicalClaim(
        text="No blood pressure observations were found", patient_id=patient_id,
        category="observation", value="Blood Pressure", assertion="absent",
    )
    report = build_report("No blood pressure observations were found.", [claim])
    assert report.summary.contradicted == 1
    assert report.summary.supported == 0


def test_observation_absent_claim_is_category_wide_not_item_specific():
    """Documents existing (unchanged) verifier behavior: an 'absent' observation
    claim is checked against ALL observation facts for the patient, not specifically
    the named vital — see docs/observation-audit.md §7. Not a Stage 7D2.2 bug fix,
    just a regression test making the existing behavior explicit."""
    patient_id = "6895f047-ab31-c293-b335-374256e01eb1"
    # This patient has a Blood Pressure reading recorded, so even an "absent Heart Rate"
    # claim -- naming a DIFFERENT vital -- is still CONTRADICTED, because the current
    # verifier checks "any observation exists", not "this specific vital exists".
    claim = MedicalClaim(
        text="No heart rate was found", patient_id=patient_id,
        category="observation", value="Heart Rate", assertion="absent",
    )
    report = build_report("No heart rate was found.", [claim])
    assert report.summary.contradicted == 1
