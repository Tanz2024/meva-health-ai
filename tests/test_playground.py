"""Stage 8B/8C — Playground service tests.

Fully offline — no AI model, no network. Confirms meva.playground.service
(shared by the Stage 8B CLI and the Stage 8C browser sandbox) exercises
MEVA's real, unmodified deterministic verifier against real v0.4 public
synthetic data, produces every verdict type correctly, and never calls
any model inference.
"""

import ast
import sys
from pathlib import Path

from meva.playground import (
    build_ready_made_examples,
    describe_patient,
    format_datetime_display,
    list_patients,
    observation_display_value,
    verify_claim,
)
from meva.playground.service import INVALID_PATIENT_ID_EXAMPLE

ALLERGY_PATIENT_ID = "c053e996-a4c4-6c02-e2b6-284227156c67"


# --- no model inference anywhere in the playground service -------------------

def test_playground_service_never_imports_ollama_or_extraction():
    source = (Path(__file__).resolve().parent.parent / "src" / "meva" / "playground" / "service.py").read_text()
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert not any("ollama" in m.lower() for m in imported_modules)
    assert not any("ai.agent" in m or "extraction" in m for m in imported_modules)


def test_cli_playground_never_imports_ollama_or_extraction():
    source = (Path(__file__).resolve().parent.parent / "examples" / "playground.py").read_text()
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert not any("ollama" in m.lower() for m in imported_modules)
    assert not any("ai.agent" in m or "extraction" in m for m in imported_modules)


# --- public patients ----------------------------------------------------

def test_list_patients_returns_all_21():
    patients = list_patients()
    assert len(patients) == 21
    assert all({"patient_id", "name", "file"} <= set(p) for p in patients)


def test_describe_patient_returns_read_only_counts():
    summary = describe_patient(ALLERGY_PATIENT_ID)
    assert summary["patient"]["patient_id"] == ALLERGY_PATIENT_ID
    assert summary["allergy_count"] >= 1
    assert isinstance(summary["medication_count"], int)


# --- four canonical verdicts ---------------------------------------------

def test_supported_example_uses_real_evidence():
    result = verify_claim(ALLERGY_PATIENT_ID, "allergy", "present", value="Peanut")
    assert result["status"] == "SUPPORTED"
    assert result["evidence"]
    assert result["evidence"][0]["source_tool"] == "get_allergies"
    assert result["evidence"][0]["resource_id"]  # real provenance, not fabricated


def test_contradicted_example_against_real_data():
    result = verify_claim(ALLERGY_PATIENT_ID, "allergy", "absent")
    assert result["status"] == "CONTRADICTED"
    assert len(result["evidence"]) >= 1


def test_unsupported_example_for_nonexistent_medication():
    result = verify_claim(ALLERGY_PATIENT_ID, "medication", "present", value="Zzznonexistentdrug")
    assert result["status"] == "UNSUPPORTED"
    assert result["evidence"] == []


def test_unverifiable_example_for_invalid_patient():
    result = verify_claim(INVALID_PATIENT_ID_EXAMPLE, "allergy", "absent")
    assert result["status"] == "UNVERIFIABLE"
    assert "not found" in result["reason"].lower()


# --- ready-made examples (Stage 8C item 16/17) --------------------------

def test_ready_made_examples_are_generated_from_live_fixtures_and_cover_all_verdicts():
    examples = build_ready_made_examples()
    assert len(examples) >= 4
    statuses = set()
    for example in examples:
        result = verify_claim(
            example["patient_id"], example["category"], example["assertion"],
            value=example["value"], attribute=example["attribute"], attribute_value=example["attribute_value"],
        )
        statuses.add(result["status"])
    assert statuses == {"SUPPORTED", "CONTRADICTED", "UNSUPPORTED", "UNVERIFIABLE"}


def test_ready_made_examples_include_an_observation_and_attribute_example():
    examples = build_ready_made_examples()
    assert any(e["category"] == "observation" for e in examples)
    assert any(e["assertion"] == "attribute" for e in examples)


def test_ready_made_examples_use_no_historical_removed_patient_ids():
    historical_ids = {
        "6895f047-ab31-c293-b335-374256e01eb1", "363f50e2-9771-dfb4-1ff5-3d7db24b9ada",
        "c28b00a3-54c0-21ba-4ed7-de871f1b157f",
    }
    examples = build_ready_made_examples()
    for example in examples:
        if example["patient_id"] == INVALID_PATIENT_ID_EXAMPLE:
            continue
        assert example["patient_id"] not in historical_ids


# --- observation presentation (Stage 8C item 10) -----------------------

def test_observation_display_value_prefers_blood_pressure_over_null_value():
    composite_observation = {"name": "Blood Pressure", "value": None, "blood_pressure": "128/81 mmHg"}
    assert observation_display_value(composite_observation) == "128/81 mmHg"


def test_observation_display_value_falls_back_to_plain_value():
    simple_observation = {"name": "Heart rate", "value": "72 /min", "blood_pressure": None}
    assert observation_display_value(simple_observation) == "72 /min"


# --- encounter timestamp normalization (presentation-only) -----------------

def test_format_datetime_display_normalizes_offset_to_utc():
    # +08:00 -> 07:33 UTC (matches the exact offset reported from the deployed sandbox)
    assert format_datetime_display("2023-07-29T15:33:11+08:00") == "2023-07-29 07:33 UTC"


def test_format_datetime_display_normalizes_different_offsets_consistently():
    # Two different raw offsets for the same instant must normalize to the same UTC display.
    a = format_datetime_display("2024-01-06T15:33:11+08:00")
    b = format_datetime_display("2024-01-06T14:33:11+07:00")
    assert a == b == "2024-01-06 07:33 UTC"


def test_format_datetime_display_handles_missing_value():
    assert format_datetime_display(None) == ""
    assert format_datetime_display("") == ""


def test_format_datetime_display_falls_back_on_unparseable_value():
    assert format_datetime_display("not-a-real-timestamp") == "not-a-real-timestamp"


def test_format_datetime_display_leaves_naive_datetime_unchanged():
    # No offset to normalize against -- shown as recorded rather than guessed.
    assert format_datetime_display("2024-01-06T15:33:11") == "2024-01-06T15:33:11"


# --- provenance -----------------------------------------------------------

def test_every_supported_result_carries_resource_provenance():
    result = verify_claim(ALLERGY_PATIENT_ID, "allergy", "present", value="Peanut")
    for evidence in result["evidence"]:
        assert evidence["source_tool"]
        assert evidence["resource_id"]


# --- uses the real verifier, not a reimplementation ------------------------

def test_playground_service_uses_meva_verification_build_report():
    from meva.playground import service

    assert service.build_report.__module__ == "meva.verification.verifier"


# --- CLI wrapper still works and delegates to the shared service -----------

def test_cli_run_demo_produces_all_four_verdicts(capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
    import playground as cli_playground

    results = cli_playground.run_demo()
    statuses = {r["status"] for r in results}
    assert statuses == {"SUPPORTED", "CONTRADICTED", "UNSUPPORTED", "UNVERIFIABLE"}
    capsys.readouterr()
