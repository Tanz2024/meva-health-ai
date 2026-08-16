# MEVA Model Comparison

Stage 7C1 lets MEVA run its exact same benchmark against more than one
local Ollama model — starting with `qwen3:4b` vs `llama3.2:3b`. This is
a **foundation**: it proves the comparison machinery is fair and
correct on a small pilot. It is not yet a full benchmark run, and it is
never a clinical judgement of either model.

## Why models use the exact same cases

`examples/compare_models.py` runs every model over the identical list
of case IDs, in the identical order, loaded once from the benchmark
dataset. `run_model_comparison()` never cherry-picks different cases
per model — a fair comparison requires asking the exact same questions.

## Why prompts are kept the same

MEVA uses one system prompt and one structured-claim instruction
(`meva.ai.agent.SYSTEM_PROMPT` / `_FINAL_ANSWER_INSTRUCTION`) for every
model. Writing a "Qwen-tuned prompt" and a "Llama-tuned prompt" would
mean the comparison measures prompt engineering, not the models —
schema and prompt adherence is itself part of what's being measured
(see "structured claim quality" below). Model-specific prompt
experiments are legitimate but must be reported separately, never
blended into the official comparison.

## Why exact model digest is recorded

An Ollama tag like `qwen3:4b` can point to a different underlying model
over time (updates, re-tags). The **digest** (from `/api/tags`) is a
content hash — recording it means a comparison result stays
attributable to the exact model weights that produced it, not just a
name that might later mean something else.

## Fair configuration policy

Every model uses `temperature=0`, `seed=42`, and MEVA's standard
`tool_call_think`/`final_structured_think` defaults — **unless** a
model genuinely doesn't support a setting. `meva.models.discovery`
queries `/api/show` for each model's real `capabilities`; if
`"thinking"` isn't listed (as with `llama3.2:3b`), `tool_think` and
`structured_think` are both set to `False` for that model rather than
sent anyway — Ollama itself rejects a `think` parameter on a
non-thinking model. This is recorded in the result's
`effective_configuration`, never silently applied or hidden.

## Compatibility check, before any scoring

Before running the pilot cases, each model gets one real question
("What allergies are recorded for patient `<id>`?") through the full
agent loop, and MEVA checks two things independently:

- `tool_call_supported` — did the model produce at least one valid tool call?
- `structured_output_supported` — did its final response parse as valid
  JSON matching the `AgentAnswer` schema (an `"answer"` key present)?

If either check fails, MEVA does **not** proceed to a full benchmark
run for that model — the result records `agent_case_count=0` and the
`compatibility_error`, and the comparison continues with the next
model. One incompatible model never blocks or corrupts another's
result.

## Three performance layers — never combined

Every model's `agent_metrics` keeps three kinds of measurement
separate, on purpose:

**A. Agent / retrieval** — did the model call the right tools?
(`required_tool_recall`, `tool_precision`, `exact_tool_match_rate`,
`tool_overcall_rate`, duplicate calls, `evidence_recall`)

**B. Structured claim quality** — did its output parse into valid,
well-formed claims? (`structured_claim_validity_rate`, plus the raw
counts underlying it — see `docs/evidence-verification.md`)

**C. Evidence grounding** — of the claims that *were* extractable, did
they match reality? (`supported`/`contradicted`/`unsupported`/
`unverifiable`, `evidence_grounding_score`)

These are reported as separate numbers, never averaged into one
"MEVA score" — a model that retrieves perfectly but writes malformed
JSON, and a model that writes perfect JSON but retrieves the wrong
tool, fail in completely different ways that a single blended number
would hide.

### The three failure types stay distinct

| Case | What happened | How MEVA reports it |
|---|---|---|
| A | Correct evidence retrieved, but the claims JSON was malformed | **Structured output failure** — low `structured_claim_validity_rate`, layer B |
| B | Wrong tool called, or the right tool wasn't called at all | **Retrieval failure** — low `required_tool_recall`, layer A |
| C | Evidence has BP 128/81, model claims none exists | **Grounding failure** — a `CONTRADICTED` claim, layer C |

A single "did it pass" number would flatten these into one bit and
throw away exactly the information that explains *why* a model failed
— which is often the more useful finding.

## Why verifier challenges aren't model-scored

`VERIFIER_CHALLENGE` cases (see `docs/benchmarking.md`) bypass the live
model entirely and feed a hand-written wrong claim straight into
MEVA's deterministic verifier — they test MEVA's code, not a model.
`agent_only()` filters them out before any model comparison runs, and
`run_model_comparison()` filters defensively again even if a caller
forgets. Comparing "Qwen vs Llama" on a verifier-challenge case would
be comparing MEVA's verifier against itself.

## Sequential execution, thermal-safety pauses

Models are always run one after another, never in parallel — loading
two multi-GB local models simultaneously stresses laptop memory and
thermals for no benefit (this pilot doesn't need concurrent inference
speed). `--pause-between-cases` and `--pause-between-models` add
configurable delays, and MEVA best-effort unloads a model
(`keep_alive=0`) before moving to the next. **This does not guarantee
thermal safety** — it's a simple, honest throttle, not a hardware
control system.

## Limitations of comparing different parameter sizes

`qwen3:4b` (4.0B params) and `llama3.2:3b` (3.2B params) are different
sizes, different architectures, and different training runs — a
difference in benchmark numbers doesn't isolate any single cause.
Parameter size, quantization (both `Q4_K_M` here), and license are
recorded specifically so a reader can see what varies between them,
not so MEVA can draw a "bigger is better" conclusion from two data
points.

## Local hardware affects latency

As in `docs/reproducibility.md`, every latency number here depends on
the machine MEVA ran on. Comparing `qwen3:4b`'s median latency to
`llama3.2:3b`'s median latency on the *same* machine, in the *same*
run, is meaningful; comparing either number to a different machine's
results is not.

## Not yet: full-benchmark comparison

Stage 7C1 is a **6-case pilot**, not the full v0.3 benchmark (56 cases,
52 of them AGENT). Running the full AGENT set across multiple models is
future work — this stage exists to prove the comparison machinery
(registry, discovery, fair configuration, compatibility gating, layered
metrics, sequential execution) is correct and honest before spending
the time on a full run.
