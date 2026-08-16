"""Offline demo: proves MEVA catches an incorrect AI claim, without needing Ollama.

Simulates a bad AI answer that says a patient has no recorded allergies,
when the patient's real FHIR evidence contains seven of them. MEVA's
deterministic verifier — not the AI itself — is what catches this.

Usage:
    python3 examples/verify_contradiction_demo.py
"""

from meva.verification import MedicalClaim, build_report

PATIENT_ID = "6895f047-ab31-c293-b335-374256e01eb1"  # has 7 recorded allergies


def main():
    fake_ai_answer = "No allergies are recorded for this patient."
    fake_claim = MedicalClaim(
        text=fake_ai_answer,
        patient_id=PATIENT_ID,
        category="allergy",
        value=None,
        assertion="absent",
    )

    print("MEVA — Intentional Contradiction Demo\n")
    print(f"Fake AI answer (deliberately wrong):\n{fake_ai_answer}\n")

    report = build_report(fake_ai_answer, [fake_claim])
    verification = report.claims[0]

    print(f"MEVA verification result: {verification.status}")
    print(f"Reason: {verification.reason}")
    print("Evidence used:")
    for ref in verification.evidence:
        print(f"  {ref.source_tool} -> {ref.value}")

    assert verification.status == "CONTRADICTED", "MEVA failed to catch the incorrect claim!"
    print("\nMEVA correctly caught the incorrect claim.")


if __name__ == "__main__":
    main()
