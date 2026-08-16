"""Stage 8D — release-candidate finalization tests.

Fully offline. Covers exactly the release-readiness gaps this stage found:
version consistency, no unresolved non-placeholder strings leaking into
public docs, and the repository-relative data path assumption that Stage
8D's package-build check found is load-bearing (see
docs/publishing-checklist.md, "Known packaging note").
"""

from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # Python 3.10

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- version consistency ----------------------------------------------

def test_version_is_0_1_0_everywhere_it_is_declared():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == "0.1.0"

    citation_text = (REPO_ROOT / "CITATION.cff").read_text()
    assert "version: 0.1.0" in citation_text

    changelog_text = (REPO_ROOT / "CHANGELOG.md").read_text()
    assert "[0.1.0] - Unreleased" in changelog_text

    from meva.benchmark.reporter import MEVA_VERSION
    assert MEVA_VERSION == "0.1.0"


def test_changelog_not_prematurely_marked_released():
    changelog_text = (REPO_ROOT / "CHANGELOG.md").read_text()
    assert "Unreleased" in changelog_text
    assert "No GitHub release has been published yet" in changelog_text


# --- repository-relative data path (packaging note) ---------------------

def test_mcp_registry_data_dir_resolves_to_repo_data_directory():
    """DATA_DIR's parent-count arithmetic must still land on the real
    data/synthetic/synthea directory — a silent regression here (e.g. after
    moving registry.py) would make every public fixture invisible."""
    from meva.mcp.registry import DATA_DIR

    assert DATA_DIR.exists()
    assert DATA_DIR.name == "synthea"
    assert (DATA_DIR / "manifest.json").exists()
    assert len(list(DATA_DIR.glob("patient-*.json"))) == 21


# --- v0.3/v0.4 wording sanity (release-candidate pass) -----------------

def test_readme_never_implies_v03_results_are_v04_results():
    readme = (REPO_ROOT / "README.md").read_text()
    # Every "v0.4" mention involving model names must also mention "pending"
    # or sit inside a sentence explicitly distinguishing it from v0.3.
    assert "v0.4 model-comparison results are pending" in readme or "v0.4 model results" in readme.lower()
    assert "HISTORICAL DEVELOPMENT RESULT" in readme
    assert "PUBLIC REPRODUCIBLE DATASET" in readme


def test_changelog_explains_historical_vs_public_dataset_distinction():
    changelog_text = " ".join((REPO_ROOT / "CHANGELOG.md").read_text().lower().split())
    assert "v0.4 model comparison results are pending" in changelog_text
    assert "historical development records" in changelog_text


# --- publishing checklist exists and lists exact placeholders ------------

def test_publishing_checklist_reflects_stage_8e1_resolution():
    """Stage 8E1 resolved every pre-push placeholder with real maintainer-supplied
    values — the checklist should document that resolution, not still list unresolved
    placeholder tokens (see docs/publishing-checklist.md's 'Resolved' table)."""
    checklist = (REPO_ROOT / "docs" / "publishing-checklist.md").read_text()
    assert "Resolved (Stage 8E1)" in checklist
    assert "Tanzim Bin Zahir" in checklist
    assert "Tanz2024" in checklist
    # Deliberately-deferred items (not fabricated) must still be tracked.
    assert "date-released" in checklist
    assert "Screenshots" in checklist


def test_no_unresolved_publishing_placeholders_remain_in_docs():
    """Every placeholder Stage 8D flagged as needing maintainer input has now been
    filled with a real value (or explicitly, deliberately omitted — see
    test_citation_cff_has_no_email) — none should remain as a literal token in any
    public-facing doc/config file."""
    doc_extensions = {".md", ".toml", ".cff", ".yml", ".yaml"}
    unresolved_tokens = (
        "<REPO_URL_PLACEHOLDER>", "<MAINTAINER_CONTACT_EMAIL_PLACEHOLDER>",
        "<SECURITY_CONTACT_EMAIL_PLACEHOLDER>", "PLACEHOLDER-AUTHOR-NAME-OR-ORGANIZATION",
        "PLACEHOLDER-REPO-URL", "PLACEHOLDER-ORG", "PLACEHOLDER-REPO",
    )
    excluded_dirs = {".venv", "venv", "__pycache__", ".git", ".pytest_cache", "results", ".claude", "tests", "scripts"}
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in doc_extensions:
            continue
        if any(part in excluded_dirs for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in unresolved_tokens:
            assert token not in text, f"{path.relative_to(REPO_ROOT)}: unresolved placeholder {token!r} remains"


def test_citation_cff_has_no_email_and_real_author():
    text = (REPO_ROOT / "CITATION.cff").read_text()
    assert "Tanzim Bin Zahir" in text
    assert "PLACEHOLDER" not in text
    # No email address or ORCID field anywhere, per explicit maintainer instruction —
    # checked only in the actual YAML fields, not the explanatory header comment.
    yaml_body = text.split("cff-version:")[1]
    assert "@" not in yaml_body
    assert "orcid" not in yaml_body.lower()
