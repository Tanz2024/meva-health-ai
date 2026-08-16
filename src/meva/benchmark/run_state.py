"""Resumable run-state persistence for long multi-model benchmark runs.

No database — one JSON file per run (results/comparisons/runs/<run_id>.json),
rewritten after each completed model/case pair so a killed/crashed process
can resume without re-running already-completed work. Resuming validates
that the benchmark version, model list, and case list match exactly; an
incompatible resume is rejected rather than silently mixed with old data.
"""

import json
from pathlib import Path

DEFAULT_RUNS_DIR = (Path(__file__).resolve().parent.parent.parent.parent / "results" / "comparisons" / "runs").resolve()


class IncompatibleResumeError(Exception):
    """Raised when a --resume run_id's saved state doesn't match this run's configuration."""


class RunState:
    """Tracks which (model, case_id) pairs have completed, plus the verifier-challenge
    results (run once, not per model) and per-model metadata, for one comparison run."""

    def __init__(self, run_id: str, benchmark_version: str, models: list[str], case_ids: list[str], runs_dir=None):
        self.run_id = run_id
        self.benchmark_version = benchmark_version
        self.models = models
        self.case_ids = case_ids
        self.runs_dir = Path(runs_dir) if runs_dir else DEFAULT_RUNS_DIR
        self.path = self.runs_dir / f"{run_id}.json"
        self.completed: dict[str, dict[str, dict]] = {m: {} for m in models}
        self.verifier_challenge_results: list[dict] | None = None
        self.model_metadata: dict[str, dict] = {}

    @classmethod
    def load_or_create(
        cls, run_id: str, benchmark_version: str, models: list[str], case_ids: list[str], runs_dir=None,
    ) -> "RunState":
        runs_dir = Path(runs_dir) if runs_dir else DEFAULT_RUNS_DIR
        path = runs_dir / f"{run_id}.json"

        if not path.exists():
            state = cls(run_id, benchmark_version, models, case_ids, runs_dir=runs_dir)
            state.save()
            return state

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("benchmark_version") != benchmark_version:
            raise IncompatibleResumeError(
                f"Run '{run_id}' was recorded for benchmark_version "
                f"'{data.get('benchmark_version')}', not '{benchmark_version}'. Refusing to resume."
            )
        if data.get("models") != models:
            raise IncompatibleResumeError(
                f"Run '{run_id}' was recorded for models {data.get('models')}, not {models}. Refusing to resume."
            )
        if data.get("case_ids") != case_ids:
            raise IncompatibleResumeError(
                f"Run '{run_id}' was recorded for a different case list "
                f"({len(data.get('case_ids', []))} cases), not {len(case_ids)}. Refusing to resume."
            )

        state = cls(run_id, benchmark_version, models, case_ids, runs_dir=runs_dir)
        completed = data.get("completed") or {}
        for m in models:
            state.completed[m] = completed.get(m, {})
        state.verifier_challenge_results = data.get("verifier_challenge_results")
        state.model_metadata = data.get("model_metadata") or {}
        return state

    def is_case_done(self, model: str, case_id: str) -> bool:
        return case_id in self.completed.get(model, {})

    def record_case_result(self, model: str, case_id: str, result_dict: dict) -> None:
        self.completed.setdefault(model, {})[case_id] = result_dict
        self.save()

    def record_model_metadata(self, model: str, metadata: dict) -> None:
        self.model_metadata[model] = metadata
        self.save()

    def record_verifier_challenge_results(self, results: list[dict]) -> None:
        self.verifier_challenge_results = results
        self.save()

    def case_results_for(self, model: str) -> list[dict]:
        """This model's completed case results, in the run's canonical case_id order."""
        done = self.completed.get(model, {})
        return [done[cid] for cid in self.case_ids if cid in done]

    def is_model_complete(self, model: str) -> bool:
        return all(self.is_case_done(model, cid) for cid in self.case_ids)

    def save(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.run_id,
            "benchmark_version": self.benchmark_version,
            "models": self.models,
            "case_ids": self.case_ids,
            "completed": self.completed,
            "verifier_challenge_results": self.verifier_challenge_results,
            "model_metadata": self.model_metadata,
        }
        tmp_path = self.path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        tmp_path.replace(self.path)
