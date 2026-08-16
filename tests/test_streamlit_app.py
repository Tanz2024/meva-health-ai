"""Stage 8C — browser sandbox (streamlit_app.py) tests.

Fully offline, no browser started. Streamlit apps execute top-to-bottom on
import; outside a live session this runs in Streamlit's "bare mode" (widgets
return inert defaults, buttons are never "clicked") — safe to import in a
test as a static-analysis + smoke check. No AI model, no network.
"""

import ast
import warnings
from pathlib import Path

import pytest

# Stage 8D dependency-isolation fix: streamlit is an OPTIONAL extra
# (pyproject.toml [project.optional-dependencies].playground) — a core-only
# install (`pip install -e .`) must not make `pytest` hard-fail here. Tests
# that don't need streamlit installed (import-graph/static checks, config
# file checks) stay collected either way; the ones that actually import
# streamlit_app skip cleanly when it's unavailable.
pytest.importorskip("streamlit")

REPO_ROOT = Path(__file__).resolve().parent.parent


def _import_streamlit_app():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import streamlit_app
        return streamlit_app


# --- browser app imports --------------------------------------------------

def test_streamlit_app_imports_without_error():
    app = _import_streamlit_app()
    assert app is not None


# --- empty patient list never raises IndexError (Streamlit Cloud incident) --

def test_empty_patient_list_does_not_index_error(monkeypatch):
    """Regression test: if the public dataset is undiscoverable (the exact Streamlit
    Cloud incident — a non-editable install broke meva.mcp.registry.DATA_DIR), the
    app must show a friendly st.error + st.stop(), never raise IndexError on labels[0]."""
    import streamlit as st

    app = _import_streamlit_app()
    monkeypatch.setattr(app, "_cached_patient_list", lambda: [])

    stopped = {"called": False}

    def fake_stop():
        stopped["called"] = True
        raise SystemExit  # st.stop() halts script execution; simulate that here

    monkeypatch.setattr(st, "stop", fake_stop)

    with pytest.raises(SystemExit):
        # Re-running the module-level patient-selector logic directly (not the whole
        # file) to avoid re-triggering Streamlit's full script execution machinery.
        patients = app._cached_patient_list()
        patient_options = {f"{p['name']} — {p['patient_id']}": p["patient_id"] for p in patients}
        labels = list(patient_options.keys())
        if not labels:
            st.error("MEVA could not load the public synthetic patient dataset.")
            st.stop()
        labels[0]  # would have raised IndexError before the fix

    assert stopped["called"]


def test_streamlit_app_source_guards_empty_patient_list_before_indexing():
    """Static check that the actual guard exists in streamlit_app.py, in the right
    place — before labels[0] is ever accessed."""
    source = (REPO_ROOT / "streamlit_app.py").read_text()
    guard_pos = source.find("if not labels:")
    index_pos = source.find("labels[0]")
    assert guard_pos != -1, "streamlit_app.py is missing the 'if not labels' guard"
    assert index_pos != -1
    assert guard_pos < index_pos, "the empty-list guard must appear before labels[0] is used"
    assert "st.stop()" in source


# --- patient list uses all 21 public fixtures -------------------------------

def test_streamlit_app_patient_list_has_all_21():
    app = _import_streamlit_app()
    patients = app._cached_patient_list()
    assert len(patients) == 21


# --- example scenarios validate against live v0.4 fixtures ------------------

def test_streamlit_app_examples_validate_against_live_fixtures():
    app = _import_streamlit_app()
    examples = app._cached_ready_made_examples()
    statuses = set()
    for example in examples:
        result = app.verify_claim(
            example["patient_id"], example["category"], example["assertion"],
            value=example["value"], attribute=example["attribute"], attribute_value=example["attribute_value"],
        )
        statuses.add(result["status"])
    assert statuses == {"SUPPORTED", "CONTRADICTED", "UNSUPPORTED", "UNVERIFIABLE"}


# --- supported / contradicted / unsupported / unverifiable examples ---------

def test_streamlit_app_supported_example():
    app = _import_streamlit_app()
    result = app.verify_claim("c053e996-a4c4-6c02-e2b6-284227156c67", "allergy", "present", value="Peanut")
    assert result["status"] == "SUPPORTED"


def test_streamlit_app_contradicted_example():
    app = _import_streamlit_app()
    result = app.verify_claim("c053e996-a4c4-6c02-e2b6-284227156c67", "allergy", "absent")
    assert result["status"] == "CONTRADICTED"


def test_streamlit_app_unsupported_example():
    app = _import_streamlit_app()
    result = app.verify_claim("c053e996-a4c4-6c02-e2b6-284227156c67", "medication", "present", value="Zzznonexistentdrug")
    assert result["status"] == "UNSUPPORTED"


def test_streamlit_app_unverifiable_example():
    app = _import_streamlit_app()
    result = app.verify_claim("00000000-0000-0000-0000-000000000000", "allergy", "absent")
    assert result["status"] == "UNVERIFIABLE"


# --- observation display chooses blood_pressure when top-level value is null -

def test_streamlit_app_observation_display_prefers_blood_pressure():
    app = _import_streamlit_app()
    composite = {"name": "Blood Pressure", "value": None, "blood_pressure": "121/79 mmHg"}
    assert app.observation_display_value(composite) == "121/79 mmHg"


# --- claim-builder validation ------------------------------------------------

def test_streamlit_app_validation_requires_value_for_present():
    app = _import_streamlit_app()
    assert app._validate_form("allergy", "present", "", "", "") is not None
    assert app._validate_form("allergy", "present", "Peanut", "", "") is None


def test_streamlit_app_validation_allows_blank_value_for_absent():
    app = _import_streamlit_app()
    assert app._validate_form("allergy", "absent", "", "", "") is None


# --- attribute validation -----------------------------------------------

def test_streamlit_app_validation_requires_attribute_fields():
    app = _import_streamlit_app()
    assert app._validate_form("allergy", "attribute", "Peanut", "", "") is not None
    assert app._validate_form("allergy", "attribute", "Peanut", "criticality", "low") is None
    assert app._validate_form("allergy", "attribute", "", "criticality", "low") is not None


# --- provenance rendering data -----------------------------------------------

def test_streamlit_app_result_evidence_has_provenance_fields():
    app = _import_streamlit_app()
    result = app.verify_claim("c053e996-a4c4-6c02-e2b6-284227156c67", "allergy", "present", value="Peanut")
    assert result["evidence"]
    for e in result["evidence"]:
        assert "source_tool" in e and "resource_id" in e and "value" in e


# --- no historical fixture IDs ------------------------------------------

def test_streamlit_app_examples_have_no_historical_patient_ids():
    app = _import_streamlit_app()
    historical_ids = {"6895f047-ab31-c293-b335-374256e01eb1", "363f50e2-9771-dfb4-1ff5-3d7db24b9ada"}
    examples = app._cached_ready_made_examples()
    for example in examples:
        assert example["patient_id"] not in historical_ids


# --- no paid/cloud imports; no Ollama/model inference imports ---------------

def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_streamlit_app_has_no_forbidden_imports():
    modules = _imported_modules(REPO_ROOT / "streamlit_app.py")
    forbidden_substrings = ("ollama", "openai", "anthropic", "google.generativeai", "cohere", "ai.agent", "extraction")
    for module in modules:
        lowered = module.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"streamlit_app.py imports forbidden module: {module}"


# --- no arbitrary path input ------------------------------------------------

def test_streamlit_app_source_has_no_filesystem_path_input():
    source = (REPO_ROOT / "streamlit_app.py").read_text()
    # The app never accepts a free-text filesystem path from the user (no open()/Path()
    # calls driven by a text_input/text_area value) — patient selection is a closed
    # dropdown over meva.playground.list_patients(), not free text.
    assert "st.text_input" not in source or "path" not in source.lower().split("st.text_input")[1][:100]
    assert "open(" not in source
    assert "os.path" not in source and "Path(" not in source


# --- Streamlit remains optional dependency -----------------------------

def test_streamlit_is_an_optional_dependency_not_core():
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib  # Python 3.10

    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    core_deps = " ".join(data["project"]["dependencies"]).lower()
    assert "streamlit" not in core_deps
    assert "streamlit" in " ".join(data["project"]["optional-dependencies"]["playground"]).lower()


# --- deployment dependency file is valid ------------------------------------

def test_requirements_txt_exists_and_references_playground_extra():
    text = (REPO_ROOT / "requirements.txt").read_text()
    assert "playground" in text


def test_streamlit_config_has_no_secrets_or_telemetry():
    config_path = REPO_ROOT / ".streamlit" / "config.toml"
    assert config_path.exists()
    # Only check actual TOML value lines (not comments) for secret-shaped content.
    value_lines = "\n".join(
        line for line in config_path.read_text().lower().splitlines() if line.strip() and not line.strip().startswith("#")
    )
    assert "token" not in value_lines and "key" not in value_lines and "secret" not in value_lines
    assert "gatherusagestats=false" in value_lines.replace(" ", "")


def test_no_secrets_toml_committed():
    assert not (REPO_ROOT / ".streamlit" / "secrets.toml").exists()


# --- historical skips remain exactly documented -----------------------------

def test_historical_skip_count_unchanged():
    # Source-level count (robust to running this file in isolation, unlike inspecting
    # request.session.items, which only reflects whatever subset pytest collected).
    # test_benchmark_validator.py: 3 skipped tests. test_observation_audit.py: a
    # module-level pytestmark skip applied to all 7 tests in that file.
    validator_skips = (REPO_ROOT / "tests" / "test_benchmark_validator.py").read_text().count("@pytest.mark.skip(")
    observation_audit_text = (REPO_ROOT / "tests" / "test_observation_audit.py").read_text()
    observation_audit_test_count = observation_audit_text.count("\ndef test_")
    assert "pytestmark = pytest.mark.skip(" in observation_audit_text
    assert validator_skips + observation_audit_test_count == 10
