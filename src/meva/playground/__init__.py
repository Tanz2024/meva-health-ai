"""Shared service layer behind MEVA's playgrounds (CLI and browser sandbox).

No verification rules or FHIR parsing of its own — see service.py.
"""

from meva.playground.guided import (
    GUIDED_CATEGORIES,
    GUIDED_CATEGORY_LABELS,
    GUIDED_CUSTOM_LABELS,
    GUIDED_RESULT_EXPLANATIONS,
    guided_custom_claim,
    guided_options,
)
from meva.playground.service import (
    CATEGORY_VALUE_HINTS,
    INVALID_PATIENT_ID_EXAMPLE,
    build_ready_made_examples,
    describe_patient,
    format_datetime_display,
    list_patients,
    observation_display_value,
    suggested_values,
    verify_claim,
)

__all__ = [
    "list_patients",
    "describe_patient",
    "verify_claim",
    "observation_display_value",
    "format_datetime_display",
    "build_ready_made_examples",
    "suggested_values",
    "CATEGORY_VALUE_HINTS",
    "INVALID_PATIENT_ID_EXAMPLE",
    "GUIDED_CATEGORIES",
    "GUIDED_CATEGORY_LABELS",
    "GUIDED_CUSTOM_LABELS",
    "GUIDED_RESULT_EXPLANATIONS",
    "guided_options",
    "guided_custom_claim",
]
