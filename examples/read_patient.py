"""Example script: load a synthetic patient and print their basic info."""

from pathlib import Path

from meva.patient_reader import load_patient

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "patient-001.json"


def main():
    patient = load_patient(str(DATA_FILE))

    print(f"Patient: {patient['name']}")
    print(f"Age: {patient['age']}")
    print(f"Allergies: {patient['allergies']}")
    print(f"Medications: {patient['medications']}")
    print(f"Blood Pressure: {patient['blood_pressure']}")


if __name__ == "__main__":
    main()
