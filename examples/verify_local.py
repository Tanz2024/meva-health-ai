"""Ask MEVA's local AI a question, then deterministically verify its claims.

Usage:
    python3 examples/verify_local.py "What allergies are recorded for patient <id>?"

Requires a running local Ollama server (see docs/local-ai.md). This is
the full MEVA pipeline: local model -> structured claims -> deterministic
verification against real retrieved evidence -> Evidence Grounding Score.
"""

import sys

from meva.ai.agent import run_agent
from meva.ai.ollama_client import model_name
from meva.verification import build_report


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 examples/verify_local.py "your question"')
        sys.exit(1)

    question = sys.argv[1]

    print("MEVA — Medical Evidence Verification Agent\n")
    print(f"Model:\n{model_name()}\n")
    print(f"Question:\n{question}\n")

    result = run_agent(question)
    print(f"AI Answer:\n{result['answer']}\n")

    report = build_report(result["answer"], result["claims"])

    print("Verification:\n")
    if not report.claims:
        print("(The model's answer did not contain any structured claims to verify.)\n")

    for verification in report.claims:
        print(f"[{verification.status}]")
        print(f"Claim:\n{verification.claim.text}\n")
        if verification.evidence:
            print("Evidence:")
            for ref in verification.evidence:
                print(f"  {ref.source_tool} -> FHIR resource: {ref.resource_id} ({ref.value})")
        print(f"Reason: {verification.reason}\n")

    print(f"Evidence Grounding Score:\n{report.summary.grounding_score}")
    print(
        f"(supported={report.summary.supported}, contradicted={report.summary.contradicted}, "
        f"unsupported={report.summary.unsupported}, unverifiable={report.summary.unverifiable})"
    )


if __name__ == "__main__":
    main()
