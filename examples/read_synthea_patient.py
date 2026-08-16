"""Example script: load a realistic Synthea-generated FHIR patient and print a summary.

Synthea patients are much richer than our handmade example — they may have
many conditions, medications, and observations, or none at all. We print
whatever is actually present and never invent missing data.
"""

from pathlib import Path

from meva.fhir import (
    blood_pressure_text,
    get_allergies,
    get_conditions,
    get_encounters,
    get_medications,
    get_observations,
    get_patient,
    load_bundle,
    patient_name,
)

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "synthea" / "patient-03.json"


def print_list(title: str, items: list, format_item) -> None:
    print(f"\n{title}:")
    if not items:
        print("- (none found)")
        return
    for item in items:
        print(f"- {format_item(item)}")


def main():
    resources = load_bundle(str(DATA_FILE))

    patient = get_patient(resources)
    patient_id = patient["id"]

    print("MEVA — Synthea Patient\n")
    print("Patient:")
    print(f"Name: {patient_name(patient)}")
    print(f"\nGender: {patient.get('gender')}")
    print(f"Birth Date: {patient.get('birthDate')}")

    print_list("Conditions", get_conditions(resources, patient_id), lambda c: c["name"])
    print_list("Allergies", get_allergies(resources, patient_id), lambda a: a["name"])
    print_list("Medications", get_medications(resources, patient_id), lambda m: m["name"])

    observations = get_observations(resources, patient_id)

    def format_observation(observation):
        bp = blood_pressure_text(observation)
        if bp:
            return f"Blood Pressure: {bp}"
        return f"{observation['name']}: {observation['value']}"

    print_list("Observations", observations[:10], format_observation)

    print_list(
        "Encounters",
        get_encounters(resources, patient_id),
        lambda e: f"{e['type']} ({e['status']}, {e['start']})",
    )


if __name__ == "__main__":
    main()
