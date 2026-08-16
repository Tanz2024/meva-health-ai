# Provenance — Locally Generated Synthetic Patients (Stage 8A.1)

Every FHIR bundle in this directory (`patient-01.json` through
`patient-21.json`) was generated **locally, by this project**, using the
official, Apache-2.0-licensed Synthea generator — not copied from any
third-party sample-data repository. This replaces the previous set of 18
patients that had been copied from `synthetichealth/synthea-sample-data`
(a repository with no declared license) — see
`docs/historical-sample-data-provenance.md` for that removed set's identity
and `THIRD_PARTY_NOTICES.md` for the licensing rationale.

## Generator identity

- **Repository:** `synthetichealth/synthea`
- **Revision:** tag `v3.4.0`, commit `ed897583f1d10a449ccb20a2345ef83f84421c20`
- **License:** Apache License 2.0 (confirmed via the repository's own
  license metadata)
- **Generation date:** 2026-08-16

## Generation configuration

- **Command:** `./run_synthea -s 42 -p 30 Massachusetts`
- **Seed:** `42` (`-s 42`) — reproducible: the same command against the
  same Synthea revision produces the same population
- **Population requested:** 30 (`-p 30`); Synthea reported
  `Records: total=30, alive=30, dead=0`
- **Location:** Massachusetts, USA (Synthea's default module set targets
  US healthcare; no other module configuration was changed)
- **Export format:** FHIR R4 transaction Bundles (Synthea's default
  `exporter.fhir.export=true`, `exporter.fhir_stu3.export=false`,
  `exporter.fhir_dstu2.export=false`, `exporter.fhir.transaction_bundle=true`
  — unmodified `src/main/resources/synthea.properties` defaults)
- **Java toolchain used to build/run Synthea:** OpenJDK 21.0.12 (Homebrew) —
  Synthea's Gradle 8.14.3 wrapper did not support the newer JDK 26 initially
  attempted; this is a build-environment detail, not a Synthea configuration
  choice, and does not affect the generated data's determinism

## Selection process

Synthea generated 30 patients (plus 2 non-patient support files —
`hospitalInformation*.json`, `practitionerInformation*.json` — not
retained). All 30 patient bundles were verified loadable through MEVA's
existing FHIR layer (`meva.fhir.reader.load_bundle` +
`meva.fhir.patient/allergies/medications/conditions/observations`) before
selection.

**21 of the 30** were retained as the public dataset — selected as the 20
smallest generated files (favoring a lightweight public repository, the
same spirit as the previous dataset's "small-to-medium" selection), plus
one additional larger file added specifically for allergy-category
diversity (`patient-21.json`, 8 allergies). The 9 excluded patients ranged
from moderately large to very large (up to ~28 MB for one outlier with
extensive multi-decade history) and were excluded purely for repository
size, not for any data-quality reason — they are equally valid synthetic
patients, just not committed to this repository.

No expected medical evidence was fabricated to hit any target — every
fact used in `benchmarks/v0.4/cases.json` is read directly from these
generated bundles (see `benchmarks/v0.4/manifest.json`).

## Retained public fixtures

| Repo filename | Synthea `patient.id` | Allergies | Medications | Conditions | Observations | SHA-256 |
|---|---|---|---|---|---|---|
| `patient-01.json` | `d15b23ed-02d5-3e28-efbd-2604425317c5` | 0 | 0 | 1 | 41 | `057374ea1a30bc9251315874838c32f1bd00de6d9d7c5cf48a77f20e12b56c3b` |
| `patient-02.json` | `c053e996-a4c4-6c02-e2b6-284227156c67` | 2 | 6 | 8 | 140 | `d92af9a95c5b6d78093731123b262e33559733b06b3ed91c0a74c954d608c4b9` |
| `patient-03.json` | `2d68ad16-268a-478c-1f84-d0f1976e1a46` | 0 | 0 | 8 | 179 | `cbb25e1d5bcb696191bf942e77272b71b5f175852aa14e451c13d2874fb03784` |
| `patient-04.json` | `c0a47dee-cc72-29ce-df5a-ea6d306c36a4` | 2 | 4 | 13 | 83 | `41f76d521d7721dadfd3ec9f1836e68148024056da1b6c9846743966c9fb20cd` |
| `patient-05.json` | `4f083ce3-f12b-bb4b-7353-e17f0cd55b0a` | 0 | 2 | 13 | 98 | `df6f10abfa0dbaf32bfeaac0f78271f90ac052dc1533726cbdbdaeae50a94864` |
| `patient-06.json` | `5e688e99-61b3-5c88-3f60-21df8aaced27` | 0 | 2 | 9 | 120 | `0a85d36e9b8bd464a47f62568b417605d75a53e2b63d9d8b56a9cd61639c16f1` |
| `patient-07.json` | `982750f4-569b-5949-196b-60699bdda3fb` | 0 | 4 | 20 | 85 | `829de739c1df797c45a58edcbe77df40d25761ff2ffa3353d1a7b3b19c4fb5ff` |
| `patient-08.json` | `76b20010-c318-5754-8c85-983aa538522f` | 0 | 4 | 17 | 206 | `cf2e00c0c25ecaa7610477962ef9125fade5f2acf4eddef3cf8bda3456cc44be` |
| `patient-09.json` | `947c82ee-1735-c9ed-8210-38cb93d8070c` | 0 | 5 | 17 | 173 | `3ed49695203008648c9fd739a8520e63f4f595ea3db5a5692d943d93c59a6cf9` |
| `patient-10.json` | `d3727ff2-5d7b-347f-d78c-edc4323cf890` | 0 | 10 | 16 | 146 | `9b814f9415db5a325de6e11089f05fd8c8836e6a8525ecf1e4375a879d4d1f32` |
| `patient-11.json` | `922fb35e-148d-9e82-7e65-bfa05e3b3515` | 0 | 12 | 19 | 74 | `6de8b36a36921eb58349932f56e55cdd12674ec5e05be1e533b06ab7e94a29e5` |
| `patient-12.json` | `2c167999-289d-95fa-5c27-7d8b8d35348c` | 0 | 6 | 24 | 166 | `bd5aa3056788d8342d80b28c99306f7da41d183b5705ebd272e060f40afdb9ac` |
| `patient-13.json` | `aee7bbe1-0c45-c028-1e62-1f4cdb30c273` | 0 | 9 | 32 | 153 | `3552806c70d10c2cb731107d1fdb6b5c4b8c95d5040b5afebcb9408c4a727687` |
| `patient-14.json` | `eb5910f1-26e6-bc6f-b300-716eae678d6f` | 0 | 6 | 28 | 72 | `662e4b6a69558a0b94c204595758d67dbb111360230d11ef5306ae3222ca43dc` |
| `patient-15.json` | `46976cf7-b0bf-be20-39a5-9f425a52886d` | 0 | 14 | 26 | 149 | `1b6b9ea5bd1dc07eb4732cc761f6b96768eacc76d46c58e97f30bf4b14984449` |
| `patient-16.json` | `6fbddf55-7096-b883-7cd3-260f27953080` | 3 | 6 | 28 | 169 | `8ed4ad15d5b473f9f68269a1251dbf7e44e5c99d46425b70bd4a90874e04ee44` |
| `patient-17.json` | `35b353dd-402b-571a-d67a-af0a104d0854` | 0 | 17 | 33 | 249 | `1a72c4b23c65d3f0a81ebfe7f1412d5a0290827ec937884798c7a6c93cd9124f` |
| `patient-18.json` | `5ba0a3f3-32f7-02b1-ec6a-8f568923954c` | 8 | 47 | 26 | 140 | `dbb079e36b252ac3a6549c39c7aa83f04c6153eea6a6cec312252a0e36a710aa` |
| `patient-19.json` | `b6a1cac9-8873-36a7-e726-4aad8a07d44d` | 1 | 6 | 17 | 103 | `b9eec45ee95e1f55bf45aa1a3f3d92becfba741d28f52090854079e48642e201` |
| `patient-20.json` | `080b069b-5108-46b6-ecef-6aacd3b9ef3f` | 9 | 43 | 38 | 234 | `63015f80f09fa5f8998985ad3daa7dc6272658dd59e994e8cc79d1001d7ce1e4` |
| `patient-21.json` | `f95a6723-14a5-c4b6-78df-fa97f7ab361c` | 8 | 41 | 38 | 161 | `a43457e11bf9894dece907031c4f6f6e345be79378dceb5e2233cc66a4118230` |

Allergy/medication/condition/observation counts above are raw resource
counts as read by MEVA's own FHIR layer at generation-verification time
(Stage 8A.1) — not benchmark case counts.

## Reproducing this dataset

```bash
git clone https://github.com/synthetichealth/synthea.git
cd synthea
git checkout v3.4.0
./run_synthea -s 42 -p 30 Massachusetts
```

This is expected to regenerate the same 30 patients (same seed, same
generator revision) — though byte-for-byte identity across different Java
versions/operating systems is not separately guaranteed by this project
beyond what Synthea itself guarantees for its own seeded RNG.

All 21 patients here are entirely fictional — generated by statistical
models, not derived from any real person, living or dead.
