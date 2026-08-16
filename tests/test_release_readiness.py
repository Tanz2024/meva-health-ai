"""Stage 8A — public release readiness regression tests. Fully offline."""

import subprocess
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # Python 3.10

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PUBLIC_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "ROADMAP.md",
    "CHANGELOG.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CITATION.cff",
    "pyproject.toml",
    ".gitignore",
]

DOC_FILES_REFERENCED_BY_README = [
    "docs/safety-and-scope.md",
    "docs/synthetic-data.md",
    "docs/mcp-server.md",
    "docs/local-ai.md",
    "docs/evidence-verification.md",
    "docs/reproducibility.md",
    "docs/benchmarking.md",
    "docs/benchmark-dataset.md",
    "docs/model-comparison.md",
    "docs/decoupled-evaluation.md",
    "docs/claim-extraction-contract.md",
    "docs/observation-audit.md",
    "docs/baseline-results-v0.3.md",
    "data/synthetic/synthea/PROVENANCE.md",
    "docs/historical-sample-data-provenance.md",
    "docs/playground.md",
]


# --- release metadata --------------------------------------------------

def test_pyproject_has_required_metadata():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    project = data["project"]
    assert project["name"] == "meva-health-ai"
    assert project["version"]
    assert project["description"]
    assert project["readme"] == "README.md"
    assert project["license"] == "Apache-2.0"
    assert project["requires-python"].startswith(">=")


def test_pyproject_does_not_add_paid_ai_dependencies():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    deps = " ".join(data["project"]["dependencies"]).lower()
    for forbidden in ("openai", "anthropic", "google-generativeai", "cohere"):
        assert forbidden not in deps


# --- public-file existence ----------------------------------------------

def test_all_required_public_files_exist():
    for name in REQUIRED_PUBLIC_FILES:
        assert (REPO_ROOT / name).exists(), f"missing required public file: {name}"


def test_license_file_is_apache_2_0_text():
    text = (REPO_ROOT / "LICENSE").read_text()
    assert "Apache License" in text
    assert "Version 2.0" in text


def test_third_party_notices_documents_synthea_sample_data_licensing_question():
    text = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text()
    assert "synthea-sample-data" in text
    # Stage 8A.1: the blocker was resolved by removal (locally-generated fixtures replaced
    # the unlicensed-provenance files), not by asserting a license — this still must be
    # documented, just with different wording than Stage 8A's original "UNCLEAR" framing.
    assert "no declared license" in text.lower() or "license field is unset" in text.lower()
    assert "no longer" in text.lower()


def test_third_party_notices_does_not_claim_model_weights_are_meva_licensed():
    text = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text().lower()
    assert "redistribute either model's weights" in text


# --- benchmark docs references --------------------------------------------

def test_readme_references_key_docs():
    readme = (REPO_ROOT / "README.md").read_text()
    for doc in DOC_FILES_REFERENCED_BY_README:
        assert doc in readme, f"README.md does not reference {doc}"
        assert (REPO_ROOT / doc).exists(), f"{doc} referenced by README.md does not exist"


def test_readme_states_safety_scope_boundaries():
    readme = (REPO_ROOT / "README.md").read_text().lower()
    for phrase in ("not a medical chatbot", "clinically validated", "medical device"):
        assert phrase in readme


def test_readme_does_not_declare_a_benchmark_winner():
    readme = (REPO_ROOT / "README.md").read_text().lower()
    assert "no winner is declared" in readme or "does not declare a winner" in readme.replace("no winner is declared", "does not declare a winner")


def test_readme_discloses_metric_correction_history():
    baseline = (REPO_ROOT / "docs" / "baseline-results-v0.3.md").read_text().lower()
    assert "per-case mean" in baseline
    assert "micro-average" in baseline
    assert "corrected" in baseline


# --- CI / templates -----------------------------------------------------

def test_ci_workflow_does_not_require_ollama_or_secrets():
    ci_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text().lower()
    for forbidden in ("ollama", "api_key", "secrets.", "gpu"):
        assert forbidden not in ci_text


def test_issue_and_pr_templates_exist():
    assert (REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").exists()
    for name in ("bug_report.yml", "feature_request.yml", "benchmark_case.yml", "config.yml"):
        assert (REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / name).exists()


def test_benchmark_case_template_forbids_real_patient_data():
    text = (REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "benchmark_case.yml").read_text().lower()
    assert "synthetic" in text
    assert "real patient" in text


# --- release_check.py behavior --------------------------------------------

def test_release_check_script_passes_on_current_repo():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "release_check.py")],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_release_check_detects_missing_required_file(tmp_path, monkeypatch):
    import importlib

    import scripts.release_check as release_check
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_required_files()
    assert len(errors) == len(REQUIRED_PUBLIC_FILES)


def test_release_check_detects_absolute_machine_path(tmp_path, monkeypatch):
    # Built at runtime, not as a literal contiguous string in this file's own source, so
    # this test doesn't trip release_check's own scan when it later scans this test file.
    fake_path = "/" + "Users" + "/" + "someone" + "/secret-project"
    import scripts.release_check as release_check
    (tmp_path / "leaky.md").write_text(f"See {fake_path} for details.")
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    expected_match = "/" + "Users" + "/" + "someone"
    errors = release_check.check_no_absolute_machine_paths()
    assert any(expected_match in e for e in errors)


def test_release_check_detects_forbidden_dependency(tmp_path, monkeypatch):
    import scripts.release_check as release_check
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["openai>=1.0"]\n')
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_no_forbidden_dependencies()
    assert any("openai" in e for e in errors)


# --- Stage 8C: browser sandbox release checks -------------------------------

def test_release_check_detects_missing_streamlit_entry_point(tmp_path, monkeypatch):
    import scripts.release_check as release_check
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_streamlit_entry_point_exists()
    assert any("streamlit_app.py" in e for e in errors)


def test_release_check_passes_streamlit_entry_point_on_real_repo():
    import scripts.release_check as release_check
    assert release_check.check_streamlit_entry_point_exists() == []


def test_release_check_detects_missing_playground_deployment_files(tmp_path, monkeypatch):
    import scripts.release_check as release_check
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = []\n')
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_playground_deployment_files_exist()
    assert any("requirements.txt" in e for e in errors)
    assert any(".streamlit/config.toml" in e for e in errors)


def test_release_check_detects_streamlit_as_core_dependency(tmp_path, monkeypatch):
    import scripts.release_check as release_check
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["streamlit>=1.38.0"]\n'
        '[project.optional-dependencies]\nplayground = ["streamlit>=1.38.0"]\n'
    )
    (tmp_path / "requirements.txt").write_text(".[playground]\n")
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "config.toml").write_text("[browser]\n")
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_playground_deployment_files_exist()
    assert any("core dependency" in e for e in errors)


def test_release_check_detects_committed_secrets_toml(tmp_path, monkeypatch):
    import scripts.release_check as release_check
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "secrets.toml").write_text('api_key = "should-not-exist"\n')
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_no_secrets_files_committed()
    assert any("secrets.toml" in e for e in errors)


def test_release_check_passes_no_secrets_on_real_repo():
    import scripts.release_check as release_check
    assert release_check.check_no_secrets_files_committed() == []


# --- Stage 8D: release-candidate release-check extensions -------------------

def test_release_check_detects_missing_publishing_checklist(tmp_path, monkeypatch):
    import scripts.release_check as release_check
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_publishing_docs_exist()
    assert any("publishing-checklist.md" in e for e in errors)


def test_release_check_passes_publishing_checklist_on_real_repo():
    import scripts.release_check as release_check
    assert release_check.check_publishing_docs_exist() == []


def test_release_check_flags_undocumented_placeholder(tmp_path, monkeypatch):
    import scripts.release_check as release_check
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "publishing-checklist.md").write_text("nothing tracked here\n")
    (tmp_path / "leaky.md").write_text("See <REPO_URL_PLACEHOLDER> for details.\n")
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_placeholders_are_all_documented()
    assert any("REPO_URL_PLACEHOLDER" in e for e in errors)


def test_release_check_passes_placeholder_tracking_on_real_repo():
    import scripts.release_check as release_check
    assert release_check.check_placeholders_are_all_documented() == []


def test_release_check_detects_version_mismatch(tmp_path, monkeypatch):
    import scripts.release_check as release_check
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "9.9.9"\n')
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_version_consistency()
    assert any("CITATION.cff" in e or "CHANGELOG.md" in e or "MEVA_VERSION" in e for e in errors)


def test_release_check_passes_version_consistency_on_real_repo():
    import scripts.release_check as release_check
    assert release_check.check_version_consistency() == []


def test_release_check_detects_missing_v03_v04_distinction(tmp_path, monkeypatch):
    import scripts.release_check as release_check
    (tmp_path / "README.md").write_text("MEVA has great benchmark results.\n")
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)
    errors = release_check.check_v03_v04_wording_sanity()
    assert errors


def test_release_check_passes_v03_v04_wording_on_real_repo():
    import scripts.release_check as release_check
    assert release_check.check_v03_v04_wording_sanity() == []


# --- no obvious secrets in tracked source/docs -----------------------------

def test_no_obvious_secret_patterns_in_source_and_docs():
    import re
    secret_pattern = re.compile(r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}")
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".venv", "venv", "__pycache__", ".git", "results", ".claude", ".pytest_cache"} for part in path.parts):
            continue
        if path.suffix not in {".py", ".md", ".toml", ".json", ".yml", ".yaml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        assert not secret_pattern.search(text), f"possible secret pattern found in {path.relative_to(REPO_ROOT)}"
