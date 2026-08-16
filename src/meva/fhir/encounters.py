"""Extract simple encounter (visit) information from FHIR resources."""

from meva.fhir.references import belongs_to_patient


def _encounter_type(resource: dict) -> str | None:
    types = resource.get("type", [])
    if not types:
        return None
    if types[0].get("text"):
        return types[0]["text"]
    coding = types[0].get("coding", [])
    return coding[0].get("display") if coding else None


def get_encounters(resources: list, patient_id: str | None = None) -> list[dict]:
    """Return simplified Encounter info, optionally filtered by patient ID."""
    encounters = []
    for resource in resources:
        if resource.get("resourceType") != "Encounter":
            continue
        if patient_id and not belongs_to_patient(resource, patient_id, reference_field="subject"):
            continue

        period = resource.get("period", {})
        encounters.append({
            "id": resource.get("id"),
            "status": resource.get("status"),
            "type": _encounter_type(resource),
            "start": period.get("start"),
            "end": period.get("end"),
        })

    return encounters
