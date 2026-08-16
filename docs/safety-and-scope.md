# Safety, Scope, and Research Status

MEVA is an **open-source research and engineering framework**. This
document states its scope and limits plainly, in one place, for anyone
evaluating whether to use, extend, or cite it.

## What MEVA is

A framework for evaluating whether AI agents retrieve and faithfully use
medical evidence from **synthetic** FHIR patient records — measuring tool
use, structured-output adherence, and evidence-grounding behavior against a
deterministic, non-AI verifier.

## What MEVA is not

- **Not a medical chatbot.**
- **Not diagnostic AI.**
- **Not clinical decision support.**
- **Not a treatment recommendation system.**
- **Not a medical device**, and not built, tested, or intended to meet any
  medical device regulatory standard.
- **Not clinically validated.** No claim here has been reviewed or approved
  by a clinical or regulatory body.

## Data

MEVA uses **only synthetic (fake, computer-generated) patient data** —
produced by [Synthea](https://github.com/synthetichealth/synthea), an
open-source synthetic patient generator. No real patient data is included
anywhere in this project, and none should ever be contributed (see
`CONTRIBUTING.md`). See `docs/synthetic-data.md` for full provenance, and
`THIRD_PARTY_NOTICES.md` for the licensing status of the specific sample
data files.

## What MEVA's metrics mean — and don't mean

**Evidence Grounding Score**, **Verifiable Claim Coverage**, and every other
metric this project reports are **engineering/research benchmark metrics**.
They measure whether a claim a model made matches evidence a deterministic
verifier retrieved from synthetic FHIR data. They do **not** measure:

- medical/clinical accuracy
- diagnostic accuracy
- treatment appropriateness
- patient safety
- real-world reliability on real patient data

A model scoring well on MEVA's benchmark says nothing about whether it
would be safe or effective in an actual clinical setting. Do not use MEVA's
results, alone or in combination, to make a clinical claim about any model.

## Local-only inference

MEVA never calls a paid or cloud AI API. All model inference (both the
tested "source" models and the fixed claim extractor) runs through a
locally-installed [Ollama](https://ollama.com) server. See
`docs/local-ai.md` and `docs/reproducibility.md`.
