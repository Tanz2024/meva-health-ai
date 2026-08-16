"""Tests for the process-local registry cache in meva.mcp.registry.

Stage 8E2 CI-reliability fix: `_build_registry()` previously re-parsed every
patient's full FHIR bundle from disk on *every* call (list_patients(),
get_resources_for_patient()), which made scripts/release_check.py take
~23s (2,063 redundant json.load() calls across validate_dataset()'s 53
benchmark cases) — flaky against a 60s subprocess timeout under CI load.
`_cached_build_registry()` now caches the registry per resolved data
directory. These tests cover the caching contract itself: they must never
assert on wall-clock timing (flaky by nature) — instead they spy on
`load_bundle` to count real bundle parses.

Fully offline. No AI model, no network.
"""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from meva.mcp import registry

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_DATA_DIR = REPO_ROOT / "data" / "synthetic" / "synthea"
ALLERGY_PATIENT_ID = "c053e996-a4c4-6c02-e2b6-284227156c67"


def _copy_real_dataset(dest: Path, patient_files: list[str]) -> Path:
    """Build a small, VALID dataset (real copied bundles, so load_bundle()
    genuinely parses them) under dest/data/synthetic/synthea."""
    data_dir = dest / "data" / "synthetic" / "synthea"
    data_dir.mkdir(parents=True)
    shutil.copy(REAL_DATA_DIR / "manifest.json", data_dir / "manifest.json")
    for name in patient_files:
        shutil.copy(REAL_DATA_DIR / name, data_dir / name)
    return data_dir


@pytest.fixture(autouse=True)
def _clear_cache_around_test():
    """Every test starts and ends with a clean cache, so tests can't leak
    cached state into each other regardless of run order."""
    registry.clear_registry_cache()
    yield
    registry.clear_registry_cache()


# --- first build actually scans/parses fixtures -----------------------------

def test_first_registry_build_loads_and_parses_bundles():
    with patch("meva.mcp.registry.load_bundle", wraps=registry.load_bundle) as spy:
        result = registry._build_registry()
    assert len(result) == 21
    assert spy.call_count == 21  # one real parse per public patient bundle


# --- repeated calls reuse the cache, no re-parsing ---------------------------

def test_repeated_registry_calls_reuse_the_cache():
    registry._build_registry()  # warm the cache
    with patch("meva.mcp.registry.load_bundle", wraps=registry.load_bundle) as spy:
        registry._build_registry()
        registry._build_registry()
        registry.list_patients()
        registry.get_resources_for_patient(ALLERGY_PATIENT_ID)
    assert spy.call_count == 0  # nothing re-parsed


def test_list_patients_and_get_resources_share_one_cached_build():
    with patch("meva.mcp.registry.load_bundle", wraps=registry.load_bundle) as spy:
        registry.list_patients()
        registry.get_resources_for_patient(ALLERGY_PATIENT_ID)
    assert spy.call_count == 21  # built once, reused for the second call


# --- patient lookup results remain identical (behavior unchanged) -----------

def test_cached_results_match_uncached_results():
    uncached_patients = registry.list_patients()
    uncached_resources = registry.get_resources_for_patient(ALLERGY_PATIENT_ID)

    registry._build_registry()  # warm the cache
    cached_patients = registry.list_patients()
    cached_resources = registry.get_resources_for_patient(ALLERGY_PATIENT_ID)

    assert cached_patients == uncached_patients
    assert cached_resources == uncached_resources


def test_get_resources_returns_independent_list_objects_each_call():
    """Requirement: callers must not be able to corrupt the shared cache."""
    r1 = registry.get_resources_for_patient(ALLERGY_PATIENT_ID)
    r2 = registry.get_resources_for_patient(ALLERGY_PATIENT_ID)
    assert r1 == r2
    assert r1 is not r2  # different list objects
    r1.append({"resourceType": "Fake"})  # mutate the caller's copy
    r3 = registry.get_resources_for_patient(ALLERGY_PATIENT_ID)
    assert {"resourceType": "Fake"} not in r3  # cache untouched


# --- different resolved data directories never share a cache entry ---------

def test_different_data_dirs_do_not_share_cache(tmp_path, monkeypatch):
    dir_a = _copy_real_dataset(tmp_path / "a", ["patient-01.json", "patient-02.json"])
    dir_b = _copy_real_dataset(tmp_path / "b", ["patient-03.json"])

    monkeypatch.setattr(registry, "DATA_DIR", dir_a)
    patients_a = registry.list_patients()
    assert len(patients_a) == 2

    monkeypatch.setattr(registry, "DATA_DIR", dir_b)
    patients_b = registry.list_patients()
    assert len(patients_b) == 1

    # Switching back to dir_a must still return dir_a's patients, not dir_b's
    # (i.e. the cache didn't get corrupted/overwritten across directories),
    # and must be served from cache — not re-parsed a second time.
    monkeypatch.setattr(registry, "DATA_DIR", dir_a)
    with patch("meva.mcp.registry.load_bundle", wraps=registry.load_bundle) as spy:
        patients_a_again = registry.list_patients()
    assert patients_a_again == patients_a
    assert spy.call_count == 0


# --- clearing the cache forces a rebuild ------------------------------------

def test_clear_registry_cache_forces_rebuild():
    registry._build_registry()  # warm
    with patch("meva.mcp.registry.load_bundle", wraps=registry.load_bundle) as spy:
        registry._build_registry()
    assert spy.call_count == 0  # still cached

    registry.clear_registry_cache()
    with patch("meva.mcp.registry.load_bundle", wraps=registry.load_bundle) as spy:
        result = registry._build_registry()
    assert spy.call_count == 21  # rebuilt from scratch
    assert len(result) == 21


def test_clear_registry_cache_then_directory_change_picks_up_new_fixtures(tmp_path, monkeypatch):
    dir_a = _copy_real_dataset(tmp_path / "a", ["patient-01.json"])
    monkeypatch.setattr(registry, "DATA_DIR", dir_a)
    assert len(registry.list_patients()) == 1

    # Add a second patient file to the SAME directory after it was cached.
    shutil.copy(REAL_DATA_DIR / "patient-02.json", dir_a / "patient-02.json")
    registry.clear_registry_cache()
    assert len(registry.list_patients()) == 2


# --- path-traversal / security protections remain intact -------------------

def test_approved_bundle_files_still_only_reads_from_data_dir():
    files = registry._approved_bundle_files()
    for path in files:
        assert path.resolve().parent == registry.DATA_DIR


def test_unknown_patient_id_still_raises_after_caching():
    with pytest.raises(registry.UnknownPatientError):
        registry.get_resources_for_patient("not-a-real-patient-id")


def test_cache_key_is_the_data_dir_not_something_attacker_influenced():
    """The cache is keyed on the resolved Path object only — never on a
    patient_id, claim value, or any other caller-supplied string."""
    import inspect

    sig = inspect.signature(registry._cached_build_registry)
    assert list(sig.parameters) == ["data_dir"]
