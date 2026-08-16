"""Read synthetic patient data from a JSON file."""

import json
from pathlib import Path


def load_patient(file_path: str) -> dict:
    """Load a patient record from a JSON file and return it as a dictionary."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Patient file not found: {file_path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data
