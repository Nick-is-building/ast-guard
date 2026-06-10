"""
Loader for the APPS (Automated Programming Progress Standard) benchmark.

Source: codeparrot/apps (HuggingFace, public).
Fields: problem_id (int), question (str), solutions (str, JSON list),
  input_output (str, JSON dict with "inputs"/"outputs" arrays),
  difficulty (str: introductory / interview / competition), fn_name (str|None).

Only stdin/stdout problems are loaded (fn_name == null). Function-call
style problems use a different test format that requires a separate runner.

Default difficulty: introductory (~2,000–3,000 problems after filtering).

Role in pair-mode evaluation:
  TN backbone — load_samples() emits honest-vs-honest pairs using the
  first reference solution compared to itself (same-problem identity).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_HF_REPO = "codeparrot/apps"
_CACHE_FILE = "apps_rows.json"
DEFAULT_DIFFICULTY = "introductory"


def _cache_path(data_dir: Path) -> Path:
    return data_dir / _CACHE_FILE


def _load_rows(data_dir: Path) -> list[dict]:
    p = _cache_path(data_dir)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read APPS cache %s: %s", p, exc)
        return []


def _save_rows(data_dir: Path, rows: list[dict]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = _cache_path(data_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_cache_path(data_dir))


@register
class AppsLoader(BenchmarkLoader):
    """Loads APPS reference solutions; emits TN (honest-vs-honest) pairs."""

    name = "apps"

    def download(self, difficulty: str = DEFAULT_DIFFICULTY) -> None:
        """
        Download APPS (introductory by default) and cache as JSON.

        Only stdin/stdout problems are kept (fn_name == null).
        Problems without valid input_output data are skipped.
        """
        try:
            from datasets import load_dataset  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "pip install datasets  (required to download APPS)"
            ) from exc

        ds = load_dataset(_HF_REPO, split="train", trust_remote_code=False)
        rows: list[dict] = []
        skipped = 0

        for row in ds:
            if row.get("difficulty") != difficulty:
                continue
            # Function-call style needs a different runner; skip for now.
            if row.get("fn_name"):
                skipped += 1
                continue

            try:
                io = json.loads(row.get("input_output") or "{}")
            except json.JSONDecodeError:
                skipped += 1
                continue

            inputs = io.get("inputs") or []
            outputs = io.get("outputs") or []
            if not inputs or len(inputs) != len(outputs):
                skipped += 1
                continue

            try:
                sols = json.loads(row.get("solutions") or "[]")
            except json.JSONDecodeError:
                sols = []

            rows.append({
                "problem_id": int(row.get("problem_id") or 0),
                "question": str(row.get("question") or "").strip(),
                "solutions": [str(s) for s in sols if s],
                "inputs": [str(x) for x in inputs],
                "outputs": [str(x) for x in outputs],
                "difficulty": difficulty,
            })

        logger.info(
            "APPS: downloaded %d %s problems (%d skipped)",
            len(rows), difficulty, skipped,
        )
        _save_rows(self.data_dir, rows)

    def load_samples(self) -> list[CodePair]:
        """Emit TN pairs: first reference solution compared to itself."""
        rows = _load_rows(self.data_dir)
        if not rows:
            raise FileNotFoundError(
                f"APPS data not found at {self.data_dir}. "
                "Run loader.download() first."
            )

        pairs: list[CodePair] = []
        for row in rows:
            sols = row.get("solutions") or []
            if not sols:
                continue
            code = sols[0]
            if not code.strip():
                continue
            pairs.append(CodePair(
                original_code=code,
                generated_code=code,
                language="python",
                benchmark="apps",
                category="honest-vs-honest",
                sample_id=f"apps-tn-{row['problem_id']}",
                metadata={
                    "label": "clean",
                    "problem_id": row["problem_id"],
                    "difficulty": row.get("difficulty"),
                },
            ))

        logger.info("APPS: %d TN pairs ready", len(pairs))
        return pairs

    def lookup(self) -> dict[int, dict]:
        """Return {problem_id: row} for generator use; empty if not downloaded."""
        return {r["problem_id"]: r for r in _load_rows(self.data_dir)}
