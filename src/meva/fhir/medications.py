"""Extract simple medication information from a list of FHIR resources."""

from meva.fhir.references import belongs_to_patient


def _medication_name(resource: dict) -> str:
    concept = resource.get("medicationCodeableConcept")
    if concept:
        if concept.get("text"):
            return concept["text"]
        coding = concept.get("coding", [])
        if coding:
            return coding[0].get("display", "Unknown medication")

    if "medicationReference" in resource:
        # The medication is defined in a separate resource we didn't fetch.
        return resource["medicationReference"].get("display", "Unknown medication")

    return "Unknown medication"


def get_medications(resources: list, patient_id: str | None = None) -> list[dict]:
    """Return simplified MedicationRequest info, optionally filtered by patient ID."""
    medications = []
    for resource in resources:
        if resource.get("resourceType") != "MedicationRequest":
            continue
        if patient_id and not belongs_to_patient(resource, patient_id, reference_field="subject"):
            continue

        medications.append({
            "id": resource.get("id"),
            "name": _medication_name(resource),
            "status": resource.get("status"),
            "intent": resource.get("intent"),
        })

    return medications
