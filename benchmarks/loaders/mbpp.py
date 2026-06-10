"""
Loader for the MBPP (Mostly Basic Python Programming) benchmark.

Source: google-research-datasets/mbpp (HuggingFace, public, Apache-2.0).
Fields verified on 2026-06-10: task_id (int), text (str), code (str),
  test_list (list[str]), test_setup_code (str), challenge_test_list (list[str]).

Two roles in pair-mode evaluation:
  1. TN backbone — load_samples() emits honest-vs-honest pairs (rotation):
     original = problem[i].code, generated = problem[i+1].code.
     Both are reference solutions; expect CLEAN. Measures FPR of pair mode.
  2. Cross-loader lookup — lookup() returns {task_id: code} so that other
     loaders (e.g. school_of_hacks) can pull MBPP reference solutions.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_HF_REPO = "google-research-datasets/mbpp"
_SPLITS = ("train", "validation", "test", "prompt")
_CACHE_FILE = "mbpp_rows.json"


def _cache_path(data_dir: Path) -> Path:
    return data_dir / _CACHE_FILE


def _load_rows(data_dir: Path) -> list[dict]:
    p = _cache_path(data_dir)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read MBPP cache %s: %s", p, exc)
        return []


def _save_rows(data_dir: Path, rows: list[dict]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = _cache_path(data_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_cache_path(data_dir))


@register
class MbppLoader(BenchmarkLoader):
    """Loads MBPP reference solutions; emits TN (honest-vs-honest) pairs."""

    name = "mbpp"

    def download(self) -> None:
        """Download all MBPP splits via HuggingFace datasets and cache as JSON."""
        try:
            from datasets import load_dataset  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "pip install datasets  (required to download MBPP)"
            ) from exc

        rows: list[dict] = []
        seen: set[int] = set()
        for split in _SPLITS:
            try:
                ds = load_dataset(_HF_REPO, split=split, trust_remote_code=False)
            except Exception as exc:
                logger.warning("MBPP split %r not available: %s", split, exc)
                continue
            for row in ds:
                tid = int(row["task_id"])
                if tid in seen:
                    continue
                seen.add(tid)
                rows.append({
                    "task_id": tid,
                    "text": str(row.get("text") or ""),
                    "code": str(row.get("code") or ""),
                    "test_list": list(row.get("test_list") or []),
                })

        logger.info("MBPP: downloaded %d unique problems", len(rows))
        _save_rows(self.data_dir, rows)

    def load_samples(self) -> list[CodePair]:
        """Emit TN pairs: problem[i].code vs problem[i+1].code (rotation).

        Neither side is a hack; both are MBPP reference solutions.
        Expected verdict for all pairs: CLEAN.
        """
        rows = _load_rows(self.data_dir)
        if not rows:
            raise FileNotFoundError(
                f"MBPP data not found at {self.data_dir}. "
                "Run with --download or call loader.download()."
            )

        valid = [r for r in rows if r.get("code", "").strip()]
        n = len(valid)
        pairs: list[CodePair] = []
        for i, row in enumerate(valid):
            nxt = valid[(i + 1) % n]
            pairs.append(CodePair(
                original_code=row["code"],
                generated_code=nxt["code"],
                language="python",
                benchmark="mbpp",
                category="honest-vs-honest",
                sample_id=f"mbpp-tn-{row['task_id']}-{nxt['task_id']}",
                metadata={
                    "label": "clean",
                    "task_id_orig": row["task_id"],
                    "task_id_gen": nxt["task_id"],
                    "text_orig": row["text"][:120],
                },
            ))

        logger.info("MBPP: %d TN pairs ready", len(pairs))
        return pairs

    def lookup(self) -> dict[int, str]:
        """Return {task_id: code} for cross-loader use; empty if not downloaded."""
        return {r["task_id"]: r["code"] for r in _load_rows(self.data_dir) if r.get("code")}
