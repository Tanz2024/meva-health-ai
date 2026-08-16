# MEVA Roadmap

This is an approximate, non-binding plan — priorities may shift based on
contributor interest and findings from ongoing benchmark work.

## v0.1 (current)

- Reproducible synthetic-FHIR benchmark (18 Synthea patients, 56 v0.3
  cases, AGENT + VERIFIER_CHALLENGE case types)
- MCP tool layer over synthetic FHIR data (allergies, medications,
  conditions, observations, encounters, patient demographics)
- Local Ollama model integration (qwen3:4b, llama3.2:3b), no cloud/paid AI
- Deterministic evidence verifier, fully independent of the model being
  evaluated
- END_TO_END and DECOUPLED evaluation modes, with a fixed-extractor
  fidelity audit (development + held-out validation)
- Multi-model comparison framework with resumable, thermally-throttled
  local execution
- Transparent metric-integrity correction history (Stage 7C2.1)
- Independent observation-category sanity audit (Stage 7D2.2)
- Public release hardening (this stage)

## Near-term future work

- **Local/browser playground** — an interactive way to explore MEVA's
  verification behavior without writing Python. Not started; explicitly
  out of scope for Stage 8A.
- **Public verifier sandbox** — a hosted, safe way to try MEVA's verifier
  against sample claims (synthetic data only). Not started.
- **More synthetic patient diversity** — beyond the current 18 patients,
  broader condition/medication/observation coverage.
- **Independent claim-extractor comparison** — Stage 7D2.1 validated a
  single fixed extractor (qwen3:4b); a documented extractor-bias caveat
  applies until a second, independent extractor is evaluated the same way.
- **Additional local models** — currently limited to qwen3:4b and
  llama3.2:3b; adding a third (or more) model is future work, following
  the same fairness rules in `docs/model-comparison.md`.
- **Observation tool-output consistency** — Stage 7D2.2 documented that
  Blood Pressure observations currently expose a `null` top-level `value`
  field, with the actual combined reading only in a separate
  `blood_pressure` key (see `docs/observation-audit.md` §6 for the full
  finding and proposed fix). **Deliberately not fixed in Stage 8A** — it's
  a real finding worth its own reviewed change, not a drive-by fix during a
  release-hardening pass.
- **Additional FHIR resources** — MEVA currently covers allergies,
  medications, conditions, observations, encounters, and patient
  demographics; other FHIR resource types (e.g. procedures, immunizations,
  diagnostic reports) are unimplemented.

## Explicitly not planned soon

- Real patient data support of any kind
- Diagnosis or treatment-recommendation functionality
- Paid/cloud AI API integration
- Positioning MEVA as a clinical or medical-device product
