"""Data structures for MEVA's evidence verification layer.

Everything here is plain data (Pydantic models) — no verification logic
lives in this file. See verifier.py for the actual rules.
"""

from pydantic import BaseModel, Field

# Claim categories MEVA currently knows how to verify.
CLAIM_CATEGORIES = ("patient", "allergy", "medication", "condition", "observation", "encounter")

# What kind of statement a claim is making.
# - "present": claims something specific exists (value is required)
# - "absent": claims nothing of this category is recorded
# - "value": claims a specific recorded value (e.g. an exact observation reading)
# - "attribute": claims a specific metadata field of an already-identified item (e.g. an
#   allergy's criticality, a medication's status). Requires `value` (which item), `attribute`
#   (the field name), and `attribute_value` (the claimed value of that field). Added in Stage
#   7B.5 — see docs/evidence-verification.md for why this exists.
# - "interpretation": a clinical judgement/opinion about the evidence (e.g. "this is dangerous") —
#   MEVA never verifies these; they are always UNVERIFIABLE by design.
CLAIM_ASSERTIONS = ("present", "absent", "value", "attribute", "interpretation")

VERIFICATION_STATUSES = ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED", "UNVERIFIABLE")


class MedicalClaim(BaseModel):
    """One factual statement to check against a patient's retrieved FHIR evidence."""

    text: str
    patient_id: str
    category: str
    value: str | None = None
    assertion: str

    # Only used when assertion == "attribute": which metadata field, and what value it's
    # claimed to have (e.g. attribute="criticality", attribute_value="low").
    attribute: str | None = None
    attribute_value: str | None = None


class EvidenceFact(BaseModel):
    """One piece of evidence, built only from a real, successful MEVA tool result."""

    evidence_id: str
    patient_id: str
    category: str
    value: str
    source_tool: str
    resource_id: str | None = None

    # Extra metadata fields already returned by MEVA's tool output for this fact
    # (e.g. an allergy's criticality/clinical_status). Only ever populated from
    # real tool output — never fabricated. Added in Stage 7B.5.
    attributes: dict[str, str] = Field(default_factory=dict)


class EvidenceReference(BaseModel):
    """A trimmed-down pointer to an EvidenceFact, attached to a verification result for provenance."""

    evidence_id: str
    source_tool: str
    resource_id: str | None = None
    value: str

    @classmethod
    def from_fact(cls, fact: EvidenceFact) -> "EvidenceReference":
        return cls(
            evidence_id=fact.evidence_id,
            source_tool=fact.source_tool,
            resource_id=fact.resource_id,
            value=fact.value,
        )


class ClaimVerification(BaseModel):
    """The verdict for one claim, plus the evidence that produced it."""

    claim: MedicalClaim
    status: str
    evidence: list[EvidenceReference] = Field(default_factory=list)
    reason: str


class VerificationSummary(BaseModel):
    """Counts and the Evidence Grounding Score for a full report."""

    verifiable_claims: int
    supported: int
    contradicted: int
    unsupported: int
    unverifiable: int
    grounding_score: str  # e.g. "75%" or "N/A"


class VerificationReport(BaseModel):
    """The full result of verifying an AI answer's claims against retrieved evidence."""

    answer: str
    claims: list[ClaimVerification]
    summary: VerificationSummary


class AgentAnswer(BaseModel):
    """The local model's final, structured response: a human-readable answer plus its claims."""

    answer: str
    claims: list[MedicalClaim] = Field(default_factory=list)
