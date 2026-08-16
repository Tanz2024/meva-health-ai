# Third-Party Notices

MEVA's own source code is licensed under the Apache License 2.0 (see
`LICENSE`). This document separately lists third-party dependencies, data,
and models MEVA uses or interacts with — their licenses are their own, not
MEVA's.

## Software dependencies (installed via `pip install -e .`)

| Package | Version (as tested) | License | Notes |
|---|---|---|---|
| [`mcp`](https://modelcontextprotocol.io) | 2.0.0 | MIT | Model Context Protocol SDK |
| [`langgraph`](https://docs.langchain.com/oss/python/langgraph/overview) | 1.2.11 | MIT | Workflow orchestration for the benchmark engine |
| [`langchain-core`](https://docs.langchain.com/) | 1.5.5 | MIT | Pulled in as a required dependency of `langgraph` |
| [`pydantic`](https://github.com/pydantic/pydantic) | 2.13.4 | MIT | Data models throughout the codebase |

All four are permissively licensed (MIT) and compatible with Apache-2.0
redistribution. Versions above reflect what was installed and tested during
development — see `pyproject.toml` for the actual version constraints
MEVA declares.

## Ollama (external tool, not bundled)

MEVA talks to a locally-running [Ollama](https://ollama.com) server over
HTTP — it does not vendor, bundle, or redistribute the Ollama binary or any
model weights. Users install Ollama and pull models themselves. Ollama's
own license (MIT, per its public repository) applies to the Ollama software
itself, separately from MEVA.

## Local AI models used for evaluation (not bundled or redistributed)

MEVA's benchmark results reference two locally-run models. **MEVA does not
redistribute either model's weights** — users run `ollama pull <model>`
themselves and are bound by that model's own license when they do.

| Model | License (as reported by the model's Ollama listing) | Notes |
|---|---|---|
| `qwen3:4b` | Apache License 2.0 | Permissive |
| `llama3.2:3b` | Llama 3.2 Community License Agreement | **Not an OSI-approved open-source license** — a custom, restrictive license with its own usage/acceptable-use terms (see Meta's published license text). Anyone running llama3.2:3b locally must independently review and accept that license; MEVA does not do so on a user's behalf and imposes no additional restriction beyond documenting this. |

**MEVA's Apache-2.0 license applies only to MEVA's own source code and
locally-generated synthetic data — it does not apply to, extend to, or
relicense any model's weights.** Users remain independently subject to
each model's own license (e.g. Meta's Llama 3.2 Community License) when
they download and run that model via Ollama.

## Synthea (the synthetic-data generator)

MEVA's public synthetic patient data (`data/synthetic/synthea/patient-01.json`
through `patient-21.json`) is produced by
[Synthea](https://github.com/synthetichealth/synthea), an open-source
synthetic patient generator. **The Synthea generator itself is licensed
under Apache License 2.0** (confirmed via the repository's published
license metadata; pinned in this project to tag `v3.4.0`).

**As of Stage 8A.1, this output is generated locally by this project**,
directly from that Apache-2.0 generator, with a fixed, documented,
reproducible command and seed — it is not downloaded or copied from any
third-party pre-generated dataset. Full generation details (exact
revision, command, seed, export configuration, and per-file SHA-256
hashes) are in `data/synthetic/synthea/PROVENANCE.md`. Because MEVA
generated this output itself using an Apache-2.0-licensed tool, under
MEVA's own Apache-2.0 license, there is no third-party redistribution
question for these files the way there was for the files described below.

## ⚠️ Historical note: synthea-sample-data files are no longer redistributed

Stages 3 through 8A used a different set of 18 patient files, downloaded
from the **`synthetichealth/synthea-sample-data`** repository (a separate
repository from the Synthea generator itself), specifically
`downloads/synthea_sample_data_fhir_r4_nov2021.zip`.

**That repository's own license field is unset (`null`)** — confirmed
directly against its repository metadata. GitHub's default terms apply when
no license is declared: the content is viewable publicly, but no license is
granted to copy, modify, or redistribute it beyond that.

**As of Stage 8A.1, those 18 files are no longer part of MEVA's public
dataset** — they have been replaced by the locally-generated fixtures
described above. This resolves the licensing blocker identified in Stage
8A by removing the dependency entirely, rather than by asserting a license
MEVA cannot confirm. See `docs/historical-sample-data-provenance.md` for
the removed files' identity (filenames and SHA-256 hashes only — no file
content) and what this means for MEVA's historical (v0.1–v0.3) benchmark
results, which remain valid as historical records and are not rewritten.

The two small handmade example files (`data/synthetic/patient-001.json`,
`data/synthetic/patient-001-fhir.json`) were authored directly for this
project and were never affected by this issue — they are covered by MEVA's
own Apache-2.0 license.

## No other third-party code or assets

No other third-party source code, images, fonts, or other assets have been
copied into this repository. `git grep`/directory audits performed in
Stage 8A found no other vendored third-party files.
