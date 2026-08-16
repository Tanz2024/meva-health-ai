"""Tests for reading realistic Synthea-generated FHIR bundles."""

from pathlib import Path

import pytest

from meva.fhir import (
    blood_pressure_text,
    get_allergies,
    get_conditions,
    get_encounters,
    get_medications,
    get_observations,
    get_patient,
    load_bundle,
    patient_name,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "synthea"
# Stage 8A.1: repointed to patient-20.json (locally-generated public dataset — see
# data/synthetic/synthea/PROVENANCE.md), which has allergies, conditions, medications,
# observations, and encounters — needed since several tests below assert non-empty results.
PATIENT_FILE = DATA_DIR / "patient-20.json"


def test_synthea_bundle_loads():
    resources = load_bundle(str(PATIENT_FILE))
    assert len(resources) > 0


def test_patient_can_be_extracted():
    resources = load_bundle(str(PATIENT_FILE))
    patient = get_patient(resources)
    assert patient is not None
    assert patient_name(patient) != "Unknown"
    assert patient.get("gender") in ("male", "female")


def test_conditions_can_be_processed():
    resources = load_bundle(str(PATIENT_FILE))
    patient = get_patient(resources)
    conditions = get_conditions(resources, patient["id"])
    assert len(conditions) > 0
    assert all("name" in c for c in conditions)


def test_observations_can_be_processed():
    resources = load_bundle(str(PATIENT_FILE))
    patient = get_patient(resources)
    observations = get_observations(resources, patient["id"])
    assert len(observations) > 0
    assert all("name" in o for o in observations)


def test_encounters_can_be_processed():
    resources = load_bundle(str(PATIENT_FILE))
    patient = get_patient(resources)
    encounters = get_encounters(resources, patient["id"])
    assert len(encounters) > 0
    assert all(e["status"] for e in encounters)


def test_patient_references_are_handled():
    """Synthea uses 'urn:uuid:<id>' references, not 'Patient/<id>'."""
    resources = load_bundle(str(PATIENT_FILE))
    patient = get_patient(resources)

    all_conditions = get_conditions(resources)
    patient_conditions = get_conditions(resources, patient["id"])

    assert len(patient_conditions) > 0
    assert len(patient_conditions) == len(all_conditions)


def test_blood_pressure_components_are_handled():
    resources = load_bundle(str(PATIENT_FILE))
    patient = get_patient(resources)
    observations = get_observations(resources, patient["id"])

    bp_readings = [blood_pressure_text(o) for o in observations]
    bp_readings = [bp for bp in bp_readings if bp is not None]

    assert len(bp_readings) > 0
    assert "/" in bp_readings[0]
    assert "mmHg" in bp_readings[0]


def test_allergies_can_be_processed():
    resources = load_bundle(str(PATIENT_FILE))
    patient = get_patient(resources)
    allergies = get_allergies(resources, patient["id"])
    assert len(allergies) > 0
    assert all("name" in a for a in allergies)


def test_medications_can_be_processed():
    resources = load_bundle(str(PATIENT_FILE))
    patient = get_patient(resources)
    medications = get_medications(resources, patient["id"])
    assert len(medications) > 0
    assert all("name" in m for m in medications)


def test_malformed_bundle_is_rejected():
    resources = load_bundle(str(PATIENT_FILE))
    non_bundle = {"resourceType": "Patient", "id": "not-a-bundle"}

    import json
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(non_bundle, f)
        temp_path = f.name

    with pytest.raises(ValueError):
        load_bundle(temp_path)


def test_missing_file_is_rejected():
    with pytest.raises(FileNotFoundError):
        load_bundle("data/synthetic/synthea/does-not-exist.json")
