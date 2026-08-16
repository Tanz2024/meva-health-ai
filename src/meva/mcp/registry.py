"""Find and load MEVA's approved synthetic patient bundles.

This is the only place that touches the filesystem for the MCP layer.
It never accepts a path or filename from a caller — callers only ever
pass a `patient_id` string, which is looked up against bundles we have
already discovered inside the approved data directory. This is what
prevents path traversal (e.g. "../../secret.json") or arbitrary
absolute paths from ever reaching the filesystem.

Data directory discovery (`_resolve_data_dir`) checks only a small, fixed
set of trusted candidate locations — never a path from a web user, query
parameter, claim, or patient_id. See docs/publishing-checklist.md /
CHANGELOG.md for the deployment incident (Streamlit Community Cloud) that
made this necessary: a single `Path(__file__)`-relative guess broke across
editable vs. non-editable installs and different hosting layouts.
"""

import logging
from pathlib import Path

from meva.fhir import get_patient, load_bundle, patient_name

logger = logging.getLogger(__name__)

_RELATIVE_DATA_PATH = Path("data") / "synthetic" / "synthea"

# Source-tree location derived from this file's own path — correct only when
# meva is running from an editable install / directly from the cloned repo's
# src/ tree (four parents up from src/meva/mcp/registry.py -> repo root).
_SOURCE_TREE_CANDIDATE = (Path(__file__).resolve().parent.parent.parent.parent / _RELATIVE_DATA_PATH)


def _is_valid_data_dir(candidate: Path) -> bool:
    """A candidate is trusted only if it exists AND looks like the real public
    dataset (has manifest.json and at least one patient-*.json) — not just any
    existing directory that happens to be named right."""
    if not candidate.is_dir():
        return False
    if not (candidate / "manifest.json").is_file():
        return False
    return any(candidate.glob("patient-*.json"))


def _resolve_data_dir() -> Path:
    """Pick the public synthetic-data directory from a small, fixed list of
    trusted candidates — never from user input, a query parameter, or a claim.

    Candidate order:
      A. Path.cwd() / data/synthetic/synthea — how Streamlit Community Cloud
         (and any tool that launches from the repository root) actually runs
         this app; `Path(__file__)` arithmetic doesn't help there because a
         non-editable install copies package files into site-packages.
      B. The source-tree path derived from this file's own location — correct
         for an editable install / running directly from a repo checkout.

    Returns the first candidate that passes `_is_valid_data_dir`. If neither
    does, returns candidate B (unresolved) so callers still get a stable,
    loggable Path — `_approved_bundle_files()` already handles a
    non-existent/empty directory by returning no patients, never by guessing.
    """
    candidates = [
        ("cwd", (Path.cwd() / _RELATIVE_DATA_PATH).resolve()),
        ("source-tree", _SOURCE_TREE_CANDIDATE.resolve()),
    ]

    for label, candidate in candidates:
        if _is_valid_data_dir(candidate):
            patient_count = len(list(candidate.glob("patient-*.json")))
            logger.info(
                "meva.mcp.registry: using %s candidate for DATA_DIR (exists=True, patient_files=%d)",
                label, patient_count,
            )
            return candidate

    # Nothing validated — log which candidates were tried (paths only, no secrets/env
    # vars/patient content) so a deployment failure is diagnosable from server logs,
    # then fall back to the source-tree candidate for a stable, non-guessing default.
    fallback = candidates[-1][1]
    for label, candidate in candidates:
        logger.warning(
            "meva.mcp.registry: candidate '%s' rejected for DATA_DIR (exists=%s)",
            label, candidate.exists(),
        )
    logger.warning("meva.mcp.registry: no valid data directory found; falling back to %s (0 patients expected)", fallback)
    return fallback


# The one and only folder MEVA's MCP server is allowed to read from.
DATA_DIR = _resolve_data_dir()


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
