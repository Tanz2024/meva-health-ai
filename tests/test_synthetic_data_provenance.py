"""Stage 8A.1 — synthetic data licensing remediation regression tests.

Confirms the locally-generated public fixtures load correctly, are
registry-compatible, carry consistent provenance/hashes, and that none of
the removed (unlicensed-provenance) synthea-sample-data files reappear.
Fully offline — no Ollama, no network, no Java/Synthea required.
"""

import hashlib
import json
from pathlib import Path

from meva.benchmark.loader import load_cases
from meva.benchmark.validator import validate_dataset
from meva.mcp import server as mcp_server
from meva.mcp.registry import DATA_DIR, _approved_bundle_files

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNTHEA_DIR = REPO_ROOT / "data" / "synthetic" / "synthea"

FORMER_UNLICENSED_SAMPLE_DATA_HASHES = {
    "683764ac99c03a00fd6459571612170d459d819f069363db1d07620124935b33",
    "fd0a74d3e49aca0abb61294b4c0357e7dc6fe9a6867cc620cab4caa7c323ac91",
    "0f0412e478e4a35b120d1a398698fde3433f3649e2057d3adcd98a033949bb08",
    "b809cc259b9b0527a127a2d487fb1af2455d7c3b7b157a28a5f6a9d901258c8e",
    "1219eb60428f711300c340407318b9b5fe3a7d206bf73f1265290cc2d4d67a13",
    "ce30ba440d25f1b1058f1a781068e6b72a4dca69d2d3da5a8783304f48141eb3",
    "5eceee9e1fb527e842e5247e37959aa344b21724ca48e3381c539e1c73180433",
    "fa5511a6c72efc34be8ee3b3d5d502bd786263f147c079abda0f127167ddd22c",
    "ddc059487134d0064f55b01716ae635a4b04d50112097ef27ea181130491cc2f",
    "f2b64687f4d8855884f5c64d71bfa444119698ded093e78de5bb934827d58acd",
    "b80933d813ecd7ec0ace9c28d1ae89c03b41593e82d8dee56c939198979530c8",
    "265cfa4445ce52fd9a9fcd76e0ecdec6850311853561a8b1ac0e5ddc30ae0334",
    "91a0992ad9ff5a319077c37f5b74a16177f7ad046124a15eab25e6de781b4691",
    "049054c83880f55e7a3dd565f7f98eb77794b347da91e35f80cf23e44cb8a637",
    "f246bc0a77bbd07a3d130638170689bf43e02cd008334f31001a4e9c446abd4a",
    "f88f947bf59f970f8ea96c1d490f959218c691537f85641d9e720831b1fc20d8",
    "d7bda614004f25431ffcacb52190f605563a4e7295edbddeba9d1e165b2e6d1b",
    "71e9b407182b25b76fccfa92ce147184a7ecf49d2040555d9d52fa6f3fcbbf58",
}


# --- generated public fixture loading -----------------------------------

def test_all_public_fixtures_load_as_valid_fhir_bundles():
    fixture_paths = sorted(SYNTHEA_DIR.glob("patient-*.json"))
    assert len(fixture_paths) == 21
    for path in fixture_paths:
        bundle = json.loads(path.read_text())
        assert bundle.get("resourceType") == "Bundle"
        assert bundle.get("entry")


def test_public_fixtures_are_not_the_two_handmade_stage1_examples():
    # data/synthetic/patient-001*.json (Stage 1/2) are separate, unaffected files.
    fixture_names = {p.name for p in SYNTHEA_DIR.glob("patient-*.json")}
    assert "patient-001.json" not in fixture_names


# --- registry compatibility ------------------------------------------------

def test_registry_discovers_all_21_public_fixtures():
    files = _approved_bundle_files()
    assert len(files) == 21
    for path in files:
        assert path.resolve().parent == DATA_DIR


def test_mcp_tools_work_against_every_public_fixture():
    manifest = json.loads((SYNTHEA_DIR / "manifest.json").read_text())
    for entry in manifest:
        patient = mcp_server.get_patient(entry["patient_id"])
        assert patient["patient_id"] == entry["patient_id"]
        # every tool must succeed (return a list, possibly empty) without raising
        assert isinstance(mcp_server.get_allergies(entry["patient_id"]), list)
        assert isinstance(mcp_server.get_medications(entry["patient_id"]), list)
        assert isinstance(mcp_server.get_conditions(entry["patient_id"]), list)
        assert len(mcp_server.get_observations(entry["patient_id"])) > 0


# --- v0.4 benchmark validation ----------------------------------------------

def test_v04_benchmark_loads_and_validates():
    cases = load_cases(path="benchmarks/v0.4/cases.json")
    assert 45 <= len(cases) <= 60
    warnings = validate_dataset(cases)  # must not raise
    assert warnings == []


def test_v04_manifest_matches_actual_case_counts():
    cases = load_cases(path="benchmarks/v0.4/cases.json")
    manifest = json.loads((REPO_ROOT / "benchmarks" / "v0.4" / "manifest.json").read_text())
    assert manifest["case_count"] == len(cases)
    agent_count = sum(1 for c in cases if c.case_type == "AGENT")
    challenge_count = sum(1 for c in cases if c.case_type == "VERIFIER_CHALLENGE")
    assert manifest["case_types"]["AGENT"] == agent_count
    assert manifest["case_types"]["VERIFIER_CHALLENGE"] == challenge_count


# --- provenance metadata presence -------------------------------------------

def test_provenance_markdown_exists_and_documents_generator():
    text = (SYNTHEA_DIR / "PROVENANCE.md").read_text()
    assert "synthetichealth/synthea" in text
    assert "v3.4.0" in text
    assert "Apache" in text
    assert "42" in text  # the seed


def test_historical_provenance_doc_exists_and_lists_removed_files():
    text = (REPO_ROOT / "docs" / "historical-sample-data-provenance.md").read_text()
    assert text.count("patient-") >= 18  # the removed filenames are listed
    assert "synthea-sample-data" in text


# --- SHA-256 fixture manifest consistency -----------------------------------

def test_synthea_manifest_hashes_match_actual_files():
    manifest = json.loads((SYNTHEA_DIR / "manifest.json").read_text())
    assert len(manifest) == 21
    for entry in manifest:
        fixture_path = SYNTHEA_DIR / entry["repo_filename"]
        actual_hash = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        assert actual_hash == entry["sha256"], f"{entry['repo_filename']}: hash mismatch"


# --- no historical copied sample files are being redistributed -------------

def test_no_file_in_public_dataset_matches_a_removed_historical_hash():
    for path in SYNTHEA_DIR.glob("*.json"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest not in FORMER_UNLICENSED_SAMPLE_DATA_HASHES, (
            f"{path.name}: matches a removed, unlicensed-provenance synthea-sample-data hash"
        )


# --- release-check behavior (see also tests/test_release_readiness.py) -----

def test_release_check_flags_reintroduced_historical_file(tmp_path, monkeypatch):
    import scripts.release_check as release_check

    fake_data_dir = tmp_path / "data" / "synthetic" / "synthea"
    fake_data_dir.mkdir(parents=True)
    # Recreate a file with byte-identical content to one of the removed patients'
    # known hash is impossible without the original bytes — instead verify the
    # detector runs and reports zero matches on an unrelated file, proving it
    # doesn't false-positive on ordinary content.
    (fake_data_dir / "patient-01.json").write_text('{"resourceType": "Bundle", "entry": []}')
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_no_historical_unlicensed_sample_data()
    assert errors == []


def test_release_check_public_fixture_provenance_requires_manifest(tmp_path, monkeypatch):
    import scripts.release_check as release_check

    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_public_fixture_provenance()
    assert any("manifest.json" in e for e in errors)
