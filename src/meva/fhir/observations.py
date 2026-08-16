"""Extract simple observation (measurement/result) information from FHIR resources.

Real-world FHIR Observations store their result in different ways depending
on the kind of measurement:
- valueQuantity        -> a single number + unit, e.g. height = 170 cm
- valueCodeableConcept  -> a coded answer, e.g. a yes/no or category result
- component             -> multiple sub-values, e.g. blood pressure has both
                           a systolic and a diastolic reading
"""

from meva.fhir.references import belongs_to_patient


def _observation_name(resource: dict) -> str:
    code = resource.get("code", {})
    if code.get("text"):
        return code["text"]
    coding = code.get("coding", [])
    if coding:
        return coding[0].get("display", "Unknown observation")
    return "Unknown observation"


def _component_name(component: dict) -> str:
    code = component.get("code", {})
    if code.get("text"):
        return code["text"]
    coding = code.get("coding", [])
    if coding:
        return coding[0].get("display", "Unknown component")
    return "Unknown component"


def _quantity_display(quantity: dict) -> str:
    value = quantity.get("value")
    unit = quantity.get("unit", "")
    return f"{value} {unit}".strip()


def _value_display(resource: dict) -> str | None:
    if "valueQuantity" in resource:
        return _quantity_display(resource["valueQuantity"])

    if "valueCodeableConcept" in resource:
        concept = resource["valueCodeableConcept"]
        if concept.get("text"):
            return concept["text"]
        coding = concept.get("coding", [])
        if coding:
            return coding[0].get("display")

    return None


def get_observations(resources: list, patient_id: str | None = None) -> list[dict]:
    """Return simplified Observation info, optionally filtered by patient ID.

    Each item has: id, name, value (or None), and components (a list, empty
    when the observation has no sub-values like blood pressure does).
    """
    observations = []
    for resource in resources:
        if resource.get("resourceType") != "Observation":
            continue
        if patient_id and not belongs_to_patient(resource, patient_id, reference_field="subject"):
            continue

        components = [
            {
                "name": _component_name(component),
                "value": _quantity_display(component["valueQuantity"]) if "valueQuantity" in component else None,
            }
            for component in resource.get("component", [])
        ]

        observations.append({
            "id": resource.get("id"),
            "name": _observation_name(resource),
            "value": _value_display(resource),
            "components": components,
        })

    return observations


def blood_pressure_text(observation: dict) -> str | None:
    """Given one observation dict from get_observations(), format 'systolic/diastolic mmHg'.

    Returns None if this observation isn't a blood pressure reading.
    """
    systolic = None
    diastolic = None

    for component in observation.get("components", []):
        name = component["name"].lower()
        if "systolic" in name:
            systolic = component["value"]
        elif "diastolic" in name:
            diastolic = component["value"]

    if systolic is None or diastolic is None:
        return None

    systolic_value = systolic.split(" ")[0]
    diastolic_value = diastolic.split(" ")[0]
    return f"{systolic_value}/{diastolic_value} mmHg"
