"""Stage 7D2 tests: deterministic gold-claim matching, extractor fidelity metrics,
resumable full-run state, claim recovery / grounding-failure preservation / method
disagreement, and grouped decoupled metrics. Fully offline — no Ollama required.
"""

import json
from pathlib import Path
from unittest.mock import patch

from meva.ai.ollama_client import ChatResponse, RunMetrics
from meva.benchmark.models import BenchmarkResult
from meva.extraction.extractor import run_decoupled_case
from meva.extraction.fidelity import (
    aggregate_fidelity_metrics,
    claim_key,
    evaluate_fixture,
    match_claims,
    passes_decision_gate,
)
from meva.extraction.metrics import (
    claim_recovery,
    find_grounding_failure_preservation,
    find_method_disagreements,
    group_decoupled_metrics,
)
from meva.extraction.models import DecoupledCaseResult
from meva.extraction.run_state import ExtractionRunState, IncompatibleResumeError, source_report_hash
from meva.verification.models import MedicalClaim

RICH_PATIENT_ID = "080b069b-5108-46b6-ecef-6aacd3b9ef3f"
GOLD_FIXTURES_PATH = Path(__file__).resolve().parent.parent / "data" / "extraction" / "gold_fixtures.json"


def _claim(**kw):
    base = dict(text="t", patient_id=RICH_PATIENT_ID, category="allergy", value="Fish", assertion="present")
    base.update(kw)
    return MedicalClaim(**base)


def _mock_chat_returning(claims, schema_parsed=True):
    content = json.dumps({"claims": claims}) if schema_parsed else "not json"
    return ChatResponse(message={"role": "assistant", "content": content}, metrics=RunMetrics(total_duration=1_000_000_000))


# --- 1. deterministic gold claim matching -----------------------------------

def test_claim_key_is_deterministic_and_normalized():
    a = _claim(value="Fish (substance)")
    b = _claim(value="fish  (substance)")  # different case/whitespace
    assert claim_key(a) == claim_key(b)


# --- 2. exact claim-set match ------------------------------------------------

def test_exact_claim_set_match_true_when_identical():
    gold = [_claim(value="Fish")]
    extracted = [_claim(value="Fish")]
    result = match_claims(gold, extracted)
    assert result["exact_claim_set_match"] is True


def test_exact_claim_set_match_false_on_any_difference():
    gold = [_claim(value="Fish")]
    extracted = [_claim(value="Fish"), _claim(value="Peanut")]
    result = match_claims(gold, extracted)
    assert result["exact_claim_set_match"] is False


# --- 3-4. claim precision / recall -------------------------------------------

def test_claim_precision_and_recall_with_partial_overlap():
    gold = [_claim(value="Fish"), _claim(value="Peanut")]
    extracted = [_claim(value="Fish"), _claim(value="Shellfish")]  # 1 TP, 1 FP, 1 FN
    fixtures_by_id = {"f1": {"expected_claims": [c.model_dump() for c in gold]}}
    result = {"fixture_id": "f1", "schema_parsed": True, "extraction_error": None,
              **match_claims(gold, extracted),
              "gold_claims": [c.model_dump() for c in gold], "extracted_claims": [c.model_dump() for c in extracted]}
    metrics = aggregate_fidelity_metrics([result], fixtures_by_id)
    assert metrics["claim_precision"] == 0.5  # 1 TP / (1 TP + 1 FP)
    assert metrics["claim_recall"] == 0.5  # 1 TP / (1 TP + 1 FN)


# --- 5. claim F1 -------------------------------------------------------------

def test_claim_f1_computed_from_precision_and_recall():
    gold = [_claim(value="Fish")]
    extracted = [_claim(value="Fish")]
    fixtures_by_id = {"f1": {"expected_claims": [c.model_dump() for c in gold]}}
    result = {"fixture_id": "f1", "schema_parsed": True, "extraction_error": None,
              **match_claims(gold, extracted),
              "gold_claims": [c.model_dump() for c in gold], "extracted_claims": [c.model_dump() for c in extracted]}
    metrics = aggregate_fidelity_metrics([result], fixtures_by_id)
    assert metrics["claim_f1"] == 1.0


def test_claim_f1_none_when_precision_or_recall_is_zero_denominator():
    fixtures_by_id = {"f1": {"expected_claims": []}}
    result = {"fixture_id": "f1", "schema_parsed": True, "extraction_error": None,
              **match_claims([], []), "gold_claims": [], "extracted_claims": []}
    metrics = aggregate_fidelity_metrics([result], fixtures_by_id)
    assert metrics["claim_precision"] is None
    assert metrics["claim_recall"] is None
    assert metrics["claim_f1"] is None


# --- 6-7. added / missed claim calculation -----------------------------------

def test_added_claim_rate_uses_false_positives_over_extracted_total():
    gold = [_claim(value="Fish")]
    extracted = [_claim(value="Fish"), _claim(value="Peanut")]  # 1 TP, 1 FP
    fixtures_by_id = {"f1": {"expected_claims": [c.model_dump() for c in gold]}}
    result = {"fixture_id": "f1", "schema_parsed": True, "extraction_error": None,
              **match_claims(gold, extracted),
              "gold_claims": [c.model_dump() for c in gold], "extracted_claims": [c.model_dump() for c in extracted]}
    metrics = aggregate_fidelity_metrics([result], fixtures_by_id)
    assert metrics["added_claim_rate"] == 0.5  # 1 FP / 2 extracted


def test_missed_claim_rate_uses_false_negatives_over_gold_total():
    gold = [_claim(value="Fish"), _claim(value="Peanut")]
    extracted = [_claim(value="Fish")]  # 1 TP, 1 FN
    fixtures_by_id = {"f1": {"expected_claims": [c.model_dump() for c in gold]}}
    result = {"fixture_id": "f1", "schema_parsed": True, "extraction_error": None,
              **match_claims(gold, extracted),
              "gold_claims": [c.model_dump() for c in gold], "extracted_claims": [c.model_dump() for c in extracted]}
    metrics = aggregate_fidelity_metrics([result], fixtures_by_id)
    assert metrics["missed_claim_rate"] == 0.5  # 1 FN / 2 gold


# --- 8. negative assertion preservation --------------------------------------

def test_negative_claim_preservation_rate():
    gold = [_claim(category="allergy", value=None, assertion="absent")]
    extracted = [_claim(category="allergy", value=None, assertion="absent")]
    fixtures_by_id = {"f1": {"expected_claims": [c.model_dump() for c in gold]}}
    result = {"fixture_id": "f1", "schema_parsed": True, "extraction_error": None,
              **match_claims(gold, extracted),
              "gold_claims": [c.model_dump() for c in gold], "extracted_claims": [c.model_dump() for c in extracted]}
    metrics = aggregate_fidelity_metrics([result], fixtures_by_id)
    assert metrics["negative_claim_preservation_rate"] == 1.0


def test_negative_claim_dropped_lowers_preservation_rate():
    gold = [_claim(category="allergy", value=None, assertion="absent")]
    extracted = []  # extractor dropped the negative claim entirely
    fixtures_by_id = {"f1": {"expected_claims": [c.model_dump() for c in gold]}}
    result = {"fixture_id": "f1", "schema_parsed": True, "extraction_error": None,
              **match_claims(gold, extracted),
              "gold_claims": [c.model_dump() for c in gold], "extracted_claims": []}
    metrics = aggregate_fidelity_metrics([result], fixtures_by_id)
    assert metrics["negative_claim_preservation_rate"] == 0.0


# --- 9. attribute claim comparison -------------------------------------------

def test_attribute_claim_accuracy():
    gold = [_claim(assertion="attribute", value="Fish", attribute="criticality", attribute_value="high")]
    extracted = [_claim(assertion="attribute", value="Fish", attribute="criticality", attribute_value="high")]
    fixtures_by_id = {"f1": {"expected_claims": [c.model_dump() for c in gold]}}
    result = {"fixture_id": "f1", "schema_parsed": True, "extraction_error": None,
              **match_claims(gold, extracted),
              "gold_claims": [c.model_dump() for c in gold], "extracted_claims": [c.model_dump() for c in extracted]}
    metrics = aggregate_fidelity_metrics([result], fixtures_by_id)
    assert metrics["attribute_claim_accuracy"] == 1.0


def test_attribute_claim_wrong_value_counts_as_inaccurate():
    gold = [_claim(assertion="attribute", value="Fish", attribute="criticality", attribute_value="high")]
    extracted = [_claim(assertion="attribute", value="Fish", attribute="criticality", attribute_value="low")]
    fixtures_by_id = {"f1": {"expected_claims": [c.model_dump() for c in gold]}}
    result = {"fixture_id": "f1", "schema_parsed": True, "extraction_error": None,
              **match_claims(gold, extracted),
              "gold_claims": [c.model_dump() for c in gold], "extracted_claims": [c.model_dump() for c in extracted]}
    metrics = aggregate_fidelity_metrics([result], fixtures_by_id)
    assert metrics["attribute_claim_accuracy"] == 0.0


# --- 10. wrong answer not repaired -------------------------------------------

def test_extractor_gold_fixture_wrong_answer_not_repaired():
    fixtures = {f["id"]: f for f in json.loads(GOLD_FIXTURES_PATH.read_text())}
    fixture = fixtures["observation-absence"]
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning(fixture["expected_claims"])):
        result = evaluate_fixture(fixture)
    assert result["extracted_claims"][0]["assertion"] == "absent"
    assert result["true_positive_claims"] >= 1


# --- 11. zero-gold-claim fixture handling ------------------------------------

def test_zero_gold_claim_fixture_handled_safely():
    fixtures = {f["id"]: f for f in json.loads(GOLD_FIXTURES_PATH.read_text())}
    fixture = fixtures["no-factual-claim"]
    assert fixture["expected_claims"] == []
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning([])):
        result = evaluate_fixture(fixture)
    assert result["gold_claim_count"] == 0
    assert result["false_negative_claims"] == 0
    assert result["exact_claim_set_match"] is True


def test_decision_gate_passes_and_fails_correctly():
    assert passes_decision_gate({"claim_precision": 0.9, "claim_recall": 0.9}) is True
    assert passes_decision_gate({"claim_precision": 0.5, "claim_recall": 0.9}) is False
    assert passes_decision_gate({"claim_precision": None, "claim_recall": None}) is False


# --- 12. resume persistence ---------------------------------------------------

def test_resume_persistence_saves_after_each_answer(tmp_path):
    state = ExtractionRunState.load_or_create(
        "run1", "hash123", "qwen3:4b", "digest123", ["qwen3:4b"], ["c1", "c2"], {"temperature": 0}, runs_dir=tmp_path,
    )
    state.record("qwen3:4b", "c1", {"case_id": "c1"})
    assert (tmp_path / "run1.json").exists()

    reloaded = ExtractionRunState.load_or_create(
        "run1", "hash123", "qwen3:4b", "digest123", ["qwen3:4b"], ["c1", "c2"], {"temperature": 0}, runs_dir=tmp_path,
    )
    assert reloaded.is_done("qwen3:4b", "c1")
    assert not reloaded.is_done("qwen3:4b", "c2")


# --- 13. incompatible resume rejection ----------------------------------------

def test_incompatible_resume_rejected_on_hash_mismatch(tmp_path):
    ExtractionRunState.load_or_create("run1", "hash123", "qwen3:4b", "digestA", ["qwen3:4b"], ["c1"], {"temperature": 0}, runs_dir=tmp_path)
    try:
        ExtractionRunState.load_or_create("run1", "DIFFERENT_HASH", "qwen3:4b", "digestA", ["qwen3:4b"], ["c1"], {"temperature": 0}, runs_dir=tmp_path)
        assert False, "expected IncompatibleResumeError"
    except IncompatibleResumeError:
        pass


def test_incompatible_resume_rejected_on_extractor_digest_mismatch(tmp_path):
    ExtractionRunState.load_or_create("run1", "hash123", "qwen3:4b", "digestA", ["qwen3:4b"], ["c1"], {"temperature": 0}, runs_dir=tmp_path)
    try:
        ExtractionRunState.load_or_create("run1", "hash123", "qwen3:4b", "digestB", ["qwen3:4b"], ["c1"], {"temperature": 0}, runs_dir=tmp_path)
        assert False, "expected IncompatibleResumeError"
    except IncompatibleResumeError:
        pass


def test_source_report_hash_is_deterministic(tmp_path):
    f = tmp_path / "report.json"
    f.write_text('{"a": 1}')
    h1 = source_report_hash(f)
    h2 = source_report_hash(f)
    assert h1 == h2 and len(h1) == 64


# --- 14. 104 saved source answers loaded correctly ----------------------------

def test_all_agent_case_results_loaded_from_saved_report():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
    from run_decoupled_full import load_all_agent_answers  # noqa: E402

    source = Path(__file__).resolve().parent.parent / "results" / "comparisons" / "comparison-v0.3-full-20260815-230131-corrected.json"
    if not source.exists():
        return  # environment without the saved Stage 7C2 report; skip silently, no Ollama needed either way
    by_model = load_all_agent_answers(source)
    assert sum(len(v) for v in by_model.values()) == 104
    assert len(by_model.get("qwen3:4b", [])) == 52
    assert len(by_model.get("llama3.2:3b", [])) == 52


# --- 15. original source claims ignored ---------------------------------------

def test_decoupled_ignores_source_models_original_structured_claims():
    with patch("meva.extraction.extractor.OllamaClient.chat", return_value=_mock_chat_returning(
        [{"text": "t", "patient_id": RICH_PATIENT_ID, "category": "allergy", "value": "Fish (substance)", "assertion": "present"}]
    )):
        decoupled = run_decoupled_case(
            case_id="allergy-01", category="allergy", difficulty="simple", patient_id=RICH_PATIENT_ID,
            source_model="qwen3:4b", question="q", answer_text="Fish allergy recorded.",
        )
    # run_decoupled_case's signature has no parameter for the source model's original claims at all.
    import inspect
    assert "original_claims" not in inspect.signature(run_decoupled_case).parameters
    assert decoupled.extraction_result.claims[0].value == "Fish (substance)"


# --- 16. claim recovery count --------------------------------------------------

def _e2e(**kw):
    base = dict(case_id="c1", category="medication", case_type="AGENT", difficulty="simple",
                patient_id=RICH_PATIENT_ID, question="q", status="passed",
                structured_claim_validity_rate=0.0, total_emitted_claims=4, zero_claim=False,
                supported=0, contradicted=0, unsupported=0, unverifiable=4, answer="losartan potassium is recorded.")
    base.update(kw)
    return BenchmarkResult(**base)


def _decoupled(case_id="c1", claims=None):
    claims = claims if claims is not None else [_claim(category="medication", value="losartan potassium")]
    from meva.verification.verifier import build_report
    report = build_report("losartan potassium is recorded.", claims)
    from meva.extraction.models import ExtractionResult
    extraction = ExtractionResult(answer_text="losartan potassium is recorded.", claims=claims, total_raw_claims=len(claims),
                                   schema_parsed=True, model="qwen3:4b")
    return DecoupledCaseResult(
        case_id=case_id, category="medication", difficulty="simple", patient_id=RICH_PATIENT_ID,
        source_model="llama3.2:3b", original_question="q", original_natural_language_answer="losartan potassium is recorded.",
        extractor_model="qwen3:4b", extraction_result=extraction, verification_report=report.model_dump(),
        supported=report.summary.supported, contradicted=report.summary.contradicted,
        unsupported=report.summary.unsupported, unverifiable=report.summary.unverifiable,
        evidence_grounding_score=report.summary.grounding_score, total_emitted_claims=len(claims),
    )


def test_claim_recovery_count_when_e2e_had_invalid_claims_but_decoupled_recovered():
    e2e = [_e2e(case_id="medication-01")]
    decoupled = [_decoupled(case_id="medication-01")]
    result = claim_recovery(e2e, decoupled)
    assert result["claim_recovery_count"] == 1
    assert "medication-01" in result["recovered_case_ids"]


def test_claim_recovery_not_counted_when_e2e_already_had_valid_claims():
    e2e = [_e2e(case_id="c1", structured_claim_validity_rate=1.0, zero_claim=False, unverifiable=0, supported=1)]
    decoupled = [_decoupled(case_id="c1")]
    result = claim_recovery(e2e, decoupled)
    assert result["claim_recovery_count"] == 0


# --- 17. grounding-failure preservation ----------------------------------------

def test_grounding_failure_preserved_across_both_methods():
    e2e = [_e2e(case_id="observation-01", contradicted=1, supported=0)]
    decoupled = [_decoupled(case_id="observation-01", claims=[
        _claim(category="observation", value="Blood Pressure", assertion="absent"),
    ])]
    # RICH_PATIENT_ID has a real recorded BP, so this "absent" claim is genuinely CONTRADICTED
    preserved = find_grounding_failure_preservation(e2e, decoupled)
    assert len(preserved) == 1
    assert preserved[0]["case_id"] == "observation-01"


# --- 18. method-disagreement classification -------------------------------------

def test_method_disagreement_classified_as_zero_original_claims():
    e2e = [_e2e(case_id="medication-01", zero_claim=True, structured_claim_validity_rate=None,
                 total_emitted_claims=0, unverifiable=0, supported=0)]
    decoupled = [_decoupled(case_id="medication-01")]
    disagreements = find_method_disagreements(e2e, decoupled)
    assert len(disagreements) == 1
    assert disagreements[0]["cause"] == "zero original claims"
    assert disagreements[0]["end_to_end_outcome"] == "NONE"
    assert disagreements[0]["decoupled_outcome"] == "SUPPORTED"


def test_no_disagreement_when_outcomes_match():
    e2e = [_e2e(case_id="c1", supported=1, unverifiable=0, structured_claim_validity_rate=1.0)]
    decoupled = [_decoupled(case_id="c1")]
    disagreements = find_method_disagreements(e2e, decoupled)
    assert disagreements == []


# --- 19. grouped decoupled metrics ----------------------------------------------

def test_grouped_decoupled_metrics_include_n():
    decoupled = [_decoupled(case_id="c1"), _decoupled(case_id="c2")]
    grouped = group_decoupled_metrics(decoupled, lambda r: r.category)
    assert grouped["medication"]["n"] == 2
