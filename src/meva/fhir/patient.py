"""Extract simple patient information from a list of FHIR resources."""


def get_patient(resources: list) -> dict | None:
    """Return the first Patient resource found, or None."""
    for resource in resources:
        if resource.get("resourceType") == "Patient":
            return resource
    return None


def patient_name(patient: dict) -> str:
    """Build a readable full name from a Patient resource."""
    names = patient.get("name", [])
    if not names:
        return "Unknown"

    name = names[0]
    given = " ".join(name.get("given", []))
    family = name.get("family", "")
    return f"{given} {family}".strip() or "Unknown"
