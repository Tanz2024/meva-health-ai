"""Resumable run-state persistence for the Stage 7D2 full (104-answer) decoupled run.

Same pattern as meva.benchmark.run_state — one JSON file per run, rewritten
after every completed (source_model, case_id) extraction, so a killed/crashed
process can resume. Resuming validates the source Stage 7C2 report's identity
(content hash), the extractor's exact model/tag/digest, the case list, the
source-model list, and the extraction configuration all match — an
incompatible resume is rejected rather than silently mixed with old data.
"""

import hashlib
import json
from pathlib import Path

DEFAULT_RUNS_DIR = (Path(__file__).resolve().parent.parent.parent.parent / "results" / "extraction" / "runs").resolve()


class IncompatibleResumeError(Exception):
    """Raised when a --resume run_id's saved state doesn't match this run's configuration."""


def source_report_hash(path: str | Path) -> str:
    """SHA-256 of the source Stage 7C2 report file — proves a resume is reading the exact
    same saved answers, not a report that was regenerated/changed in between runs."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ExtractionRunState:
    """Tracks which (source_model, case_id) extractions have completed for one full run."""

    def __init__(
        self, run_id: str, source_report_sha256: str, extractor_tag: str, extractor_digest: str | None,
        source_models: list[str], case_ids: list[str], extraction_config: dict, runs_dir=None,
    ):
        self.run_id = run_id
        self.source_report_sha256 = source_report_sha256
        self.extractor_tag = extractor_tag
        self.extractor_digest = extractor_digest
        self.source_models = source_models
        self.case_ids = case_ids
        self.extraction_config = extraction_config
        self.runs_dir = Path(runs_dir) if runs_dir else DEFAULT_RUNS_DIR
        self.path = self.runs_dir / f"{run_id}.json"
        self.completed: dict[str, dict[str, dict]] = {m: {} for m in source_models}

    @classmethod
    def load_or_create(
        cls, run_id: str, source_report_sha256: str, extractor_tag: str, extractor_digest: str | None,
        source_models: list[str], case_ids: list[str], extraction_config: dict, runs_dir=None,
    ) -> "ExtractionRunState":
        runs_dir = Path(runs_dir) if runs_dir else DEFAULT_RUNS_DIR
        path = runs_dir / f"{run_id}.json"

        if not path.exists():
            state = cls(
                run_id, source_report_sha256, extractor_tag, extractor_digest,
                source_models, case_ids, extraction_config, runs_dir=runs_dir,
            )
            state.save()
            return state

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        checks = [
            ("source_report_sha256", data.get("source_report_sha256"), source_report_sha256),
            ("extractor_tag", data.get("extractor_tag"), extractor_tag),
            ("extractor_digest", data.get("extractor_digest"), extractor_digest),
            ("source_models", data.get("source_models"), source_models),
            ("case_ids", data.get("case_ids"), case_ids),
            ("extraction_config", data.get("extraction_config"), extraction_config),
        ]
        for name, saved, current in checks:
            if saved != current:
                raise IncompatibleResumeError(
                    f"Run '{run_id}' was recorded with {name}={saved!r}, not {current!r}. Refusing to resume."
                )

        state = cls(
            run_id, source_report_sha256, extractor_tag, extractor_digest,
            source_models, case_ids, extraction_config, runs_dir=runs_dir,
        )
        completed = data.get("completed") or {}
        for m in source_models:
            state.completed[m] = completed.get(m, {})
        return state

    def is_done(self, source_model: str, case_id: str) -> bool:
        return case_id in self.completed.get(source_model, {})

    def record(self, source_model: str, case_id: str, result_dict: dict) -> None:
        self.completed.setdefault(source_model, {})[case_id] = result_dict
        self.save()

    def results_for(self, source_model: str) -> list[dict]:
        done = self.completed.get(source_model, {})
        return [done[cid] for cid in self.case_ids if cid in done]

    def save(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.run_id,
            "source_report_sha256": self.source_report_sha256,
            "extractor_tag": self.extractor_tag,
            "extractor_digest": self.extractor_digest,
            "source_models": self.source_models,
            "case_ids": self.case_ids,
            "extraction_config": self.extraction_config,
            "completed": self.completed,
        }
        tmp_path = self.path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        tmp_path.replace(self.path)
