"""MEVA's Evidence Grounding Score.

This is an engineering/research metric describing how well an AI
answer's claims are grounded in the actual retrieved FHIR evidence.
It is NOT a clinical accuracy, safety, or diagnostic score — MEVA has
not been clinically validated. See docs/evidence-verification.md.

Formula:
    verifiable_claims = supported + contradicted + unsupported
    (UNVERIFIABLE claims are excluded from the denominator entirely)

    grounding_score = supported / verifiable_claims, as a percentage

    If verifiable_claims == 0, the score is "N/A" (never divide by zero,
    never invent a number).
"""

from meva.verification.models import ClaimVerification, VerificationSummary


def summarize(verifications: list[ClaimVerification]) -> VerificationSummary:
    supported = sum(1 for v in verifications if v.status == "SUPPORTED")
    contradicted = sum(1 for v in verifications if v.status == "CONTRADICTED")
    unsupported = sum(1 for v in verifications if v.status == "UNSUPPORTED")
    unverifiable = sum(1 for v in verifications if v.status == "UNVERIFIABLE")

    verifiable = supported + contradicted + unsupported

    if verifiable == 0:
        score = "N/A"
    else:
        score = f"{round(100 * supported / verifiable)}%"

    return VerificationSummary(
        verifiable_claims=verifiable,
        supported=supported,
        contradicted=contradicted,
        unsupported=unsupported,
        unverifiable=unverifiable,
        grounding_score=score,
    )
