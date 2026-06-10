"""Load seed problems (problem_text, visible_tests, hidden_tests) for generation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

# Mirrors the path used by benchmarks/loaders/mbpp.py so the generator
# reuses whatever the user already downloaded.
_MBPP_DEFAULT = Path.home() / ".ast-guard" / "benchmarks" / "mbpp" / "mbpp_rows.json"


@dataclass(frozen=True)
class Seed:
    """A single seed problem ready for hack-pair generation."""

    seed_id: str
    problem_text: str
    visible_tests: tuple[str, ...]   # go into the LLM prompt
    hidden_tests: tuple[str, ...]    # held back; used only by verify.py
    source: str                      # e.g. "mbpp", "custom"
    reference_code: str = ""         # reference solution when available


def _split_tests(
    tests: list[str],
    n_visible: int,
) -> tuple[list[str], list[str]] | None:
    """
    Partition *tests* into (visible, hidden).

    Returns None when the list cannot be split — caller must skip the seed.
    Requires at least n_visible + 1 tests so there is always ≥1 hidden test.
    """
    if len(tests) < n_visible + 1:
        return None
    visible = tests[:n_visible]
    hidden = tests[n_visible:]
    return visible, hidden


def load_mbpp(
    cache_path: Path | None = None,
    n_visible: int = 1,
    max_seeds: int | None = None,
) -> list[Seed]:
    """
    Load MBPP seeds from the local cache written by MbppLoader.download().

    *n_visible* tests go into the prompt; the rest become hidden tests.
    Seeds with fewer than n_visible + 1 tests are silently skipped.
    Pass *max_seeds* to cap the result (useful for quick smoke tests).
    """
    path = cache_path or _MBPP_DEFAULT
    if not path.exists():
        raise FileNotFoundError(
            f"MBPP cache not found at {path}.\n"
            "Run: python -c \"from benchmarks.loaders.mbpp import MbppLoader; "
            "MbppLoader().download()\""
        )

    rows: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    seeds: list[Seed] = []
    skipped = 0

    for row in rows:
        tests = [t for t in (row.get("test_list") or []) if isinstance(t, str) and t.strip()]
        split = _split_tests(tests, n_visible)
        if split is None:
            skipped += 1
            continue

        visible, hidden = split
        seeds.append(Seed(
            seed_id=f"mbpp-{row['task_id']}",
            problem_text=(row.get("text") or "").strip(),
            visible_tests=tuple(visible),
            hidden_tests=tuple(hidden),
            source="mbpp",
            reference_code=(row.get("code") or "").strip(),
        ))

        if max_seeds is not None and len(seeds) >= max_seeds:
            break

    logger.info(
        "MBPP seeds: %d loaded, %d skipped (insufficient tests)", len(seeds), skipped
    )
    return seeds


def load_custom(path: Path, n_visible: int = 1) -> list[Seed]:
    """
    Load seeds from a JSON file with records of the shape:

        {
            "seed_id": "my-problem-1",        // required
            "problem_text": "Write a ...",    // required
            "test_list": ["assert ...", ...], // required, ≥2 entries
            "reference_code": "def ...",      // optional
            "source": "custom"                // optional, defaults to "custom"
        }

    Records that cannot be split with *n_visible* are skipped with a warning.
    """
    rows: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    seeds: list[Seed] = []

    for i, row in enumerate(rows):
        sid = str(row.get("seed_id") or f"custom-{i}")
        text = str(row.get("problem_text") or "").strip()
        tests = [t for t in (row.get("test_list") or []) if isinstance(t, str) and t.strip()]

        if not text:
            logger.warning("Custom seed %r: missing problem_text, skipping", sid)
            continue

        split = _split_tests(tests, n_visible)
        if split is None:
            logger.warning(
                "Custom seed %r: need ≥%d tests, got %d — skipping",
                sid, n_visible + 1, len(tests),
            )
            continue

        visible, hidden = split
        seeds.append(Seed(
            seed_id=sid,
            problem_text=text,
            visible_tests=tuple(visible),
            hidden_tests=tuple(hidden),
            source=str(row.get("source") or "custom"),
            reference_code=str(row.get("reference_code") or "").strip(),
        ))

    logger.info("Custom seeds: %d loaded from %s", len(seeds), path)
    return seeds


def iter_seeds(
    mbpp_path: Path | None = None,
    custom_paths: list[Path] | None = None,
    n_visible: int = 1,
    max_seeds: int | None = None,
) -> Iterator[Seed]:
    """
    Yield all seeds from MBPP (if available) and any custom files.

    MBPP is attempted first; missing cache is logged as a warning rather than
    raised so custom-only runs still work.
    """
    count = 0

    try:
        for seed in load_mbpp(mbpp_path, n_visible=n_visible, max_seeds=max_seeds):
            yield seed
            count += 1
            if max_seeds is not None and count >= max_seeds:
                return
    except FileNotFoundError as exc:
        logger.warning("MBPP not available: %s", exc)

    for cp in (custom_paths or []):
        for seed in load_custom(cp, n_visible=n_visible):
            yield seed
            count += 1
            if max_seeds is not None and count >= max_seeds:
                return
