"""Extractor fidelity evaluation against hand-reviewed gold fixtures (Stage 7D2).

Schema validity (Stage 7D1) proves the extractor's OUTPUT is well-formed —
it says nothing about whether the claims it produced are the claims the
answer actually made. This module measures that directly: does the
extractor capture what was said, avoid inventing claims, avoid dropping
claims, and refuse to "fix" a wrong answer?

Claim matching here is fully deterministic — normalized structured-field
equality (patient_id/category/assertion/value/attribute/attribute_value),
via MEVA's existing conservative text normalizer. No embeddings, no LLM
judge, no fuzzy medical-synonym matching, no external knowledge.
"""

from meva.extraction.extractor import extract_claims
from meva.verification.models import MedicalClaim
from meva.verification.normalizer import normalize_text

# Below these, Stage 7D2's decision gate stops before the full 104-answer run
# rather than silently proceeding on a poorly-fidelity extractor. Chosen as a
# conservative "clearly usable" bar, not tuned to whatever qwen3:4b happens to score.
MIN_ACCEPTABLE_PRECISION = 0.7
MIN_ACCEPTABLE_RECALL = 0.7

# Stage 7D2.1's HOLDOUT gate — stricter, and recorded here BEFORE the holdout run
# (see docs/claim-extraction-contract.md / Stage 7D2.1 §17-18). Never changed after
# seeing holdout results. exact_claim_set_match_rate is reported but is NOT gated on.
HOLDOUT_MIN_PRECISION = 0.80
HOLDOUT_MIN_RECALL = 0.80
HOLDOUT_MIN_F1 = 0.80
HOLDOUT_MIN_NEGATIVE_PRESERVATION = 0.80
HOLDOUT_MIN_ATTRIBUTE_ACCURACY = 0.75


def _norm(value: str | None) -> str | None:
    return normalize_text(value) if value else None


def claim_key(claim: MedicalClaim) -> tuple:
    """A deterministic, normalized fingerprint of a claim's structured fields.

    Two claims with the same key are considered the same claim for matching
    purposes — exact normalized-field equality, not a fuzzy/substring match
    (unlike meva.verification.normalizer.values_match, which is intentionally
    looser for evidence lookup; fidelity matching should not be that generous).
    """
    return (
        claim.patient_id,
        claim.category,
        claim.assertion,
        _norm(claim.value),
        _norm(claim.attribute),
        _norm(claim.attribute_value),
    )


def match_claims(gold_claims: list[MedicalClaim], extracted_claims: list[MedicalClaim]) -> dict:
    """Deterministically match two claim lists and return per-fixture TP/FP/FN.

    Uses set semantics (a claim key present twice counts once) — gold
    fixtures aren't expected to contain literal duplicate claims.
    """
    gold_keys = {claim_key(c) for c in gold_claims}
    extracted_keys = {claim_key(c) for c in extracted_claims}

    true_positive = gold_keys & extracted_keys
    false_positive = extracted_keys - gold_keys
    false_negative = gold_keys - extracted_keys

    return {
        "gold_claim_count": len(gold_claims),
        "extracted_claim_count": len(extracted_claims),
        "true_positive_claims": len(true_positive),
        "false_positive_claims": len(false_positive),
        "false_negative_claims": len(false_negative),
        "exact_claim_set_match": gold_keys == extracted_keys,
    }


_ERROR_TYPES = (
    "added_claim", "missed_claim", "wrong_category", "wrong_assertion",
    "wrong_value", "attribute_error", "uncertainty_error", "other",
)


def classify_mismatches(fixture_id: str, gold_claims: list[MedicalClaim], extracted_claims: list[MedicalClaim]) -> list[dict]:
    """Deterministically classify every unmatched gold/extracted claim into one error type.

    No LLM judge — purely structured-field comparison. For each unmatched gold
    claim, looks for a "near miss" among the unmatched extracted claims (same
    category+value but wrong assertion, etc.); anything left over is a plain
    missed_claim (gold) or added_claim (extracted). A fixture whose id names it
    as an uncertainty case gets its leftover added claims labeled
    uncertainty_error instead of added_claim (still fully deterministic — the
    fixture's own declared expected_claims == [] is what triggers this, not an
    LLM's judgement of "this looks uncertain").
    """
    gold_by_key = {claim_key(c): c for c in gold_claims}
    extracted_by_key = {claim_key(c): c for c in extracted_claims}
    matched = set(gold_by_key) & set(extracted_by_key)

    unmatched_gold = {k: c for k, c in gold_by_key.items() if k not in matched}
    unmatched_extracted = {k: c for k, c in extracted_by_key.items() if k not in matched}
    used_extracted: set = set()
    errors = []

    for gkey, gclaim in unmatched_gold.items():
        found = None
        for ekey, eclaim in unmatched_extracted.items():
            if ekey in used_extracted:
                continue
            if eclaim.category == gclaim.category and _norm(eclaim.value) == _norm(gclaim.value) and eclaim.assertion != gclaim.assertion:
                found = (ekey, "wrong_assertion")
            elif eclaim.category == gclaim.category and eclaim.assertion == gclaim.assertion and _norm(eclaim.value) != _norm(gclaim.value):
                found = (ekey, "wrong_value")
            elif eclaim.assertion == gclaim.assertion and _norm(eclaim.value) == _norm(gclaim.value) and eclaim.category != gclaim.category:
                found = (ekey, "wrong_category")
            elif (
                gclaim.assertion == "attribute" and eclaim.assertion == "attribute"
                and eclaim.category == gclaim.category and _norm(eclaim.value) == _norm(gclaim.value)
                and (eclaim.attribute != gclaim.attribute or _norm(eclaim.attribute_value) != _norm(gclaim.attribute_value))
            ):
                found = (ekey, "attribute_error")
            if found:
                break

        if found:
            ekey, error_type = found
            used_extracted.add(ekey)
            errors.append({"type": error_type, "gold_claim": gclaim.model_dump(), "extracted_claim": unmatched_extracted[ekey].model_dump()})
        else:
            errors.append({"type": "missed_claim", "gold_claim": gclaim.model_dump(), "extracted_claim": None})

    is_uncertainty_fixture = not gold_claims and "uncertain" in fixture_id.lower()
    for ekey, eclaim in unmatched_extracted.items():
        if ekey in used_extracted:
            continue
        error_type = "uncertainty_error" if is_uncertainty_fixture else "added_claim"
        errors.append({"type": error_type, "gold_claim": None, "extracted_claim": eclaim.model_dump()})

    return errors


def evaluate_fixture(fixture: dict, extractor_model: str | None = None, base_url: str | None = None) -> dict:
    """Run the extractor over one gold fixture's answer and score it against its expected claims."""
    gold_claims = [MedicalClaim(**c) for c in fixture["expected_claims"]]
    result = extract_claims(
        fixture["question"], fixture["patient_id"], fixture["answer"], model=extractor_model, base_url=base_url,
    )
    match = match_claims(gold_claims, result.claims)
    errors = classify_mismatches(fixture["id"], gold_claims, result.claims)
    return {
        "fixture_id": fixture["id"],
        "schema_parsed": result.schema_parsed,
        "extraction_error": result.extraction_error,
        **match,
        "gold_claims": [c.model_dump() for c in gold_claims],
        "extracted_claims": [c.model_dump() for c in result.claims],
        "errors": errors,
    }


def aggregate_error_counts(fixture_results: list[dict]) -> dict:
    """Per-error-type counts across a whole fidelity run — see classify_mismatches."""
    counts = {error_type: 0 for error_type in _ERROR_TYPES}
    for r in fixture_results:
        for error in r.get("errors", []):
            counts[error["type"]] = counts.get(error["type"], 0) + 1
    return counts


def aggregate_fidelity_metrics(fixture_results: list[dict], fixtures_by_id: dict[str, dict]) -> dict:
    """Micro-averaged precision/recall/F1 and the rest of Stage 7D2's fidelity metrics.

    Micro-averaged (summed TP/FP/FN across all fixtures, then one division) —
    NOT a mean of each fixture's own precision/recall — see Stage 7C2.1 for
    why a per-item macro-average silently misrepresents a "how much of the
    total did we get right" question.
    """
    n = len(fixture_results)
    schema_successes = sum(1 for r in fixture_results if r["schema_parsed"])

    tp = sum(r["true_positive_claims"] for r in fixture_results)
    fp = sum(r["false_positive_claims"] for r in fixture_results)
    fn = sum(r["false_negative_claims"] for r in fixture_results)
    total_extracted = sum(r["extracted_claim_count"] for r in fixture_results)
    total_gold = sum(r["gold_claim_count"] for r in fixture_results)
    exact_matches = sum(1 for r in fixture_results if r["exact_claim_set_match"])

    precision = (tp / (tp + fp)) if (tp + fp) else None
    recall = (tp / (tp + fn)) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision and recall and (precision + recall)) else None

    # Negative-assertion preservation: among gold claims asserting "absent", how many
    # were correctly matched (i.e. not silently dropped or converted to "present").
    negative_gold = 0
    negative_matched = 0
    attribute_gold = 0
    attribute_matched = 0
    for r in fixture_results:
        fixture = fixtures_by_id[r["fixture_id"]]
        gold_claims = [MedicalClaim(**c) for c in fixture["expected_claims"]]
        extracted_keys = {claim_key(MedicalClaim(**c)) for c in r["extracted_claims"]}
        for gc in gold_claims:
            key = claim_key(gc)
            if gc.assertion == "absent":
                negative_gold += 1
                if key in extracted_keys:
                    negative_matched += 1
            if gc.assertion == "attribute":
                attribute_gold += 1
                if key in extracted_keys:
                    attribute_matched += 1

    return {
        "fixture_count": n,
        "schema_success_rate": (schema_successes / n) if n else None,
        "claim_precision": precision,
        "claim_recall": recall,
        "claim_f1": f1,
        "exact_claim_set_match_rate": (exact_matches / n) if n else None,
        "added_claim_rate": (fp / total_extracted) if total_extracted else None,
        "missed_claim_rate": (fn / total_gold) if total_gold else None,
        "negative_claim_preservation_rate": (negative_matched / negative_gold) if negative_gold else None,
        "attribute_claim_accuracy": (attribute_matched / attribute_gold) if attribute_gold else None,
        "true_positive_claims": tp,
        "false_positive_claims": fp,
        "false_negative_claims": fn,
        "total_gold_claims": total_gold,
        "total_extracted_claims": total_extracted,
    }


def passes_decision_gate(metrics: dict) -> bool:
    """Stage 7D2's decision gate: stop before the full run if fidelity looks weak.

    None (e.g. no gold claims at all to measure precision/recall against) is
    treated as "cannot confirm acceptable" — the gate does not pass on a
    missing number, only on an actually-measured one.
    """
    precision, recall = metrics.get("claim_precision"), metrics.get("claim_recall")
    if precision is None or recall is None:
        return False
    return precision >= MIN_ACCEPTABLE_PRECISION and recall >= MIN_ACCEPTABLE_RECALL


def passes_holdout_gate(metrics: dict) -> dict:
    """Stage 7D2.1's holdout decision gate — every required metric must independently pass.

    Thresholds (HOLDOUT_MIN_*) are fixed constants recorded before any holdout run and never
    adjusted after seeing results. exact_claim_set_match_rate is reported but not gated on.
    Returns a dict of {check_name: bool} plus "passed": overall bool, so a caller can see
    exactly which requirement(s) failed, not just a single opaque True/False.
    """
    checks = {
        "claim_precision": (metrics.get("claim_precision"), HOLDOUT_MIN_PRECISION),
        "claim_recall": (metrics.get("claim_recall"), HOLDOUT_MIN_RECALL),
        "claim_f1": (metrics.get("claim_f1"), HOLDOUT_MIN_F1),
        "negative_claim_preservation_rate": (metrics.get("negative_claim_preservation_rate"), HOLDOUT_MIN_NEGATIVE_PRESERVATION),
        "attribute_claim_accuracy": (metrics.get("attribute_claim_accuracy"), HOLDOUT_MIN_ATTRIBUTE_ACCURACY),
    }
    results = {name: (value is not None and value >= threshold) for name, (value, threshold) in checks.items()}
    results["passed"] = all(results.values())
    return results


def evaluate_gold_fixtures(fixtures: list[dict], extractor_model: str | None = None, base_url: str | None = None) -> dict:
    """Run the fixed extractor over every gold fixture and compute fidelity metrics."""
    fixtures_by_id = {f["id"]: f for f in fixtures}
    fixture_results = [evaluate_fixture(f, extractor_model=extractor_model, base_url=base_url) for f in fixtures]
    metrics = aggregate_fidelity_metrics(fixture_results, fixtures_by_id)
    return {
        "fixture_results": fixture_results,
        "metrics": metrics,
        "error_counts": aggregate_error_counts(fixture_results),
        "gate_passed": passes_decision_gate(metrics),
        "holdout_gate": passes_holdout_gate(metrics),
    }
