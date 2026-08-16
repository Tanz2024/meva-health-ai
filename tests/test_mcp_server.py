"""Tests for MEVA's MCP tool functions.

These call the underlying Python functions directly (the same functions
the @mcp.tool() decorator wraps) so tests run fully offline, without
needing a live MCP client or Inspector.
"""

import pytest

from meva.mcp import server
from meva.mcp.registry import DATA_DIR, _approved_bundle_files

# Stage 8A.1: repointed to the locally-generated public dataset (see
# data/synthetic/synthea/PROVENANCE.md).
# patient-20.json has allergies, conditions, medications, observations, encounters.
RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"
# patient-01.json has no allergies or medications (this generator run's patients all have
# at least one condition — see test_conditions_retrieval below for that specific case).
SPARSE_PATIENT_ID = "d15b23ed-02d5-3e28-efbd-2604425317c5"


def test_list_patients_works():
    patients = server.list_patients()
    assert len(patients) >= 3  # more synthetic patients may be added over time (see Stage 7B.5)
    ids = {p["patient_id"] for p in patients}
    assert RICH_PATIENT_ID in ids
    assert all({"patient_id", "name", "file"} <= set(p) for p in patients)


def test_valid_patient_lookup_works():
    patient = server.get_patient(RICH_PATIENT_ID)
    assert patient["patient_id"] == RICH_PATIENT_ID
    assert patient["name"]
    assert patient["gender"] in ("male", "female")


def test_invalid_patient_lookup_raises_clear_error():
    with pytest.raises(ValueError, match="does-not-exist"):
        server.get_patient("does-not-exist")


def test_allergies_retrieval():
    allergies = server.get_allergies(RICH_PATIENT_ID)
    assert len(allergies) > 0
    assert all("name" in a for a in allergies)

    # A patient can genuinely have none — must be an empty list, not fabricated data.
    assert server.get_allergies(SPARSE_PATIENT_ID) == []


def test_medications_retrieval():
    medications = server.get_medications(RICH_PATIENT_ID)
    assert len(medications) > 0
    assert server.get_medications(SPARSE_PATIENT_ID) == []


def test_conditions_retrieval():
    conditions = server.get_conditions(RICH_PATIENT_ID)
    assert len(conditions) > 0
    # SPARSE_PATIENT_ID genuinely has no allergies/medications, but (unlike the removed
    # historical fixture) does have one real recorded condition — verify it's returned
    # faithfully rather than fabricated or suppressed.
    sparse_conditions = server.get_conditions(SPARSE_PATIENT_ID)
    assert len(sparse_conditions) == 1
    assert all("name" in c for c in sparse_conditions)


def test_observations_retrieval():
    observations = server.get_observations(RICH_PATIENT_ID)
    assert len(observations) > 0
    assert all("name" in o for o in observations)


def test_encounters_retrieval():
    encounters = server.get_encounters(RICH_PATIENT_ID)
    assert len(encounters) > 0
    assert all("status" in e for e in encounters)


def test_observations_limit_is_applied():
    observations = server.get_observations(RICH_PATIENT_ID, limit=2)
    assert len(observations) == 2


def test_encounters_limit_is_applied():
    encounters = server.get_encounters(RICH_PATIENT_ID, limit=1)
    assert len(encounters) == 1


def test_limit_over_maximum_is_rejected():
    with pytest.raises(ValueError, match="between 1 and 100"):
        server.get_observations(RICH_PATIENT_ID, limit=1000)


def test_limit_below_minimum_is_rejected():
    with pytest.raises(ValueError, match="between 1 and 100"):
        server.get_encounters(RICH_PATIENT_ID, limit=0)


def test_only_approved_directory_files_are_ever_listed():
    """The registry must only ever look inside data/synthetic/synthea."""
    files = _approved_bundle_files()
    assert len(files) >= 3  # more synthetic patients may be added over time (see Stage 7B.5)
    for path in files:
        assert path.resolve().parent == DATA_DIR


def test_path_traversal_patient_id_is_rejected():
    """A patient_id is just a lookup key, never a filename — traversal strings simply don't match."""
    with pytest.raises(ValueError):
        server.get_patient("../../../../etc/passwd")


def test_arbitrary_filename_patient_id_is_rejected():
    with pytest.raises(ValueError):
        server.get_patient("patient-01.json")
