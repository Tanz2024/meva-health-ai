# MEVA Reproducibility & Performance

Before comparing multiple models later, MEVA needs its *current* single
local model to be fast and consistent. This stage tunes exactly that —
no new models, no benchmark dataset.

## Why deterministic settings during benchmarks

If the same question can produce different tool calls or different
claims on different runs, you can't tell whether a change to MEVA's
code made things better or worse — the noise from randomness would
drown out the signal. MEVA's "evaluation mode" fixes the model's
generation settings so runs are comparable:

- `temperature = 0` — the model always picks its most likely next
  token instead of sampling randomly. This is the single biggest lever
  for consistent output.
- `seed = 42` — even at temperature 0, some backends use randomness in
  ties or sampling internals; a fixed seed removes that remaining
  variation. 42 has no special meaning — it's just a fixed, well-known
  placeholder.

With both set, the same question against the same model version
produces the same tool choices and essentially the same claims run to
run. (Ollama's structured-output mode already makes wording fairly
stable; determinism here is about the *decisions* — which tool, which
claims — not guaranteeing byte-identical sentences.)

## Why "thinking" is handled differently per phase

Qwen3 models can emit a chain-of-thought ("thinking") before their
answer. This helps the model choose the right tool, but for the final
structured-claims call it mostly adds latency without improving the
result. So MEVA uses two separate settings:

- `TOOL_CALL_THINK = True` — thinking stays on while the model is
  deciding which MEVA tool to call, since turning it off risked worse
  tool selection.
- `FINAL_STRUCTURED_THINK = False` — thinking is off for the final
  structured `AgentAnswer` call. Measured locally, this cut that call's
  latency from roughly 100–200 seconds down to about 1–2 seconds on a
  4B model, with no loss of claim quality once the final-answer prompt
  was made explicit about required fields (see
  `docs/evidence-verification.md`).

Both settings are overridable per call (`run_agent(..., tool_call_think=, final_structured_think=)`)
for experimentation.

## Why latency is recorded

`RunMetrics` captures exactly what Ollama reports for each call
(`total_duration`, `load_duration`, `prompt_eval_count`,
`prompt_eval_duration`, `eval_count`, `eval_duration`) — never an
invented number. Any field Ollama doesn't return stays `None`. This
lets `examples/benchmark_single_run.py` report real tool-call vs.
structured-answer latency, which matters once MEVA starts comparing
models or prompt changes: a "better" answer that takes 10x longer is
a real tradeoff, not a free win.

## Why local hardware affects runtime

All inference in MEVA runs on your own machine through Ollama — there
is no cloud fallback. That means measured latency depends entirely on
your CPU/GPU, available RAM, and whether the model is already loaded
(`keep_alive` controls how long Ollama keeps a model warm between
calls; MEVA defaults to `"5m"`). Latency numbers from one machine are
not directly comparable to another's — they're useful for tracking
*relative* change (before/after a prompt or setting change) on the same
hardware, not as an absolute benchmark.
