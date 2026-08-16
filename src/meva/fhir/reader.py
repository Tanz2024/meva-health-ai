"""Load a FHIR R4 Bundle JSON file and return its list of resources.

This module only handles loading. Extracting specific fields (like a
patient's name, or an observation's value) lives in the small helper
modules next to this file: patient.py, allergies.py, medications.py,
conditions.py, observations.py, encounters.py.
"""

import json
from pathlib import Path


def load_bundle(file_path: str) -> list:
    """Load a FHIR Bundle from a JSON file and return its list of resources."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"FHIR bundle file not found: {file_path}")

    with path.open("r", encoding="utf-8") as f:
        bundle = json.load(f)

    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        raise ValueError("File is not a FHIR Bundle (missing resourceType 'Bundle')")

    return [entry["resource"] for entry in bundle.get("entry", []) if "resource" in entry]
