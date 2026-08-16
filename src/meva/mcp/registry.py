"""Find and load MEVA's approved synthetic patient bundles.

This is the only place that touches the filesystem for the MCP layer.
It never accepts a path or filename from a caller — callers only ever
pass a `patient_id` string, which is looked up against bundles we have
already discovered inside the approved data directory. This is what
prevents path traversal (e.g. "../../secret.json") or arbitrary
absolute paths from ever reaching the filesystem.
"""

from pathlib import Path

from meva.fhir import get_patient, load_bundle, patient_name

# The one and only folder MEVA's MCP server is allowed to read from.
DATA_DIR = (Path(__file__).resolve().parent.parent.parent.parent / "data" / "synthetic" / "synthea").resolve()


class UnknownPatientError(Exception):
    """Raised when a requested patient_id does not match any known bundle."""


def _approved_bundle_files() -> list[Path]:
    """List the synthetic patient bundle files inside the approved data directory only."""
    if not DATA_DIR.exists():
        return []

    files = []
    for path in sorted(DATA_DIR.glob("patient-*.json")):
        # Defensive check: make sure the resolved file is really inside DATA_DIR.
        if path.resolve().parent == DATA_DIR:
            files.append(path)
    return files


def _build_registry() -> dict[str, dict]:
    """Load every approved bundle once and index it by FHIR patient ID."""
    registry = {}
    for path in _approved_bundle_files():
        try:
            resources = load_bundle(str(path))
        except (ValueError, FileNotFoundError):
            # Skip any file that isn't a valid FHIR Bundle rather than crashing.
            continue

        patient = get_patient(resources)
        if patient is None or "id" not in patient:
            continue

        registry[patient["id"]] = {
            "file": path.name,
            "resources": resources,
            "patient": patient,
        }

    return registry


def list_patients() -> list[dict]:
    """Return {patient_id, name, file} for every approved synthetic patient."""
    registry = _build_registry()
    return [
        {
            "patient_id": patient_id,
            "name": patient_name(entry["patient"]),
            "file": entry["file"],
        }
        for patient_id, entry in registry.items()
    ]


def get_resources_for_patient(patient_id: str) -> list[dict]:
    """Return all FHIR resources for a known patient_id, or raise UnknownPatientError."""
    registry = _build_registry()
    entry = registry.get(patient_id)
    if entry is None:
        raise UnknownPatientError(f"No synthetic patient found with ID '{patient_id}'")
    return entry["resources"]
