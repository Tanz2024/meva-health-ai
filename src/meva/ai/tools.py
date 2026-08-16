"""Expose MEVA's existing read-only functions as tools the local model can call.

This module does not implement any FHIR or patient-lookup logic itself.
It only describes the existing functions from meva.mcp.server (the same
functions the MCP server uses) so the local model knows they exist, and
provides a small, validated dispatcher to call them safely.
"""

from meva.mcp import server

# One schema per tool, in the standard function-calling format Ollama expects.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_patients",
            "description": "List the synthetic patients available in MEVA (id, name, source file).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_patient",
            "description": "Get basic demographic info (name, gender, birth date) for one synthetic patient.",
            "parameters": {
                "type": "object",
                "properties": {"patient_id": {"type": "string", "description": "The patient's FHIR ID"}},
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_allergies",
            "description": "List recorded allergies for one synthetic patient. Empty list means none recorded.",
            "parameters": {
                "type": "object",
                "properties": {"patient_id": {"type": "string", "description": "The patient's FHIR ID"}},
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_medications",
            "description": "List recorded medication requests for one synthetic patient.",
            "parameters": {
                "type": "object",
                "properties": {"patient_id": {"type": "string", "description": "The patient's FHIR ID"}},
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_conditions",
            "description": "List recorded conditions (diagnoses) for one synthetic patient.",
            "parameters": {
                "type": "object",
                "properties": {"patient_id": {"type": "string", "description": "The patient's FHIR ID"}},
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_observations",
            "description": "List recorded observations (vitals/labs) for one synthetic patient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string", "description": "The patient's FHIR ID"},
                    "limit": {"type": "integer", "description": "Max results, 1-100 (default 20)"},
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_encounters",
            "description": "List recorded encounters (visits) for one synthetic patient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string", "description": "The patient's FHIR ID"},
                    "limit": {"type": "integer", "description": "Max results, 1-100 (default 20)"},
                },
                "required": ["patient_id"],
            },
        },
    },
]

# Maps tool name -> the real MEVA function that already does the work.
_TOOL_FUNCTIONS = {
    "list_patients": server.list_patients,
    "get_patient": server.get_patient,
    "get_allergies": server.get_allergies,
    "get_medications": server.get_medications,
    "get_conditions": server.get_conditions,
    "get_observations": server.get_observations,
    "get_encounters": server.get_encounters,
}

_REQUIRED_ARGS = {
    "list_patients": [],
    "get_patient": ["patient_id"],
    "get_allergies": ["patient_id"],
    "get_medications": ["patient_id"],
    "get_conditions": ["patient_id"],
    "get_observations": ["patient_id"],
    "get_encounters": ["patient_id"],
}


def call_tool(name: str, arguments: dict) -> object:
    """Validate and run one MEVA tool call. Raises ValueError on any problem."""
    if name not in _TOOL_FUNCTIONS:
        raise ValueError(f"Unknown tool: '{name}'")

    arguments = arguments or {}
    missing = [arg for arg in _REQUIRED_ARGS[name] if arg not in arguments]
    if missing:
        raise ValueError(f"Tool '{name}' is missing required argument(s): {', '.join(missing)}")

    try:
        return _TOOL_FUNCTIONS[name](**arguments)
    except TypeError as e:
        raise ValueError(f"Tool '{name}' received invalid arguments: {e}") from None
