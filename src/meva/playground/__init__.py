"""Shared service layer behind MEVA's playgrounds (CLI and browser sandbox).

No verification rules or FHIR parsing of its own — see service.py.
"""

from meva.playground.service import (
    INVALID_PATIENT_ID_EXAMPLE,
    build_ready_made_examples,
    describe_patient,
    list_patients,
    observation_display_value,
    verify_claim,
)

__all__ = [
    "list_patients",
    "describe_patient",
    "verify_claim",
    "observation_display_value",
    "build_ready_made_examples",
    "INVALID_PATIENT_ID_EXAMPLE",
]
