"""MEVA MCP server.

Exposes MEVA's existing, read-only FHIR functions as MCP tools so an
MCP client (like Claude, or MCP Inspector) can look up synthetic
patient records. This file does no FHIR parsing itself — it only
calls the functions already built in `meva.fhir` and `meva.mcp.registry`.

All data is 100% synthetic (Synthea-generated). These tools retrieve
recorded FHIR evidence only. They do not diagnose, treat, prescribe,
or give medical advice of any kind.
"""

from mcp.server import MCPServer

from meva.fhir import blood_pressure_text
from meva.fhir import get_allergies as fhir_get_allergies
from meva.fhir import get_conditions as fhir_get_conditions
from meva.fhir import get_encounters as fhir_get_encounters
from meva.fhir import get_medications as fhir_get_medications
from meva.fhir import get_observations as fhir_get_observations
from meva.fhir import get_patient as fhir_get_patient
from meva.fhir import patient_name
from meva.mcp.registry import UnknownPatientError, get_resources_for_patient
from meva.mcp.registry import list_patients as registry_list_patients

mcp = MCPServer("MEVA")

MAX_LIMIT = 100
DEFAULT_LIMIT = 20


def _validate_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("limit must be a whole number")
    if limit < 1 or limit > MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    return limit


def _resources_for(patient_id: str) -> list[dict]:
    """Look up a patient's resources by ID, or raise a safe, clear error."""
    try:
        return get_resources_for_patient(patient_id)
    except UnknownPatientError as e:
        raise ValueError(str(e)) from None


@mcp.tool()
def list_patients() -> list[dict]:
    """List the synthetic patients available in MEVA.

    All patients are fictional, Synthea-generated data. No real patient
    data is included. Returns each patient's ID, name, and source file.
    """
    return registry_list_patients()


@mcp.tool()
def get_patient(patient_id: str) -> dict:
    """Get basic demographic info for one synthetic patient.

    Returns id, name, gender, and birth date, recorded exactly as found
    in the patient's synthetic FHIR record. This is retrieval only —
    no medical interpretation.
    """
    resources = _resources_for(patient_id)
    patient = fhir_get_patient(resources)
    if patient is None:
        raise ValueError(f"No Patient resource found for '{patient_id}'")

    return {
        "patient_id": patient.get("id"),
        "name": patient_name(patient),
        "gender": patient.get("gender"),
        "birth_date": patient.get("birthDate"),
    }


@mcp.tool()
def get_allergies(patient_id: str) -> list[dict]:
    """List recorded allergies for one synthetic patient.

    Returns the allergy name, criticality, and clinical status as
    recorded in the FHIR data. An empty list means no allergies are
    recorded for this patient — that is real, not missing, data.
    """
    resources = _resources_for(patient_id)
    return fhir_get_allergies(resources, patient_id)


@mcp.tool()
def get_medications(patient_id: str) -> list[dict]:
    """List recorded medication requests for one synthetic patient.

    Returns medication name, status, and intent as recorded in the FHIR
    data. This is a record of what was prescribed in the synthetic
    history, not a recommendation.
    """
    resources = _resources_for(patient_id)
    return fhir_get_medications(resources, patient_id)


@mcp.tool()
def get_conditions(patient_id: str) -> list[dict]:
    """List recorded conditions (diagnoses) for one synthetic patient.

    Returns the condition name, clinical status, and onset date as
    recorded in the FHIR data. This reports what was documented — it
    does not diagnose or interpret anything.
    """
    resources = _resources_for(patient_id)
    return fhir_get_conditions(resources, patient_id)


@mcp.tool()
def get_observations(patient_id: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """List recorded observations (vitals/labs) for one synthetic patient.

    `limit` caps how many observations are returned (default 20, max 100)
    so a caller cannot request unlimited output. Blood pressure readings
    include a combined systolic/diastolic string when present.
    """
    limit = _validate_limit(limit)
    resources = _resources_for(patient_id)
    observations = fhir_get_observations(resources, patient_id)

    for observation in observations:
        bp = blood_pressure_text(observation)
        if bp:
            observation["blood_pressure"] = bp

    return observations[:limit]


@mcp.tool()
def get_encounters(patient_id: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """List recorded encounters (visits) for one synthetic patient.

    `limit` caps how many encounters are returned (default 20, max 100).
    Returns encounter status, type, start, and end as recorded in the
    FHIR data.
    """
    limit = _validate_limit(limit)
    resources = _resources_for(patient_id)
    encounters = fhir_get_encounters(resources, patient_id)
    return encounters[:limit]


if __name__ == "__main__":
    mcp.run(transport="stdio")
