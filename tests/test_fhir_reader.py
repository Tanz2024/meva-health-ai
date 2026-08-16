"""Tests for the FHIR bundle reader (handmade example bundle)."""

from pathlib import Path

from meva.fhir import (
    blood_pressure_text,
    get_allergies,
    get_medications,
    get_observations,
    get_patient,
    load_bundle,
)

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "patient-001-fhir.json"


def test_bundle_loads_successfully():
    resources = load_bundle(str(DATA_FILE))
    assert len(resources) > 0


def test_patient_can_be_found():
    resources = load_bundle(str(DATA_FILE))
    patient = get_patient(resources)
    assert patient is not None
    assert patient["id"] == "patient-001"


def test_penicillin_allergy_can_be_found():
    resources = load_bundle(str(DATA_FILE))
    allergies = get_allergies(resources)
    allergy_names = [a["name"] for a in allergies]
    assert "Penicillin" in allergy_names


def test_metformin_medication_can_be_found():
    resources = load_bundle(str(DATA_FILE))
    medications = get_medications(resources)
    medication_names = [m["name"] for m in medications]
    assert "Metformin" in medication_names


def test_blood_pressure_observation_can_be_found():
    resources = load_bundle(str(DATA_FILE))
    observations = get_observations(resources)
    assert len(observations) == 1

    assert blood_pressure_text(observations[0]) == "128/82 mmHg"
