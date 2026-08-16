"""Validate a benchmark dataset before it's ever run.

Catches broken benchmark definitions early with clear messages, rather
than letting a malformed case fail confusingly mid-run (or silently
produce a meaningless result). This module never touches an LLM — it
only checks cases against MEVA's real tool output (via meva.mcp.server —
the same functions the agent actually calls) and MEVA's existing
conservative normalizer.
"""

from meva.ai.tools import TOOL_SCHEMAS
from meva.benchmark.models import BENCHMARK_CATEGORIES, CASE_TYPES, BenchmarkCase
from meva.fhir import blood_pressure_text
from meva.mcp import server as mcp_server
from meva.verification.normalizer import normalize_text, values_match

VALID_TOOL_NAMES = {schema["function"]["name"] for schema in TOOL_SCHEMAS}

# A conservative keyword blocklist for catching diagnosis/treatment-flavored
# questions before they ever enter the benchmark dataset. This is deliberately
# blunt (substring match) — false positives just mean a case gets flagged for
# a human to look at, which is the safe direction to err in.
_UNSAFE_KEYWORDS = (
    "diagnose", "diagnosis", "treat", "prescri", "cure", "should take", "should i take",
    "recommend a medication", "recommend treatment", "what medication should",
)


class ValidationError(Exception):
    """Raised with a clear, specific message when a benchmark case is invalid."""


def _check_unsafe_language(case: BenchmarkCase) -> list[str]:
    text = f"{case.question} {case.description}".lower()
    return [kw for kw in _UNSAFE_KEYWORDS if kw in text]


def _patient_exists(patient_id: str) -> bool:
    try:
        mcp_server.get_patient(patient_id)
        return True
    except ValueError:
        return False


def _tool_values(patient_id: str, source_tool: str) -> list[tuple[str, str | None]]:
    """Return [(comparable_value, resource_id), ...] as actually produced by MEVA's own tools."""
    if source_tool == "get_patient":
        patient = mcp_server.get_patient(patient_id)
        return [(str(v), None) for v in patient.values() if isinstance(v, str)]

    if source_tool == "get_allergies":
        return [(a["name"], a["id"]) for a in mcp_server.get_allergies(patient_id)]
    if source_tool == "get_medications":
        return [(m["name"], m["id"]) for m in mcp_server.get_medications(patient_id)]
    if source_tool == "get_conditions":
        return [(c["name"], c["id"]) for c in mcp_server.get_conditions(patient_id)]
    if source_tool == "get_encounters":
        return [(f"{e['type']} ({e['status']})", e["id"]) for e in mcp_server.get_encounters(patient_id, limit=100)]
    if source_tool == "get_observations":
        pairs = []
        for o in mcp_server.get_observations(patient_id, limit=100):
            bp = blood_pressure_text(o)
            pairs.append((bp if bp else str(o["value"]), o["id"]))
            pairs.append((o["name"], o["id"]))
        return pairs

    return []


def _check_expected_evidence(case: BenchmarkCase, patient_exists: bool, errors: list[str]) -> None:
    if not case.expected_evidence_facts:
        return

    if not patient_exists:
        errors.append(f"{case.case_id}: has expected_evidence_facts but patient '{case.patient_id}' was not found")
        return

    for fact in case.expected_evidence_facts:
        try:
            candidates = _tool_values(case.patient_id, fact.source_tool)
        except Exception as e:
            errors.append(f"{case.case_id}: could not fetch '{fact.source_tool}' evidence to validate: {e}")
            continue

        if fact.resource_id:
            candidates = [c for c in candidates if c[1] == fact.resource_id] or candidates
            if not any(c[1] == fact.resource_id for c in candidates):
                errors.append(
                    f"{case.case_id}: expected_evidence resource_id '{fact.resource_id}' not found via "
                    f"'{fact.source_tool}' for patient '{case.patient_id}'"
                )

        if not any(values_match(fact.value, value) for value, _ in candidates):
            errors.append(
                f"{case.case_id}: expected_evidence value '{fact.value}' ({fact.category}) not found via "
                f"'{fact.source_tool}' for patient '{case.patient_id}'"
            )


def validate_case(case: BenchmarkCase) -> list[str]:
    """Return a list of human-readable problems with one case (empty list = valid)."""
    errors = []

    if case.category not in BENCHMARK_CATEGORIES:
        errors.append(f"{case.case_id}: unknown category '{case.category}'")

    if case.case_type not in CASE_TYPES:
        errors.append(f"{case.case_id}: unknown case_type '{case.case_type}' (must be one of {CASE_TYPES})")

    if case.case_type == "VERIFIER_CHALLENGE" and not case.injected_claim:
        errors.append(f"{case.case_id}: VERIFIER_CHALLENGE cases must set injected_claim")

    for tool in case.expected_tools:
        if tool not in VALID_TOOL_NAMES:
            errors.append(f"{case.case_id}: expected_tools contains unknown tool '{tool}'")

    unsafe = _check_unsafe_language(case)
    if unsafe:
        errors.append(f"{case.case_id}: question/description contains unsafe language: {unsafe}")

    # Verifier-challenge cases don't call a live patient lookup, so their
    # patient_id doesn't need to resolve to a real bundle.
    if case.case_type != "VERIFIER_CHALLENGE":
        exists = _patient_exists(case.patient_id)
        patient_intentionally_invalid = case.category == "invalid_patient"

        if not exists and not patient_intentionally_invalid:
            errors.append(f"{case.case_id}: patient_id '{case.patient_id}' was not found, but category is not 'invalid_patient'")
        if exists and patient_intentionally_invalid:
            errors.append(f"{case.case_id}: category is 'invalid_patient' but patient_id '{case.patient_id}' actually exists")

        _check_expected_evidence(case, exists, errors)

    return errors


def _exact_duplicate_key(case: BenchmarkCase) -> tuple:
    """A deterministic fingerprint of 'what this case actually tests'.

    Two cases sharing this key ask the same question, of the same patient,
    needing the same tools, expecting the same evidence resources — an
    exact duplicate, not just a similar-looking case. No embeddings/LLM.
    """
    resource_ids = tuple(sorted(f.resource_id for f in case.expected_evidence_facts if f.resource_id))
    return (
        case.patient_id,
        case.category,
        tuple(sorted(case.expected_tools)),
        resource_ids,
        normalize_text(case.question),
    )


def find_duplicates(cases: list[BenchmarkCase]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for duplicate/near-duplicate cases.

    Exact duplicates (same patient/category/tools/evidence/question) are
    errors. Cases with identical question wording but a different
    fingerprint otherwise are flagged as a warning only — potentially
    redundant, but not necessarily wrong.
    """
    errors = []
    exact_seen: dict[tuple, str] = {}
    exact_duplicate_case_ids: set[str] = set()

    for case in cases:
        key = _exact_duplicate_key(case)
        if key in exact_seen:
            errors.append(f"{case.case_id}: exact duplicate of '{exact_seen[key]}' (same patient/category/tools/evidence/question)")
            exact_duplicate_case_ids.add(case.case_id)
        else:
            exact_seen[key] = case.case_id

    warnings = []
    question_seen: dict[str, str] = {}
    for case in cases:
        if case.case_id in exact_duplicate_case_ids:
            continue  # already reported as a hard error above; don't also warn
        q = normalize_text(case.question)
        if q in question_seen:
            warnings.append(f"{case.case_id}: same question text as '{question_seen[q]}' — possible semantic duplicate, please review")
        else:
            question_seen[q] = case.case_id

    return errors, warnings


def validate_dataset(cases: list[BenchmarkCase]) -> list[str]:
    """Validate a full dataset.

    Raises ValidationError (with every hard problem found) if the dataset
    is broken. Returns a list of non-fatal warnings (e.g. possible
    semantic duplicates) otherwise.
    """
    errors = []

    seen_ids = set()
    for case in cases:
        if case.case_id in seen_ids:
            errors.append(f"duplicate case_id: '{case.case_id}'")
        seen_ids.add(case.case_id)

        errors.extend(validate_case(case))

    duplicate_errors, warnings = find_duplicates(cases)
    errors.extend(duplicate_errors)

    if errors:
        message = "\n".join(f"  - {e}" for e in errors)
        raise ValidationError(f"Benchmark dataset failed validation ({len(errors)} problem(s)):\n{message}")

    return warnings
