"""Deterministic verification of MedicalClaims against a real EvidenceLedger.

This is the heart of MEVA: an LLM never gets to decide whether its own
answer was correct. Every verdict here is produced by plain Python
comparisons against evidence that was actually retrieved by MEVA's
existing tools.
"""

from meva.verification.evidence import EvidenceLedger, PatientNotFoundError, build_ledger
from meva.verification.models import ClaimVerification, EvidenceReference, MedicalClaim, VerificationReport
from meva.verification.normalizer import values_match
from meva.verification.scoring import summarize

PRESENCE_CATEGORIES = ("allergy", "medication", "condition")


def _unverifiable(claim: MedicalClaim, reason: str) -> ClaimVerification:
    return ClaimVerification(claim=claim, status="UNVERIFIABLE", evidence=[], reason=reason)


def _verify_presence_category(claim: MedicalClaim, ledger: EvidenceLedger) -> ClaimVerification:
    if not ledger.was_retrieved(claim.category):
        return _unverifiable(claim, f"MEVA did not retrieve {claim.category} evidence for this patient.")

    facts = ledger.facts_for(claim.category)

    if claim.assertion == "absent":
        if len(facts) == 0:
            return ClaimVerification(
                claim=claim, status="SUPPORTED", evidence=[],
                reason=f"No {claim.category} evidence is recorded for this patient, matching the claim.",
            )
        return ClaimVerification(
            claim=claim, status="CONTRADICTED",
            evidence=[EvidenceReference.from_fact(f) for f in facts],
            reason=f"{len(facts)} {claim.category} record(s) were found, contradicting the 'absent' claim.",
        )

    if claim.assertion in ("present", "value"):
        if not claim.value:
            return _unverifiable(claim, "A 'present'/'value' claim needs a value to check against evidence.")

        matches = [f for f in facts if values_match(claim.value, f.value)]
        if matches:
            return ClaimVerification(
                claim=claim, status="SUPPORTED",
                evidence=[EvidenceReference.from_fact(f) for f in matches],
                reason=f"Matching {claim.category} evidence was found for '{claim.value}'.",
            )
        return ClaimVerification(
            claim=claim, status="UNSUPPORTED",
            evidence=[],
            reason=f"No {claim.category} evidence matching '{claim.value}' was found in the retrieved records.",
        )

    return _unverifiable(claim, f"Unrecognized assertion '{claim.assertion}' for category '{claim.category}'.")


def _verify_observation(claim: MedicalClaim, ledger: EvidenceLedger) -> ClaimVerification:
    if not ledger.was_retrieved("observation"):
        return _unverifiable(claim, "MEVA did not retrieve observation evidence for this patient.")

    facts = ledger.facts_for("observation")

    if claim.assertion == "value":
        if not claim.value:
            return _unverifiable(claim, "A 'value' observation claim needs a value to check against evidence.")

        matches = [f for f in facts if values_match(claim.value, f.value)]
        if matches:
            return ClaimVerification(
                claim=claim, status="SUPPORTED",
                evidence=[EvidenceReference.from_fact(f) for f in matches],
                reason=f"Matching observation evidence was found for '{claim.value}'.",
            )
        return ClaimVerification(
            claim=claim, status="UNSUPPORTED", evidence=[],
            reason=f"No recorded observation matches '{claim.value}'.",
        )

    if claim.assertion == "absent":
        if len(facts) == 0:
            return ClaimVerification(claim=claim, status="SUPPORTED", evidence=[], reason="No observations are recorded for this patient.")
        return ClaimVerification(
            claim=claim, status="CONTRADICTED",
            evidence=[EvidenceReference.from_fact(f) for f in facts],
            reason=f"{len(facts)} observation(s) were found, contradicting the 'absent' claim.",
        )

    return _unverifiable(claim, "MEVA does not verify clinical interpretations of observations, only recorded values.")


def _verify_patient(claim: MedicalClaim, ledger: EvidenceLedger) -> ClaimVerification:
    if not ledger.was_retrieved("patient"):
        return _unverifiable(claim, "MEVA did not retrieve patient demographic evidence.")

    if claim.assertion not in ("present", "value"):
        return _unverifiable(claim, "MEVA only verifies specific demographic values (name, gender, birth date), not absence claims.")

    if not claim.value:
        return _unverifiable(claim, "A patient claim needs a value (e.g. a name, gender, or birth date) to check.")

    facts = ledger.facts_for("patient")
    matches = [f for f in facts if values_match(claim.value, f.value)]
    if matches:
        return ClaimVerification(
            claim=claim, status="SUPPORTED",
            evidence=[EvidenceReference.from_fact(f) for f in matches],
            reason=f"Matching patient evidence was found for '{claim.value}'.",
        )
    return ClaimVerification(
        claim=claim, status="UNSUPPORTED", evidence=[],
        reason=f"No recorded patient demographic matches '{claim.value}'.",
    )


def _verify_attribute(claim: MedicalClaim, ledger: EvidenceLedger) -> ClaimVerification:
    """Verify a claim about a metadata field of an already-identified item.

    e.g. category="allergy", value="Fish", attribute="criticality", attribute_value="low".
    Added in Stage 7B.5 so factually correct metadata claims (criticality, clinical
    status, medication status/intent, ...) aren't wrongly scored UNSUPPORTED just
    because the verifier previously only checked an item's primary name/value.
    """
    if not claim.value or not claim.attribute or not claim.attribute_value:
        return _unverifiable(claim, "An 'attribute' claim needs value, attribute, and attribute_value all set.")

    if not ledger.was_retrieved(claim.category):
        return _unverifiable(claim, f"MEVA did not retrieve {claim.category} evidence for this patient.")

    facts = ledger.facts_for(claim.category)
    matches = [f for f in facts if values_match(claim.value, f.value)]

    if not matches:
        return ClaimVerification(
            claim=claim, status="UNSUPPORTED", evidence=[],
            reason=f"No {claim.category} evidence matching '{claim.value}' was found, so its '{claim.attribute}' can't be checked.",
        )

    recorded_values = {m.attributes[claim.attribute] for m in matches if claim.attribute in m.attributes}

    if not recorded_values:
        return _unverifiable(
            claim, f"MEVA has no '{claim.attribute}' field recorded for this {claim.category} — cannot verify."
        )

    if any(values_match(claim.attribute_value, recorded) for recorded in recorded_values):
        return ClaimVerification(
            claim=claim, status="SUPPORTED",
            evidence=[EvidenceReference.from_fact(m) for m in matches if claim.attribute in m.attributes],
            reason=f"Recorded {claim.attribute} for '{claim.value}' matches '{claim.attribute_value}'.",
        )

    return ClaimVerification(
        claim=claim, status="CONTRADICTED",
        evidence=[EvidenceReference.from_fact(m) for m in matches if claim.attribute in m.attributes],
        reason=(
            f"Recorded {claim.attribute} for '{claim.value}' is {sorted(recorded_values)}, "
            f"which contradicts the claimed '{claim.attribute_value}'."
        ),
    )


def verify_claim(claim: MedicalClaim, ledger: EvidenceLedger | None) -> ClaimVerification:
    """Verify one claim. `ledger` is None when the patient could not be found."""
    if ledger is None:
        return _unverifiable(claim, "The referenced patient was not found, so this claim cannot be verified.")

    if claim.assertion == "interpretation":
        return _unverifiable(claim, "MEVA does not verify clinical interpretations or opinions, only recorded facts.")

    if claim.assertion == "attribute":
        return _verify_attribute(claim, ledger)

    if claim.category == "observation":
        return _verify_observation(claim, ledger)
    if claim.category == "patient":
        return _verify_patient(claim, ledger)
    if claim.category in PRESENCE_CATEGORIES:
        return _verify_presence_category(claim, ledger)
    if claim.category == "encounter":
        return _verify_presence_category(claim, ledger)

    return _unverifiable(claim, f"MEVA does not yet verify claims in category '{claim.category}'.")


def build_report(answer: str, claims: list[MedicalClaim]) -> VerificationReport:
    """Verify every claim against real, freshly retrieved evidence and build a full report.

    Each claim's patient_id is looked up independently, so claims about
    different patients (or an unknown patient) are each handled correctly.
    """
    ledgers: dict[str, EvidenceLedger | None] = {}

    def ledger_for(patient_id: str) -> EvidenceLedger | None:
        if patient_id not in ledgers:
            try:
                ledgers[patient_id] = build_ledger(patient_id)
            except PatientNotFoundError:
                ledgers[patient_id] = None
        return ledgers[patient_id]

    verifications = [verify_claim(claim, ledger_for(claim.patient_id)) for claim in claims]
    summary = summarize(verifications)
    return VerificationReport(answer=answer, claims=verifications, summary=summary)
