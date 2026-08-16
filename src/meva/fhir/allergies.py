"""Extract simple allergy information from a list of FHIR resources."""

from meva.fhir.references import belongs_to_patient


def _allergy_name(resource: dict) -> str:
    code = resource.get("code", {})
    if code.get("text"):
        return code["text"]
    coding = code.get("coding", [])
    if coding:
        return coding[0].get("display", "Unknown allergy")
    return "Unknown allergy"


def _clinical_status(resource: dict) -> str | None:
    coding = resource.get("clinicalStatus", {}).get("coding", [])
    return coding[0].get("code") if coding else None


def get_allergies(resources: list, patient_id: str | None = None) -> list[dict]:
    """Return simplified AllergyIntolerance info, optionally filtered by patient ID.

    AllergyIntolerance resources reference the patient through a "patient" field
    (not "subject"), so that's the field we check.
    """
    allergies = []
    for resource in resources:
        if resource.get("resourceType") != "AllergyIntolerance":
            continue
        if patient_id and not belongs_to_patient(resource, patient_id, reference_field="patient"):
            continue

        allergies.append({
            "id": resource.get("id"),
            "name": _allergy_name(resource),
            "criticality": resource.get("criticality"),
            "clinical_status": _clinical_status(resource),
        })

    return allergies
