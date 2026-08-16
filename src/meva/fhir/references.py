"""Helpers for matching FHIR references like 'Patient/123' or 'urn:uuid:123'."""


def reference_id(reference: str | None) -> str | None:
    """Pull the plain ID out of a FHIR reference string.

    Handles both common forms Synthea and our own examples use:
    - "Patient/patient-001"      -> "patient-001"
    - "urn:uuid:6895f047-..."    -> "6895f047-..."
    """
    if not reference:
        return None

    if "/" in reference:
        return reference.split("/")[-1]

    if reference.startswith("urn:uuid:"):
        return reference[len("urn:uuid:"):]

    return reference


def belongs_to_patient(resource: dict, patient_id: str, reference_field: str = "subject") -> bool:
    """Check whether a resource's reference field points at the given patient ID."""
    reference = resource.get(reference_field, {}).get("reference")
    return reference_id(reference) == patient_id
