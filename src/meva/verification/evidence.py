"""Build a structured evidence ledger from MEVA's real (existing) tool functions.

This is the only place that turns MEVA tool results into EvidenceFact
objects. It never invents data — every fact traces back to one actual
successful tool call. Tool errors (like "patient not found") are raised
as PatientNotFoundError and are never turned into evidence.
"""

from meva.fhir import blood_pressure_text
from meva.mcp import server as mcp_server
from meva.verification.models import EvidenceFact


class PatientNotFoundError(Exception):
    """Raised when a patient_id doesn't match any known synthetic patient.

    This is deliberately a different exception than "empty evidence" —
    an unknown patient must never be treated as "no allergies/medications/etc."
    """


class EvidenceLedger:
    """All evidence facts retrieved for one patient, grouped by category."""

    def __init__(self, patient_id: str):
        self.patient_id = patient_id
        self.facts: list[EvidenceFact] = []
        self._retrieved_categories: set[str] = set()

    def add(self, fact: EvidenceFact) -> None:
        self.facts.append(fact)

    def mark_retrieved(self, category: str) -> None:
        """Record that this category was successfully queried (even if the result was empty)."""
        self._retrieved_categories.add(category)

    def was_retrieved(self, category: str) -> bool:
        return category in self._retrieved_categories

    def facts_for(self, category: str) -> list[EvidenceFact]:
        return [f for f in self.facts if f.category == category]


def _short_id(resource_id: str | None, fallback: str) -> str:
    if resource_id:
        return resource_id.split("-")[0]
    return fallback


def _attributes(item: dict, fields: tuple[str, ...]) -> dict[str, str]:
    """Pull a fixed set of already-present, deterministic fields off a tool result item.

    Never invents a value: a field missing or None from the tool's own
    output is simply left out of the attributes dict.
    """
    return {field: str(item[field]) for field in fields if item.get(field) is not None}


def build_ledger(patient_id: str) -> EvidenceLedger:
    """Call MEVA's real tools for one patient and turn the results into an EvidenceLedger.

    Raises PatientNotFoundError if patient_id doesn't match a known patient.
    """
    try:
        patient = mcp_server.get_patient(patient_id)
    except ValueError as e:
        raise PatientNotFoundError(str(e)) from None

    ledger = EvidenceLedger(patient_id)

    for field, value in (("name", patient["name"]), ("gender", patient["gender"]), ("birth_date", patient["birth_date"])):
        if value is None:
            continue
        ledger.add(EvidenceFact(
            evidence_id=f"patient:{field}",
            patient_id=patient_id,
            category="patient",
            value=str(value),
            source_tool="get_patient",
            resource_id=field,
        ))
    ledger.mark_retrieved("patient")

    for allergy in mcp_server.get_allergies(patient_id):
        ledger.add(EvidenceFact(
            evidence_id=f"allergy:{_short_id(allergy['id'], allergy['name'])}",
            patient_id=patient_id,
            category="allergy",
            value=allergy["name"],
            source_tool="get_allergies",
            resource_id=allergy["id"],
            attributes=_attributes(allergy, ("criticality", "clinical_status")),
        ))
    ledger.mark_retrieved("allergy")

    for medication in mcp_server.get_medications(patient_id):
        ledger.add(EvidenceFact(
            evidence_id=f"medication:{_short_id(medication['id'], medication['name'])}",
            patient_id=patient_id,
            category="medication",
            value=medication["name"],
            source_tool="get_medications",
            resource_id=medication["id"],
            attributes=_attributes(medication, ("status", "intent")),
        ))
    ledger.mark_retrieved("medication")

    for condition in mcp_server.get_conditions(patient_id):
        ledger.add(EvidenceFact(
            evidence_id=f"condition:{_short_id(condition['id'], condition['name'])}",
            patient_id=patient_id,
            category="condition",
            value=condition["name"],
            source_tool="get_conditions",
            resource_id=condition["id"],
            attributes=_attributes(condition, ("clinical_status", "onset")),
        ))
    ledger.mark_retrieved("condition")

    for observation in mcp_server.get_observations(patient_id, limit=100):
        bp = blood_pressure_text(observation)
        value = f"{observation['name']}: {bp}" if bp else f"{observation['name']}: {observation['value']}"
        ledger.add(EvidenceFact(
            evidence_id=f"observation:{_short_id(observation['id'], observation['name'])}",
            patient_id=patient_id,
            category="observation",
            value=value,
            source_tool="get_observations",
            resource_id=observation["id"],
        ))
    ledger.mark_retrieved("observation")

    for encounter in mcp_server.get_encounters(patient_id, limit=100):
        value = f"{encounter['type']} ({encounter['status']}, {encounter['start']})"
        ledger.add(EvidenceFact(
            evidence_id=f"encounter:{_short_id(encounter['id'], encounter['status'])}",
            patient_id=patient_id,
            category="encounter",
            value=value,
            source_tool="get_encounters",
            resource_id=encounter["id"],
        ))
    ledger.mark_retrieved("encounter")

    return ledger
