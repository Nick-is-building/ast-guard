"""
Loader for the HumanEval benchmark.

Source: openai/openai_humaneval (HuggingFace, public, MIT).
Fields verified: task_id (str), prompt (str), canonical_solution (str),
  test (str), entry_point (str).

Role in pair-mode evaluation:
  TN backbone — load_samples() emits honest-vs-honest pairs using the
  canonical solution compared to itself (same-problem identity).

Cross-loader use: lookup() returns {task_id: full_code} so the generator
can use canonical solutions as reference_code without re-downloading.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_HF_REPO = "openai/openai_humaneval"
_HF_CONFIG = "openai_humaneval"
_CACHE_FILE = "humaneval_rows.json"


def _cache_path(data_dir: Path) -> Path:
    return data_dir / _CACHE_FILE


def _load_rows(data_dir: Path) -> list[dict]:
    p = _cache_path(data_dir)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read HumanEval cache %s: %s", p, exc)
        return []


def _save_rows(data_dir: Path, rows: list[dict]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = _cache_path(data_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_cache_path(data_dir))


@register
class HumanEvalLoader(BenchmarkLoader):
    """Loads HumanEval reference solutions; emits TN (honest-vs-honest) pairs."""

    name = "humaneval"

    def download(self) -> None:
        """Download HumanEval via HuggingFace datasets and cache as JSON."""
        try:
            from datasets import load_dataset  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "pip install datasets  (required to download HumanEval)"
            ) from exc

        ds = load_dataset(_HF_REPO, _HF_CONFIG, split="test", trust_remote_code=False)
        rows: list[dict] = []
        for row in ds:
            rows.append({
                "task_id": str(row["task_id"]),
                "prompt": str(row.get("prompt") or ""),
                "canonical_solution": str(row.get("canonical_solution") or ""),
                "test": str(row.get("test") or ""),
                "entry_point": str(row.get("entry_point") or ""),
            })

        logger.info("HumanEval: downloaded %d problems", len(rows))
        _save_rows(self.data_dir, rows)

    def load_samples(self) -> list[CodePair]:
        """Emit TN pairs: canonical solution compared to itself (same-problem identity)."""
        rows = _load_rows(self.data_dir)
        if not rows:
            raise FileNotFoundError(
                f"HumanEval data not found at {self.data_dir}. "
                "Run loader.download() first."
            )

        pairs: list[CodePair] = []
        for row in rows:
            code = row["prompt"] + row["canonical_solution"]
            if not code.strip():
                continue
            pairs.append(CodePair(
                original_code=code,
                generated_code=code,
                language="python",
                benchmark="humaneval",
                category="honest-vs-honest",
                sample_id=f"humaneval-tn-{row['task_id'].replace('/', '-')}",
                metadata={
                    "label": "clean",
                    "task_id": row["task_id"],
                    "entry_point": row["entry_point"],
                },
            ))

        logger.info("HumanEval: %d TN pairs ready", len(pairs))
        return pairs

    def lookup(self) -> dict[str, dict]:
        """Return {task_id: row} for generator use; empty if not downloaded."""
        return {r["task_id"]: r for r in _load_rows(self.data_dir)}
