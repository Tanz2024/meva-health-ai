"""Regression tests for deployment-safe synthetic-data-directory discovery
(meva.mcp.registry._resolve_data_dir) — the fix for the Streamlit Community
Cloud incident where a non-editable install broke __file__-relative
DATA_DIR arithmetic, and list_patients() silently returned [].

Fully offline. Never touches real Ollama/network. Never accepts a path from
"user input" — these tests only manipulate Path.cwd() and a fabricated
source-tree __file__ location, exactly the two trusted candidates
_resolve_data_dir() itself checks.
"""

import os
import shutil
from pathlib import Path

import pytest

from meva.mcp import registry

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_DATA_DIR = REPO_ROOT / "data" / "synthetic" / "synthea"


def _make_fake_dataset(base: Path, patient_count: int = 21) -> Path:
    """Build a minimal, valid-looking dataset directory (manifest.json + N
    patient-*.json files) under base/data/synthetic/synthea."""
    data_dir = base / "data" / "synthetic" / "synthea"
    data_dir.mkdir(parents=True)
    (data_dir / "manifest.json").write_text("[]")
    for i in range(1, patient_count + 1):
        (data_dir / f"patient-{i:02d}.json").write_text('{"resourceType": "Bundle", "entry": []}')
    return data_dir


# --- A. source/editable layout (the pre-existing, still-supported case) -----

def test_source_tree_candidate_still_resolves_in_real_repo():
    """The existing editable/dev layout must keep working exactly as before."""
    resolved = registry._resolve_data_dir()
    assert resolved == REAL_DATA_DIR
    assert resolved.exists()
    assert len(list(resolved.glob("patient-*.json"))) == 21


def test_is_valid_data_dir_accepts_real_dataset():
    assert registry._is_valid_data_dir(REAL_DATA_DIR) is True


# --- B. simulated installed-package layout: __file__-relative data absent, ---
# --- but Path.cwd()/data/synthetic/synthea has the fixtures -----------------

def test_cwd_candidate_discovers_fixtures_when_source_tree_candidate_is_absent(tmp_path, monkeypatch):
    """Simulates exactly the Streamlit Cloud incident: the __file__-derived
    source-tree candidate doesn't exist (as if installed non-editable into
    site-packages), but the process's cwd is a valid MEVA checkout."""
    _make_fake_dataset(tmp_path, patient_count=21)

    monkeypatch.setattr(registry, "_SOURCE_TREE_CANDIDATE", tmp_path / "nonexistent" / "data" / "synthetic" / "synthea")
    monkeypatch.chdir(tmp_path)

    resolved = registry._resolve_data_dir()
    assert resolved == (tmp_path / "data" / "synthetic" / "synthea").resolve()
    assert len(list(resolved.glob("patient-*.json"))) == 21


def test_cwd_candidate_is_tried_before_source_tree_candidate(tmp_path, monkeypatch):
    """Candidate A (cwd) must be checked first — both are made valid here, and the
    cwd one (containing 5 patients) must win over the source-tree one (containing 21)."""
    cwd_dataset = _make_fake_dataset(tmp_path / "cwd_repo", patient_count=5)
    source_tree_dataset = _make_fake_dataset(tmp_path / "src_repo", patient_count=21)

    monkeypatch.setattr(registry, "_SOURCE_TREE_CANDIDATE", source_tree_dataset)
    monkeypatch.chdir(tmp_path / "cwd_repo")

    resolved = registry._resolve_data_dir()
    assert resolved == cwd_dataset.resolve()
    assert len(list(resolved.glob("patient-*.json"))) == 5


# --- invalid cwd with no dataset returns a clean, empty (not crashing) result

def test_no_valid_candidate_falls_back_cleanly_without_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_SOURCE_TREE_CANDIDATE", tmp_path / "nonexistent-a")
    monkeypatch.chdir(tmp_path)  # tmp_path/data/synthetic/synthea also doesn't exist

    resolved = registry._resolve_data_dir()
    assert isinstance(resolved, Path)
    assert not resolved.exists()


def test_approved_bundle_files_returns_empty_list_not_exception_for_missing_dir(monkeypatch):
    monkeypatch.setattr(registry, "DATA_DIR", Path("/definitely/does/not/exist/anywhere"))
    assert registry._approved_bundle_files() == []


def test_list_patients_returns_empty_list_when_dataset_undiscoverable(monkeypatch):
    monkeypatch.setattr(registry, "DATA_DIR", Path("/definitely/does/not/exist/anywhere"))
    assert registry.list_patients() == []


# --- a directory that exists but ISN'T the real dataset must be rejected ----

def test_directory_without_manifest_is_rejected(tmp_path):
    fake = tmp_path / "data" / "synthetic" / "synthea"
    fake.mkdir(parents=True)
    (fake / "patient-01.json").write_text("{}")
    # no manifest.json
    assert registry._is_valid_data_dir(fake) is False


def test_directory_without_patient_files_is_rejected(tmp_path):
    fake = tmp_path / "data" / "synthetic" / "synthea"
    fake.mkdir(parents=True)
    (fake / "manifest.json").write_text("[]")
    # no patient-*.json files
    assert registry._is_valid_data_dir(fake) is False


# --- security: path traversal / only patient-*.json files are ever read -----

def test_path_traversal_protections_still_pass_with_new_resolver():
    """Existing path-traversal/patient_id-is-not-a-filename invariants are unaffected
    by the resolver change — see also tests/test_mcp_server.py for the full suite."""
    from meva.mcp import server

    with pytest.raises(ValueError):
        server.get_patient("../../../../etc/passwd")
    with pytest.raises(ValueError):
        server.get_patient("patient-01.json")


def test_only_patient_star_json_files_are_read_from_data_dir():
    """A non-patient file sitting in the real DATA_DIR (e.g. manifest.json,
    PROVENANCE.md) must never be treated as a patient bundle."""
    files = registry._approved_bundle_files()
    assert all(f.name.startswith("patient-") and f.name.endswith(".json") for f in files)
    assert not any(f.name in ("manifest.json", "PROVENANCE.md") for f in files)


def test_resolver_never_accepts_a_path_argument():
    """_resolve_data_dir takes no parameters at all — there is no code path by which
    a caller (web user, query param, claim, patient_id) could influence which
    directory gets selected."""
    import inspect
    sig = inspect.signature(registry._resolve_data_dir)
    assert len(sig.parameters) == 0
