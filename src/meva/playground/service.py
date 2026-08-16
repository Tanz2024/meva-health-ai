"""Reusable service functions behind MEVA's playgrounds (Stage 8B CLI, Stage 8C browser sandbox).

This module contains no verification rules of its own — every claim is
checked by the real, unmodified `meva.verification.verifier.build_report`.
It also contains no FHIR parsing of its own — all patient data comes from
the real MCP tool functions (`meva.mcp.server`), reading only the public
v0.4 synthetic fixtures in `data/synthetic/synthea/`.

Both `examples/playground.py` (CLI) and `streamlit_app.py` (browser) import
from here rather than duplicating this logic — see docs/playground.md.
"""

from meva.mcp import server as mcp_server
from meva.verification.models import CLAIM_ASSERTIONS, CLAIM_CATEGORIES, MedicalClaim
from meva.verification.verifier import build_report

RESOURCE_LOOKUPS = {
    "allergy": mcp_server.get_allergies,
    "medication": mcp_server.get_medications,
    "condition": mcp_server.get_conditions,
    "observation": mcp_server.get_observations,
}


def list_patients() -> list[dict]:
    """Every public synthetic patient available to a playground — the full v0.4 fixture set."""
    return mcp_server.list_patients()


def describe_patient(patient_id: str) -> dict:
    """A read-only summary of one public patient's recorded data — counts only,
    no diagnosis or interpretation, just what's on record and how many of each."""
    patient = mcp_server.get_patient(patient_id)
    return {
        "patient": patient,
        "allergy_count": len(mcp_server.get_allergies(patient_id)),
        "medication_count": len(mcp_server.get_medications(patient_id)),
        "condition_count": len(mcp_server.get_conditions(patient_id)),
        "observation_count": len(mcp_server.get_observations(patient_id)),
        "encounter_count": len(mcp_server.get_encounters(patient_id)),
    }


def observation_display_value(observation: dict) -> str:
    """Stage 8C presentation-only fix: composite (e.g. Blood Pressure) observations have a
    `null` top-level `value` with the real combined reading only in `blood_pressure` (see
    docs/observation-audit.md §6). This picks the meaningful value for DISPLAY ONLY — it does
    not touch meva.mcp.server or meva.verification, and does not change any benchmarked or
    verified behavior. A claim built from this value still goes through the unmodified
    verifier exactly as typed."""
    return observation.get("blood_pressure") or observation.get("value") or ""


def format_datetime_display(value: str | None) -> str:
    """Presentation-only fix: FHIR encounter start/end timestamps are stored with
    whatever UTC offset Synthea generated for that specific encounter (it varies
    record to record, e.g. some at +07:30, others at +08:00 for the same patient) —
    displaying them raw in a table makes the offsets look inconsistent/"wrong" even
    though each one is individually correct. This normalizes every timestamp to UTC
    for DISPLAY ONLY. It does not touch meva.fhir.encounters, meva.mcp.server, or
    any verified/benchmarked value — get_encounters() still returns the original,
    unmodified ISO-8601 string with its original offset.

    Falls back to the original raw string (never fabricates a time) if the value is
    missing or not parseable.
    """
    if not value:
        return ""
    try:
        from datetime import datetime, timezone
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return value  # no offset to normalize — show as recorded
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


# Stage 8F claim-builder guidance: example VALUE text shown as a placeholder/hint,
# derived from MEVA's own existing conventions (docs/claim-extraction-contract.md) —
# not tied to any specific patient, and never implying a "correct" answer for the
# currently selected patient.
CATEGORY_VALUE_HINTS: dict[str, str] = {
    "patient": "e.g. female",
    "allergy": "e.g. Peanut (substance)",
    "medication": "e.g. Amoxicillin 500 MG Oral Tablet",
    "condition": "e.g. Essential hypertension (disorder)",
    "observation": "e.g. Heart Rate: 72 /min",
    "encounter": "e.g. Encounter for problem (procedure)",
}


def suggested_values(patient_id: str, category: str, limit: int = 5) -> list[str]:
    """Real evidence values already visible in the sandbox's own Evidence Explorer
    for this patient/category — offered as optional, educational suggestions only.

    Never reveals anything beyond what RESOURCE_LOOKUPS[category] already returns
    (the same data the Evidence Explorer tab already displays), never implies a
    "correct" claim, and never leaks a hidden benchmark expectation — a visitor may
    still type any other value in the claim builder.
    """
    lookup = RESOURCE_LOOKUPS.get(category)
    if lookup is None:
        return []

    items = lookup(patient_id)
    if category == "observation":
        values = [observation_display_value(o) for o in items]
    else:
        values = [item.get("name") for item in items if item.get("name")]

    seen: set[str] = set()
    unique_values = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values[:limit]


def verify_claim(
    patient_id: str, category: str, assertion: str, value: str | None = None,
    attribute: str | None = None, attribute_value: str | None = None, text: str | None = None,
) -> dict:
    """Run one claim through MEVA's real, unmodified deterministic verifier.

    No AI model is involved anywhere in this call — this is the exact same
    meva.verification.verifier.build_report() used by the benchmark and the
    live agent, called directly with a claim built from your input.
    """
    claim = MedicalClaim(
        text=text or f"{assertion} claim about {category}" + (f": {value}" if value else ""),
        patient_id=patient_id, category=category, value=value, assertion=assertion,
        attribute=attribute, attribute_value=attribute_value,
    )
    report = build_report(claim.text, [claim])
    verification = report.claims[0]
    return {
        "claim": claim.model_dump(),
        "status": verification.status,
        "reason": verification.reason,
        "evidence": [e.model_dump() for e in verification.evidence],
    }


INVALID_PATIENT_ID_EXAMPLE = "00000000-0000-0000-0000-000000000000"


def build_ready_made_examples() -> list[dict]:
    """Discover concrete example claims from the CURRENT public v0.4 fixtures — never typed
    from memory (see docs/playground.md). Re-derives everything from live MCP tool calls, so
    an example always validates against whatever fixtures are actually on disk.

    Returns a list of {"label", "description", "patient_id", "category", "assertion",
    "value", "attribute", "attribute_value"} dicts — one per canonical scenario, plus one
    observation example and one attribute example when suitable data exists.
    """
    examples = []
    patients = list_patients()

    # SUPPORTED: first patient with a named (non-generic) allergy, asserted present.
    for p in patients:
        allergies = mcp_server.get_allergies(p["patient_id"])
        named = [a for a in allergies if a["name"] != "Allergic disposition (finding)"]
        if named:
            allergen = named[0]["name"].split(" (")[0]
            examples.append({
                "label": "SUPPORTED — a real recorded allergy",
                "description": f"{p['name']} has a recorded {allergen} allergy.",
                "patient_id": p["patient_id"], "category": "allergy", "assertion": "present",
                "value": allergen, "attribute": None, "attribute_value": None,
            })
            break

    # CONTRADICTED: a patient with allergies, claiming none are recorded.
    for p in patients:
        if mcp_server.get_allergies(p["patient_id"]):
            examples.append({
                "label": "CONTRADICTED — a false 'no allergies' claim",
                "description": f"{p['name']} actually has recorded allergies.",
                "patient_id": p["patient_id"], "category": "allergy", "assertion": "absent",
                "value": None, "attribute": None, "attribute_value": None,
            })
            break

    # UNSUPPORTED: any real patient, a clearly nonexistent medication.
    if patients:
        p = patients[0]
        examples.append({
            "label": "UNSUPPORTED — a medication not on record",
            "description": f"{p['name']} has no record of this medication.",
            "patient_id": p["patient_id"], "category": "medication", "assertion": "present",
            "value": "Zzznonexistentdrug", "attribute": None, "attribute_value": None,
        })

    # UNVERIFIABLE: an invalid/unknown patient_id.
    examples.append({
        "label": "UNVERIFIABLE — an unknown patient",
        "description": "This patient_id does not exist in MEVA's synthetic dataset.",
        "patient_id": INVALID_PATIENT_ID_EXAMPLE, "category": "allergy", "assertion": "absent",
        "value": None, "attribute": None, "attribute_value": None,
    })

    # Observation example: first patient with a Blood Pressure (composite) observation.
    for p in patients:
        for o in mcp_server.get_observations(p["patient_id"], limit=20):
            if o.get("blood_pressure"):
                examples.append({
                    "label": "SUPPORTED — an observation value",
                    "description": f"{p['name']}'s recorded blood pressure.",
                    "patient_id": p["patient_id"], "category": "observation", "assertion": "value",
                    "value": o["blood_pressure"], "attribute": None, "attribute_value": None,
                })
                break
        else:
            continue
        break

    # Attribute example: first patient with an allergy carrying criticality metadata.
    for p in patients:
        allergies = mcp_server.get_allergies(p["patient_id"])
        for a in allergies:
            if a.get("criticality") and a["name"] != "Allergic disposition (finding)":
                allergen = a["name"].split(" (")[0]
                examples.append({
                    "label": "SUPPORTED — an attribute claim",
                    "description": f"{p['name']}'s {allergen} allergy criticality.",
                    "patient_id": p["patient_id"], "category": "allergy", "assertion": "attribute",
                    "value": allergen, "attribute": "criticality", "attribute_value": a["criticality"],
                })
                break
        else:
            continue
        break

    return examples
