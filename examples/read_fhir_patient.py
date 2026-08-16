"""Example script: load a synthetic FHIR patient bundle and print a summary."""

from pathlib import Path

from meva.fhir import (
    blood_pressure_text,
    get_allergies,
    get_medications,
    get_observations,
    get_patient,
    load_bundle,
    patient_name,
)

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "patient-001-fhir.json"


def main():
    resources = load_bundle(str(DATA_FILE))

    patient = get_patient(resources)
    print(f"FHIR Patient: {patient_name(patient)}")
    print(f"Gender: {patient['gender']}")

    print("\nAllergies:")
    for allergy in get_allergies(resources):
        print(f"- {allergy['name']}")

    print("\nMedications:")
    for medication in get_medications(resources):
        print(f"- {medication['name']}")

    print("\nObservations:")
    for observation in get_observations(resources):
        bp = blood_pressure_text(observation)
        if bp:
            print(f"- Blood Pressure: {bp}")
        elif observation["value"]:
            print(f"- {observation['name']}: {observation['value']}")


if __name__ == "__main__":
    main()
