"""Extract simple condition (diagnosis record) information from FHIR resources."""

from meva.fhir.references import belongs_to_patient


def _condition_name(resource: dict) -> str:
    code = resource.get("code", {})
    if code.get("text"):
        return code["text"]
    coding = code.get("coding", [])
    if coding:
        return coding[0].get("display", "Unknown condition")
    return "Unknown condition"


def _clinical_status(resource: dict) -> str | None:
    coding = resource.get("clinicalStatus", {}).get("coding", [])
    return coding[0].get("code") if coding else None


def get_conditions(resources: list, patient_id: str | None = None) -> list[dict]:
    """Return simplified Condition info, optionally filtered by patient ID."""
    conditions = []
    for resource in resources:
        if resource.get("resourceType") != "Condition":
            continue
        if patient_id and not belongs_to_patient(resource, patient_id, reference_field="subject"):
            continue

        conditions.append({
            "id": resource.get("id"),
            "name": _condition_name(resource),
            "clinical_status": _clinical_status(resource),
            "onset": resource.get("onsetDateTime"),
        })

    return conditions
