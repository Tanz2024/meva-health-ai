"""Maintenance tool: show what evidence is actually available in each synthetic patient.

Use this before writing new benchmark cases, so expected evidence is
always read from the real bundle rather than guessed. Does not
generate questions automatically — a human still decides what to ask.

Usage:
    python3 examples/inspect_benchmark_data.py
    python3 examples/inspect_benchmark_data.py --summary-only
"""

import argparse

from meva.mcp import server


def main():
    parser = argparse.ArgumentParser(description="Inspect MEVA's synthetic patient population.")
    parser.add_argument("--summary-only", action="store_true", help="Skip per-patient detail, print only the population summary")
    args = parser.parse_args()

    print("MEVA — Benchmark Data Inspector\n")

    totals = {"patients": 0, "allergies": 0, "medications": 0, "conditions": 0, "observations": 0, "encounters": 0}
    patients_with = {"allergies": 0, "medications": 0, "conditions": 0}

    for patient_summary in server.list_patients():
        pid = patient_summary["patient_id"]
        patient = server.get_patient(pid)

        allergies = server.get_allergies(pid)
        medications = server.get_medications(pid)
        conditions = server.get_conditions(pid)
        observations = server.get_observations(pid, limit=100)
        encounters = server.get_encounters(pid, limit=100)

        totals["patients"] += 1
        totals["allergies"] += len(allergies)
        totals["medications"] += len(medications)
        totals["conditions"] += len(conditions)
        totals["observations"] += len(observations)
        totals["encounters"] += len(encounters)
        if allergies:
            patients_with["allergies"] += 1
        if medications:
            patients_with["medications"] += 1
        if conditions:
            patients_with["conditions"] += 1

        if args.summary_only:
            continue

        print(f"Patient: {pid} ({patient_summary['file']})")
        print(f"  Name: {patient['name']}, Gender: {patient['gender']}, Birth date: {patient['birth_date']}")
        print(f"  Allergies: {len(allergies)}")
        for a in allergies:
            print(f"    - {a['name']}  [resource_id={a['id']}]")
        print(f"  Medications: {len(medications)}")
        for m in medications:
            print(f"    - {m['name']}  [resource_id={m['id']}]")
        print(f"  Conditions: {len(conditions)}")
        for c in conditions:
            print(f"    - {c['name']}  [resource_id={c['id']}]")
        print(f"  Observations: {len(observations)}")
        print(f"  Encounters: {len(encounters)}")
        print()

    print("=== Population summary ===")
    print(f"Total patients: {totals['patients']}")
    print(f"Patients with allergies: {patients_with['allergies']}")
    print(f"Patients with medications: {patients_with['medications']}")
    print(f"Patients with conditions: {patients_with['conditions']}")
    print(f"Total allergies: {totals['allergies']}")
    print(f"Total medications: {totals['medications']}")
    print(f"Total conditions: {totals['conditions']}")
    print(f"Total observations: {totals['observations']}")
    print(f"Total encounters: {totals['encounters']}")


if __name__ == "__main__":
    main()
