#!/usr/bin/env python3
"""Deterministic pre-release sanity checks for MEVA's public repository.

Not a security scanner — a small set of concrete, explainable checks: do
the required public files exist, does the benchmark dataset still validate,
is there an obvious accidentally-committed absolute machine path or paid-AI
SDK dependency, and does the package still import. Exit code 0 = all checks
passed; 1 = at least one check failed (each failure is printed).
"""

import re
import sys
from pathlib import Path

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

# Stage 8C — browser sandbox deployment-preparation files.
STREAMLIT_ENTRY_POINT = "streamlit_app.py"
PLAYGROUND_DEPLOYMENT_FILES = [
    "requirements.txt",
    ".streamlit/config.toml",
]
FORBIDDEN_SECRETS_FILES = [
    ".streamlit/secrets.toml",
]

# Directories never scanned for path/dependency issues — build artifacts,
# caches, and the (gitignored) local venv/results, not shipped source.
EXCLUDED_DIR_NAMES = {".venv", "venv", "__pycache__", ".git", ".pytest_cache", "results", ".claude"}

# Source/doc file extensions actually reviewed for public-repo cleanliness.
SCANNED_EXTENSIONS = {".py", ".md", ".toml", ".yml", ".yaml", ".cff"}

FORBIDDEN_DEPENDENCY_NAMES = ("openai", "anthropic", "google-generativeai", "google-genai", "cohere")

ABSOLUTE_PATH_PATTERN = re.compile(r"/Users/[A-Za-z0-9_.-]+")

# Stage 8D — every explicit pre-push placeholder is EXPECTED to remain until a
# maintainer fills it in (see docs/publishing-checklist.md). This check only
# confirms each one is still documented there — it never demands they be
# resolved, and never invents a replacement value.
ALLOWED_PENDING_PLACEHOLDERS = (
    "<REPO_URL_PLACEHOLDER>",
    "<MAINTAINER_CONTACT_EMAIL_PLACEHOLDER>",
    "<SECURITY_CONTACT_EMAIL_PLACEHOLDER>",
    "PLACEHOLDER-AUTHOR-NAME-OR-ORGANIZATION",
    "PLACEHOLDER-REPO-URL",
    "PLACEHOLDER-YYYY-MM-DD",
    "PLACEHOLDER-ORG",
    "PLACEHOLDER-REPO",
)

# The current, live, publicly-committed benchmark dataset — fully live-validated
# (every expected_evidence_facts entry checked against real, on-disk FHIR data).
LIVE_BENCHMARK_VERSION = "v0.4"

# SHA-256 hashes of the 18 patient files removed in Stage 8A.1 (originally copied from
# synthetichealth/synthea-sample-data, a repository with no declared license — see
# docs/historical-sample-data-provenance.md). These must never reappear in the public
# data/synthetic/synthea/ directory.
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


def _iter_scanned_files():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        if path.suffix not in SCANNED_EXTENSIONS:
            continue
        yield path


def check_required_files() -> list[str]:
    errors = []
    for name in REQUIRED_PUBLIC_FILES:
        if not (REPO_ROOT / name).exists():
            errors.append(f"Missing required public file: {name}")
    return errors


def check_benchmark_manifests_validate() -> list[str]:
    """Fully live-validates only LIVE_BENCHMARK_VERSION (every expected_evidence_facts
    entry checked against real, on-disk FHIR data). Older dataset versions (v0.1-v0.3)
    reference patients removed in Stage 8A.1 for licensing reasons (see
    docs/historical-sample-data-provenance.md) and can no longer be live-validated —
    they're only checked for basic structural loadability (valid JSON, valid BenchmarkCase
    schema), not evidence-traceability, so historical data loss doesn't masquerade as a
    dataset bug."""
    errors = []
    try:
        from meva.benchmark.loader import load_cases
        from meva.benchmark.validator import ValidationError, validate_dataset
    except ImportError as e:
        return [f"Could not import meva.benchmark to validate datasets: {e}"]

    benchmarks_dir = REPO_ROOT / "benchmarks"
    if not benchmarks_dir.exists():
        return ["benchmarks/ directory not found"]

    live_dataset_found = False
    for version_dir in sorted(benchmarks_dir.iterdir()):
        cases_path = version_dir / "cases.json"
        if not cases_path.exists():
            continue
        try:
            cases = load_cases(path=cases_path)
        except Exception as e:
            errors.append(f"{version_dir.name}: could not load dataset: {type(e).__name__}: {e}")
            continue

        if version_dir.name == LIVE_BENCHMARK_VERSION:
            live_dataset_found = True
            try:
                validate_dataset(cases)
            except ValidationError as e:
                errors.append(f"{version_dir.name} (live dataset): dataset failed validation: {e}")
        # else: historical dataset — structural load above already proves it's valid JSON
        # matching the BenchmarkCase schema; no live evidence check performed.

    if not live_dataset_found:
        errors.append(f"Live benchmark dataset '{LIVE_BENCHMARK_VERSION}' not found under benchmarks/")

    manifest_path = benchmarks_dir / LIVE_BENCHMARK_VERSION / "manifest.json"
    if not manifest_path.exists():
        errors.append(f"benchmarks/{LIVE_BENCHMARK_VERSION}/manifest.json not found")

    return errors


def check_no_historical_unlicensed_sample_data() -> list[str]:
    """Fails if any file whose content hash matches the removed synthea-sample-data
    patients (Stage 8A.1) is present anywhere under data/synthetic/ — those files must
    never reappear in the public dataset. See docs/historical-sample-data-provenance.md."""
    import hashlib

    errors = []
    data_dir = REPO_ROOT / "data" / "synthetic"
    if not data_dir.exists():
        return []
    for path in data_dir.rglob("*.json"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in FORMER_UNLICENSED_SAMPLE_DATA_HASHES:
            errors.append(
                f"{path.relative_to(REPO_ROOT)}: content hash matches a removed, "
                f"unlicensed-provenance synthea-sample-data file — must not be reintroduced"
            )
    return errors


def check_public_fixture_provenance() -> list[str]:
    """The public Synthea fixtures must carry documented provenance, and every
    committed fixture's current hash must match what PROVENANCE.md's machine-readable
    companion (data/synthetic/synthea/manifest.json) recorded."""
    import hashlib
    import json

    errors = []
    synthea_dir = REPO_ROOT / "data" / "synthetic" / "synthea"
    provenance_md = synthea_dir / "PROVENANCE.md"
    manifest_path = synthea_dir / "manifest.json"

    if not provenance_md.exists():
        errors.append("data/synthetic/synthea/PROVENANCE.md not found")
    if not manifest_path.exists():
        errors.append("data/synthetic/synthea/manifest.json not found")
        return errors

    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return errors + [f"data/synthetic/synthea/manifest.json could not be read: {e}"]

    for entry in manifest:
        fixture_path = synthea_dir / entry["repo_filename"]
        if not fixture_path.exists():
            errors.append(f"{entry['repo_filename']}: listed in manifest.json but file is missing")
            continue
        actual_hash = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        if actual_hash != entry["sha256"]:
            errors.append(
                f"{entry['repo_filename']}: current hash does not match manifest.json "
                f"(expected {entry['sha256'][:12]}..., got {actual_hash[:12]}...)"
            )
    return errors


def check_no_absolute_machine_paths() -> list[str]:
    errors = []
    for path in _iter_scanned_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in ABSOLUTE_PATH_PATTERN.finditer(text):
            errors.append(f"{path.relative_to(REPO_ROOT)}: possible machine-specific path '{match.group(0)}'")
    return errors


def check_no_forbidden_dependencies() -> list[str]:
    errors = []
    pyproject_path = REPO_ROOT / "pyproject.toml"
    if not pyproject_path.exists():
        return ["pyproject.toml not found"]
    text = pyproject_path.read_text(encoding="utf-8").lower()
    for name in FORBIDDEN_DEPENDENCY_NAMES:
        if name in text:
            errors.append(f"pyproject.toml appears to reference a forbidden paid-AI dependency: '{name}'")
    return errors


def check_no_staged_runtime_results() -> list[str]:
    """results/ must stay gitignored — check .gitignore actually covers it, not that
    the directory is empty (developers legitimately have local results while working)."""
    gitignore_path = REPO_ROOT / ".gitignore"
    if not gitignore_path.exists():
        return [".gitignore not found"]
    gitignore_text = gitignore_path.read_text(encoding="utf-8")
    if "results/" not in gitignore_text:
        return ["results/ is not listed in .gitignore — runtime result files would be publicly committed"]
    return []


def check_package_imports() -> list[str]:
    try:
        import meva  # noqa: F401
        import meva.ai  # noqa: F401
        import meva.benchmark  # noqa: F401
        import meva.extraction  # noqa: F401
        import meva.fhir  # noqa: F401
        import meva.mcp  # noqa: F401
        import meva.models  # noqa: F401
        import meva.playground  # noqa: F401
        import meva.verification  # noqa: F401
    except ImportError as e:
        return [f"Package import failed: {e}"]
    return []


def check_streamlit_entry_point_exists() -> list[str]:
    """Stage 8C: the browser sandbox needs exactly one conventional entry point."""
    if not (REPO_ROOT / STREAMLIT_ENTRY_POINT).exists():
        return [f"{STREAMLIT_ENTRY_POINT} not found — the Stage 8C browser sandbox entry point is missing"]
    return []


def check_playground_deployment_files_exist() -> list[str]:
    """Stage 8C: minimal deployment-preparation files (not an actual deployment)."""
    errors = []
    for name in PLAYGROUND_DEPLOYMENT_FILES:
        if not (REPO_ROOT / name).exists():
            errors.append(f"Missing playground deployment file: {name}")

    pyproject_path = REPO_ROOT / "pyproject.toml"
    if pyproject_path.exists():
        text = pyproject_path.read_text()
        if "streamlit" not in text.lower():
            errors.append("pyproject.toml does not declare a streamlit dependency anywhere")
        # Streamlit must stay optional — never a core runtime dependency.
        try:
            import tomllib
            data = tomllib.loads(text)
            core_deps = " ".join(data.get("project", {}).get("dependencies", [])).lower()
            if "streamlit" in core_deps:
                errors.append("streamlit must not be a core dependency — keep it under [project.optional-dependencies]")
        except Exception as e:
            errors.append(f"Could not parse pyproject.toml to check dependency isolation: {e}")
    return errors


def check_no_secrets_files_committed() -> list[str]:
    """Stage 8C: no Streamlit secrets file (or other obvious secret file) should exist —
    the sandbox requires no API keys/tokens of any kind."""
    errors = []
    for name in FORBIDDEN_SECRETS_FILES:
        if (REPO_ROOT / name).exists():
            errors.append(f"{name} exists — the sandbox must not require or ship secrets")
    for path in REPO_ROOT.rglob("secrets.toml"):
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        errors.append(f"{path.relative_to(REPO_ROOT)}: a secrets.toml file exists and must not be committed")
    return errors


def check_publishing_docs_exist() -> list[str]:
    """Stage 8D: the exact-placeholder checklist must exist before first push."""
    errors = []
    if not (REPO_ROOT / "docs" / "publishing-checklist.md").exists():
        errors.append("docs/publishing-checklist.md not found")
    return errors


def check_placeholders_are_all_documented() -> list[str]:
    """Stage 8D: every ALLOWED_PENDING_PLACEHOLDERS string found anywhere in tracked
    docs/source must also be mentioned in docs/publishing-checklist.md — so a
    placeholder can never be silently forgotten. This does NOT require placeholders
    to be resolved; it only requires them to stay tracked."""
    errors = []
    checklist_path = REPO_ROOT / "docs" / "publishing-checklist.md"
    if not checklist_path.exists():
        return errors  # already reported by check_publishing_docs_exist

    checklist_text = checklist_path.read_text()
    found_anywhere: set[str] = set()
    # Only doc/config-shaped files can carry a REAL unresolved placeholder — .py files
    # (scripts/release_check.py itself, tests/) legitimately reference these same literal
    # strings as constants/fixtures while testing this very check, which isn't a real
    # unresolved placeholder in a public-facing file.
    doc_extensions = {".md", ".toml", ".cff", ".yml", ".yaml"}
    for path in _iter_scanned_files():
        if path.suffix not in doc_extensions:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for placeholder in ALLOWED_PENDING_PLACEHOLDERS:
            if placeholder in text:
                found_anywhere.add(placeholder)

    for placeholder in found_anywhere:
        if placeholder not in checklist_text:
            errors.append(f"Placeholder '{placeholder}' appears in the repo but is not tracked in docs/publishing-checklist.md")
    return errors


def check_version_consistency() -> list[str]:
    """Stage 8D: pyproject.toml, CITATION.cff, CHANGELOG.md, and MEVA_VERSION must
    all agree on the target release version (currently 0.1.0)."""
    errors = []
    try:
        import tomllib
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
        version = pyproject["project"]["version"]
    except Exception as e:
        return [f"Could not read version from pyproject.toml: {e}"]

    citation_path = REPO_ROOT / "CITATION.cff"
    if citation_path.exists() and f"version: {version}" not in citation_path.read_text():
        errors.append(f"CITATION.cff does not declare version: {version}")

    changelog_path = REPO_ROOT / "CHANGELOG.md"
    if changelog_path.exists() and f"[{version}]" not in changelog_path.read_text():
        errors.append(f"CHANGELOG.md has no [{version}] entry")

    try:
        from meva.benchmark.reporter import MEVA_VERSION
        if MEVA_VERSION != version:
            errors.append(f"meva.benchmark.reporter.MEVA_VERSION ({MEVA_VERSION}) != pyproject.toml version ({version})")
    except ImportError as e:
        errors.append(f"Could not import meva.benchmark.reporter to check MEVA_VERSION: {e}")

    return errors


def check_v03_v04_wording_sanity() -> list[str]:
    """Stage 8D: README must clearly separate the historical v0.3 development result
    from the current public v0.4 dataset, and must not claim v0.4 model results exist."""
    errors = []
    readme_path = REPO_ROOT / "README.md"
    if not readme_path.exists():
        return ["README.md not found"]
    text = readme_path.read_text()

    if "HISTORICAL DEVELOPMENT RESULT" not in text or "PUBLIC REPRODUCIBLE DATASET" not in text:
        errors.append("README.md does not clearly label historical (v0.3) vs. public (v0.4) datasets")

    normalized = " ".join(text.lower().replace("-", " ").split())
    if "v0.4 model comparison results are pending" not in normalized:
        errors.append("README.md does not state that v0.4 model-comparison results are pending")

    return errors


CHECKS = [
    ("Required public files exist", check_required_files),
    ("Benchmark manifests validate", check_benchmark_manifests_validate),
    ("No historical unlicensed sample data present", check_no_historical_unlicensed_sample_data),
    ("Public fixture provenance present and hashes match", check_public_fixture_provenance),
    ("No obvious absolute machine-specific paths", check_no_absolute_machine_paths),
    ("No forbidden paid-AI SDK dependency names", check_no_forbidden_dependencies),
    ("results/ properly gitignored", check_no_staged_runtime_results),
    ("Package imports successfully", check_package_imports),
    ("Streamlit entry point exists", check_streamlit_entry_point_exists),
    ("Playground deployment files present and isolated", check_playground_deployment_files_exist),
    ("No secrets files committed", check_no_secrets_files_committed),
    ("Publishing checklist exists", check_publishing_docs_exist),
    ("All pending placeholders are tracked in the publishing checklist", check_placeholders_are_all_documented),
    ("Version consistency (pyproject/CITATION/CHANGELOG/MEVA_VERSION)", check_version_consistency),
    ("v0.3/v0.4 wording sanity", check_v03_v04_wording_sanity),
]


def main() -> int:
    all_errors = []
    for label, check_fn in CHECKS:
        errors = check_fn()
        status = "PASS" if not errors else "FAIL"
        print(f"[{status}] {label}")
        for error in errors:
            print(f"    - {error}")
        all_errors.extend(errors)

    print()
    if all_errors:
        print(f"release_check: {len(all_errors)} problem(s) found.")
        return 1

    print("release_check: all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
