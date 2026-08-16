"""Stage 8G: Guided Mode support.

Translates plain-English, beginner-friendly claim choices into the exact
same MedicalClaim fields Advanced Mode uses (category/assertion/value) —
no new verifier semantics, no duplicated verification logic. Every option
returned here is safe to pass straight into
`meva.playground.service.verify_claim()`, the same function both Advanced
Mode and the CLI playground call.

Guided Mode never asserts what the "right" answer is — every suggested
claim, including the deliberately "not recorded" ones, is checked by the
real deterministic verifier, which decides SUPPORTED/CONTRADICTED/
UNSUPPORTED/UNVERIFIABLE on its own.
"""

from meva.mcp import server as mcp_server
from meva.playground.service import RESOURCE_LOOKUPS, observation_display_value

# Guided category -> (underlying MedicalClaim category, plain-English label).
GUIDED_CATEGORIES: list[tuple[str, str]] = [
    ("allergy", "Allergy"),
    ("medication", "Medication"),
    ("condition", "Condition"),
    ("observation", "Observation / Vital"),
    ("patient", "Patient information"),
]
GUIDED_CATEGORY_LABELS: dict[str, str] = dict(GUIDED_CATEGORIES)

# Plain-English question text per guided step (translates internal
# category/assertion/value terminology for a non-technical visitor).
GUIDED_CATEGORY_PROMPT = "What type of information do you want to check?"
GUIDED_CLAIM_PROMPT = "Choose a claim to check"
GUIDED_CUSTOM_LABELS = {
    "allergy": "Try another allergy",
    "medication": "Try another medication",
    "condition": "Try another condition",
    "observation": "Try another reading",
}

# Deliberately unlikely names used ONLY to build an honest "not recorded"
# suggestion — never asserted as true; the real deterministic verifier
# decides the actual result for whichever patient is selected.
_UNLIKELY_ALLERGY_NAMES = ["Latex", "Shellfish", "Pollen"]
_UNLIKELY_MEDICATION_NAMES = ["Zzznonexistentdrug", "Placebo Tablet"]
_UNLIKELY_CONDITION_NAMES = ["Zzznonexistent Syndrome", "Fictional Disorder"]
_UNLIKELY_OBSERVATION_READING = "999/999 mmHg"


def _first_unused(candidates: list[str], used: set[str]) -> str:
    for candidate in candidates:
        if candidate not in used:
            return candidate
    return candidates[0]


_PLURAL_NOUNS = {"allergy": "allergies", "medication": "medications", "condition": "conditions"}


def _guided_presence_options(patient_id: str, category: str, noun: str, unlikely_names: list[str]) -> list[dict]:
    """present/absent claims for allergy, medication, condition — the three
    categories the deterministic verifier calls "presence categories"."""
    lookup = RESOURCE_LOOKUPS[category]
    items = lookup(patient_id)
    real_names = [item["name"].split(" (")[0] for item in items if item.get("name")]

    options = []
    if real_names:
        recorded_name = real_names[0]
        options.append({
            "label": f"{recorded_name} {noun} is recorded",
            "assertion": "present", "value": recorded_name,
        })
    not_recorded_name = _first_unused(unlikely_names, set(real_names))
    options.append({
        "label": f"{not_recorded_name} {noun} is not recorded",
        "assertion": "present", "value": not_recorded_name,
    })
    options.append({
        "label": f"This patient has no recorded {_PLURAL_NOUNS[noun]}",
        "assertion": "absent", "value": None,
    })
    return options


def _guided_observation_options(patient_id: str) -> list[dict]:
    observations = RESOURCE_LOOKUPS["observation"](patient_id)
    options = []
    for observation in observations:
        display_value = observation_display_value(observation)
        if display_value:
            options.append({
                "label": f"The recorded {observation['name']} is {display_value}",
                "assertion": "value", "value": display_value,
            })
            break
    options.append({
        "label": f"This exact reading is not recorded: {_UNLIKELY_OBSERVATION_READING}",
        "assertion": "value", "value": _UNLIKELY_OBSERVATION_READING,
    })
    options.append({
        "label": "This patient has no recorded observations",
        "assertion": "absent", "value": None,
    })
    return options


def _guided_patient_options(patient_id: str) -> list[dict]:
    """Only deterministically-supported, non-sensitive demographic fields —
    the verifier's _verify_patient() only ever checks name/gender/birth date."""
    patient = mcp_server.get_patient(patient_id)
    options = []
    if patient.get("gender"):
        options.append({
            "label": f"Patient's gender is recorded as {patient['gender']}",
            "assertion": "present", "value": patient["gender"],
        })
    if patient.get("birth_date"):
        options.append({
            "label": f"Patient's birth date is recorded as {patient['birth_date']}",
            "assertion": "present", "value": patient["birth_date"],
        })
    return options


def guided_options(patient_id: str, category: str) -> list[dict]:
    """2-4 plain-English claim suggestions for one guided category, built from
    this patient's real, currently-visible synthetic evidence.

    Each item is {"label": str, "assertion": str, "value": str | None} — all
    valid `verify_claim()` input. Every combination here is one the
    deterministic verifier already supports (present/absent/value on
    allergy/medication/condition/observation, present/value on patient) —
    no new assertion type or category is introduced.
    """
    if category == "allergy":
        return _guided_presence_options(patient_id, "allergy", "allergy", _UNLIKELY_ALLERGY_NAMES)
    if category == "medication":
        return _guided_presence_options(patient_id, "medication", "medication", _UNLIKELY_MEDICATION_NAMES)
    if category == "condition":
        return _guided_presence_options(patient_id, "condition", "condition", _UNLIKELY_CONDITION_NAMES)
    if category == "observation":
        return _guided_observation_options(patient_id)
    if category == "patient":
        return _guided_patient_options(patient_id)
    return []


def guided_custom_claim(category: str, value: str) -> dict:
    """Translate a free-typed Guided Mode value into the same claim shape
    guided_options() produces — always assertion="present" for
    allergy/medication/condition (the verifier decides SUPPORTED/UNSUPPORTED
    either way) and assertion="value" for observation."""
    assertion = "value" if category == "observation" else "present"
    return {"label": value, "assertion": assertion, "value": value}


GUIDED_RESULT_EXPLANATIONS: dict[str, str] = {
    "SUPPORTED": "The recorded evidence supports this claim.",
    "CONTRADICTED": "The patient's recorded evidence conflicts with this claim.",
    "UNSUPPORTED": "MEVA did not find evidence supporting this claim.",
    "UNVERIFIABLE": "MEVA's current rules cannot safely check this claim.",
}
