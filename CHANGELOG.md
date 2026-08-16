# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

**No GitHub release has been published yet.** Everything below reflects
development history up to the point of Stage 8D release-candidate
finalization; a `git` history and public release will follow separately,
on explicit approval.

## [0.1.0] - Unreleased

### Added

- Synthetic FHIR patient data and a read-only FHIR parsing layer
  (allergies, medications, conditions, observations, encounters, patient
  demographics). The public dataset (`data/synthetic/synthea/`) now
  contains 21 patients generated locally with the official Apache-2.0
  Synthea generator (Stage 8A.1) — see "Changed" below for why an earlier
  18-patient set was replaced.
- An MCP (Model Context Protocol) tool server exposing that FHIR data to a
  local AI agent, with path-traversal-safe patient lookup.
- Local Ollama integration for a tool-calling agent loop, with structured
  final-answer output (`AgentAnswer` / `MedicalClaim` schema).
- A deterministic evidence verifier, fully independent of the model being
  evaluated — SUPPORTED / CONTRADICTED / UNSUPPORTED / UNVERIFIABLE
  verdicts and an Evidence Grounding Score.
- Reproducibility controls (fixed temperature/seed/think settings) and
  performance metrics.
- A LangGraph-based benchmark engine with a versioned dataset (v0.1 → v0.3,
  56 cases: 52 AGENT + 4 VERIFIER_CHALLENGE), dataset validation against
  real retrieved evidence, and duplicate-case detection.
- Tool-selection metrics (recall/precision/exact-match/overcalling),
  evidence recall, structured-claim-quality tracking, and attribute-claim
  verification.
- A multi-model comparison framework (`meva.models` registry + discovery,
  `meva.benchmark.comparison`) supporting sequential, resumable, thermally
  throttled local execution — first comparison: qwen3:4b vs llama3.2:3b.
- A full v0.3 benchmark run across both models, with grouped
  category/difficulty results, case-outcome taxonomy (retrieval/structured/
  grounding failure flags), and latency percentiles.
- A metric-integrity audit (Stage 7C2.1) that found and corrected a
  verifiable-claim-coverage aggregation bug (per-case mean → documented
  micro-average), with the original result preserved and the correction
  disclosed transparently.
- A DECOUPLED evaluation mode (`meva.extraction`): a fixed claim extractor
  converts a saved natural-language answer into structured claims,
  separately from the source model's own (often broken) structured output,
  with strict anti-leakage rules (no FHIR/evidence data reaches the
  extractor) and an anti-repair guarantee.
- A formal claim-extraction contract (`docs/claim-extraction-contract.md`)
  and a hardened extraction prompt, validated against development and
  held-out fixture sets with a fixed decision gate.
- A full 104-answer decoupled extraction run across both source models,
  with claim-recovery, grounding-failure-preservation, and
  method-disagreement analysis.
- An independent observation-category sanity audit (Stage 7D2.2) confirming
  the benchmark's low observation-category grounding scores reflect genuine
  model behavior, not an infrastructure bug — while documenting one
  non-blocking tool-output-shape finding for future work.
- Public release preparation (Stage 8A): README, contributor docs, license
  and third-party notice audit, CI, issue/PR templates, and a
  release-readiness check script.
- A deterministic-verifier CLI playground (Stage 8B, `examples/playground.py`)
  and a shared `meva.playground` service layer — no AI model involved.
- A Streamlit browser sandbox (Stage 8C, `streamlit_app.py`) over the same
  service layer, with an optional `playground` install extra, ready-made
  examples discovered live from current fixtures, and local deployment
  preparation (not yet deployed).
- Release-candidate finalization (Stage 8D): placeholder audit, publishing
  checklist, version/wording consistency pass, clean-install and
  package-build verification.

### Changed

- **Public synthetic dataset (Stage 8A.1):** the original 18-patient set
  (copied from a third-party repository with no declared license) was
  replaced with 21 patients generated locally via the official Apache-2.0
  Synthea generator (pinned revision, fixed seed) — see
  `data/synthetic/synthea/PROVENANCE.md`. A new benchmark version, v0.4
  (53 cases), was built entirely from this new dataset. **v0.4 model
  comparison results are pending** — no model has been run against it yet.
  The prior v0.1-v0.3 results remain preserved as historical development
  records (see `docs/baseline-results-v0.3.md`); their original fixtures
  are not redistributed and those exact historical datasets can no longer
  be live-revalidated from this repository, though the results themselves
  are unaffected — see `docs/historical-sample-data-provenance.md`.

### Known limitations

- Single machine, single run per configuration; no variance-across-runs
  reporting yet.
- Only two source models evaluated so far (against v0.1-v0.3); only one
  fixed extractor validated (itself one of the two source models — a
  documented bias caveat). No model has yet been run against the current
  public v0.4 dataset.
- Several fields in `CITATION.cff` and a few contact-email placeholders
  still require maintainer input before first publication — see
  `docs/publishing-checklist.md`.
