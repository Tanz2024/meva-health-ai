"""Stage 8B — historical-skip audit.

Every currently-skipped test in this suite was skipped for exactly one
reason: Stage 8A.1 removed the former (unlicensed-provenance) patient
set, so a handful of tests that live-validated that specific historical
data can no longer run. This test scans the actual collected skip markers
(via pytest's own session, not source-text grepping — so it can't miss a
dynamically-applied mark) and asserts every one of them states that reason
explicitly, so a skip can never quietly become a place to hide an
unrelated failure.
"""

EXPECTED_SKIP_KEYWORDS = ("historical", "8a.1", "removed")


def test_skip_reasons_all_reference_the_stage_8a1_data_removal(request):
    skip_reasons = []
    for item in request.session.items:
        for mark in item.iter_markers(name="skip"):
            reason = (mark.kwargs.get("reason") or (mark.args[0] if mark.args else "")).lower()
            skip_reasons.append((item.nodeid, reason))

    assert skip_reasons, (
        "expected at least one skipped test in the suite "
        "(see tests/test_benchmark_validator.py, tests/test_observation_audit.py)"
    )

    for nodeid, reason in skip_reasons:
        assert reason, f"{nodeid}: skip has no reason at all"
        assert any(keyword in reason for keyword in EXPECTED_SKIP_KEYWORDS), (
            f"{nodeid}: skip reason does not reference the Stage 8A.1 historical data "
            f"removal — reason was: {reason!r}"
        )
