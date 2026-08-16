"""MEVA's deterministic evidence verification layer.

Turns an AI-produced list of MedicalClaim objects into a VerificationReport
by checking them against real evidence retrieved through MEVA's existing
FHIR/MCP tools. The verification logic here is plain Python — no LLM is
ever asked whether its own answer was correct.
"""

from meva.verification.evidence import EvidenceLedger, PatientNotFoundError, build_ledger
from meva.verification.models import (
    AgentAnswer,
    ClaimVerification,
    EvidenceFact,
    EvidenceReference,
    MedicalClaim,
    VerificationReport,
    VerificationSummary,
)
from meva.verification.verifier import build_report, verify_claim

__all__ = [
    "AgentAnswer",
    "MedicalClaim",
    "EvidenceFact",
    "EvidenceReference",
    "ClaimVerification",
    "VerificationSummary",
    "VerificationReport",
    "EvidenceLedger",
    "PatientNotFoundError",
    "build_ledger",
    "verify_claim",
    "build_report",
]
