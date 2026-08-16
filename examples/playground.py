"""MEVA Public Verifier Playground (Stage 8B) — v0.4 public synthetic patients only.

Lets anyone explore MEVA's deterministic evidence verifier directly: pick a
public synthetic patient, state a claim (category/assertion/value), and see
the exact SUPPORTED/CONTRADICTED/UNSUPPORTED/UNVERIFIABLE verdict — with the
real evidence (or lack of it) that produced it.

This is a demonstration of DETERMINISTIC VERIFICATION ONLY. It never calls
any AI model (no qwen3:4b, no llama3.2:3b, no local or cloud inference of
any kind) — every claim you type is checked by plain Python against real,
on-disk FHIR data for MEVA's public synthetic patients (see
data/synthetic/synthea/PROVENANCE.md). No real patient data is used or
accepted. This is a research/engineering demo, not a medical tool — it does
not diagnose, does not recommend treatment, and its verdicts describe
whether a STATEMENT matches RECORDED DATA, never whether that data or
statement is medically correct.

The reusable logic behind this CLI lives in meva.playground.service — the
same functions back the Stage 8C browser sandbox (streamlit_app.py), so
neither duplicates the other.

Usage:
    python3 examples/playground.py list-patients
    python3 examples/playground.py describe-patient <patient_id>
    python3 examples/playground.py verify --patient-id <id> --category allergy --assertion present --value "Peanut"
    python3 examples/playground.py demo
"""

import argparse
import json

from meva.playground import build_ready_made_examples, describe_patient, list_patients, verify_claim
from meva.verification.models import CLAIM_ASSERTIONS, CLAIM_CATEGORIES


def _print_result(result: dict) -> None:
    print(json.dumps(result, indent=2))


def run_demo() -> list[dict]:
    """Run every ready-made example (discovered live from current v0.4 fixtures — see
    meva.playground.service.build_ready_made_examples) through the real verifier."""
    results = []
    for example in build_ready_made_examples():
        result = verify_claim(
            example["patient_id"], example["category"], example["assertion"],
            value=example["value"], attribute=example["attribute"], attribute_value=example["attribute_value"],
            text=example["description"],
        )
        print(f"\n=== {example['label']} ===")
        _print_result(result)
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description="MEVA Public Verifier Playground (v0.4 public synthetic patients only, no AI inference).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-patients", help="List public synthetic patients available in the playground")

    describe_parser = subparsers.add_parser("describe-patient", help="Summarize one public patient's recorded data")
    describe_parser.add_argument("patient_id")

    verify_parser = subparsers.add_parser("verify", help="Verify one claim deterministically against real data")
    verify_parser.add_argument("--patient-id", required=True)
    verify_parser.add_argument("--category", required=True, choices=CLAIM_CATEGORIES)
    verify_parser.add_argument("--assertion", required=True, choices=CLAIM_ASSERTIONS)
    verify_parser.add_argument("--value", default=None)
    verify_parser.add_argument("--attribute", default=None)
    verify_parser.add_argument("--attribute-value", default=None)
    verify_parser.add_argument("--text", default=None)

    subparsers.add_parser("demo", help="Run every ready-made example (SUPPORTED/CONTRADICTED/UNSUPPORTED/UNVERIFIABLE/observation/attribute)")

    args = parser.parse_args()

    if args.command == "list-patients":
        _print_result({"patients": list_patients()})
    elif args.command == "describe-patient":
        _print_result(describe_patient(args.patient_id))
    elif args.command == "verify":
        result = verify_claim(
            args.patient_id, args.category, args.assertion, value=args.value,
            attribute=args.attribute, attribute_value=args.attribute_value, text=args.text,
        )
        _print_result(result)
    elif args.command == "demo":
        run_demo()


if __name__ == "__main__":
    main()
