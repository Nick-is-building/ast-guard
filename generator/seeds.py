"""Load seed problems (problem_text, visible_tests, hidden_tests) for generation."""

from __future__ import annotations

import ast as _ast
import copy
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

_MBPP_DEFAULT = Path.home() / ".ast-guard" / "benchmarks" / "mbpp" / "mbpp_rows.json"
_HUMANEVAL_DEFAULT = Path.home() / ".ast-guard" / "benchmarks" / "humaneval" / "humaneval_rows.json"
_APPS_DEFAULT = Path.home() / ".ast-guard" / "benchmarks" / "apps" / "apps_rows.json"


@dataclass(frozen=True)
class Seed:
    """A single seed problem ready for hack-pair generation."""

    seed_id: str
    problem_text: str
    visible_tests: tuple[str, ...]   # go into the LLM prompt
    hidden_tests: tuple[str, ...]    # held back; used only by verify.py
    source: str                      # e.g. "mbpp", "humaneval", "apps", "custom"
    reference_code: str = ""         # reference solution when available
    test_format: str = "assert"      # "assert" | "io"  (io = JSON-encoded input/output pairs)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

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
    return tests[:n_visible], tests[n_visible:]


# ---------------------------------------------------------------------------
# MBPP
# ---------------------------------------------------------------------------

def load_mbpp(
    cache_path: Path | None = None,
    n_visible: int = 1,
    max_seeds: int | None = None,
    skip_seeds: int = 0,
) -> list[Seed]:
    """Load MBPP seeds from the local cache written by MbppLoader.download()."""
    path = cache_path or _MBPP_DEFAULT
    if not path.exists():
        raise FileNotFoundError(
            f"MBPP cache not found at {path}.\n"
            "Run: python -c \"from benchmarks.loaders.mbpp import MbppLoader; "
            "MbppLoader().download()\""
        )

    rows: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    if skip_seeds > 0:
        rows = rows[skip_seeds:]
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

    logger.info("MBPP seeds: %d loaded, %d skipped (insufficient tests)", len(seeds), skipped)
    return seeds


# ---------------------------------------------------------------------------
# HumanEval
# ---------------------------------------------------------------------------

class _SubstituteCandidate(_ast.NodeTransformer):
    """Replace all Name('candidate') nodes with Name(entry_point)."""

    def __init__(self, entry_point: str) -> None:
        self.entry_point = entry_point

    def visit_Name(self, node: _ast.Name) -> _ast.Name:
        if node.id == "candidate":
            return _ast.Name(id=self.entry_point, ctx=node.ctx)
        return node


def _extract_humaneval_tests(test_code: str, entry_point: str) -> list[str]:
    """
    Extract assert statements from a HumanEval check() function.

    Replaces 'candidate' with the actual entry_point name using AST
    substitution (safer than string replacement across string literals).
    """
    try:
        tree = _ast.parse(test_code)
    except SyntaxError:
        return []

    transformer = _SubstituteCandidate(entry_point)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.FunctionDef) and node.name == "check":
            results: list[str] = []
            for stmt in node.body:
                if isinstance(stmt, _ast.Assert):
                    try:
                        new_stmt = transformer.visit(copy.deepcopy(stmt))
                        results.append(_ast.unparse(new_stmt))
                    except Exception:
                        continue
            return results
    return []


def load_humaneval(
    cache_path: Path | None = None,
    n_visible: int = 1,
    max_seeds: int | None = None,
    skip_seeds: int = 0,
) -> list[Seed]:
    """Load HumanEval seeds from the local cache written by HumanEvalLoader.download()."""
    path = cache_path or _HUMANEVAL_DEFAULT
    if not path.exists():
        raise FileNotFoundError(
            f"HumanEval cache not found at {path}.\n"
            "Run: python -c \"from benchmarks.loaders.humaneval import HumanEvalLoader; "
            "HumanEvalLoader().download()\""
        )

    rows: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    if skip_seeds > 0:
        rows = rows[skip_seeds:]
    seeds: list[Seed] = []
    skipped = 0

    for row in rows:
        entry_point = row.get("entry_point") or ""
        tests = _extract_humaneval_tests(row.get("test") or "", entry_point)
        if not tests:
            skipped += 1
            continue

        split = _split_tests(tests, n_visible)
        if split is None:
            skipped += 1
            continue

        visible, hidden = split
        # Full code = prompt (signature + docstring) + canonical_solution (body)
        reference_code = (row.get("prompt") or "") + (row.get("canonical_solution") or "")
        seeds.append(Seed(
            seed_id=f"humaneval-{row['task_id'].replace('/', '-')}",
            problem_text=(row.get("prompt") or "").strip(),
            visible_tests=tuple(visible),
            hidden_tests=tuple(hidden),
            source="humaneval",
            reference_code=reference_code.strip(),
        ))

        if max_seeds is not None and len(seeds) >= max_seeds:
            break

    logger.info(
        "HumanEval seeds: %d loaded, %d skipped (no tests / insufficient split)",
        len(seeds), skipped,
    )
    return seeds


# ---------------------------------------------------------------------------
# APPS
# ---------------------------------------------------------------------------

def load_apps(
    cache_path: Path | None = None,
    n_visible: int = 1,
    max_seeds: int | None = None,
    skip_seeds: int = 0,
) -> list[Seed]:
    """
    Load APPS seeds from the local cache written by AppsLoader.download().

    Tests are stored as JSON-encoded {"input": str, "output": str} pairs
    (test_format="io"). The IO runner in verify.py handles execution.
    """
    path = cache_path or _APPS_DEFAULT
    if not path.exists():
        raise FileNotFoundError(
            f"APPS cache not found at {path}.\n"
            "Run: python -c \"from benchmarks.loaders.apps import AppsLoader; "
            "AppsLoader().download()\""
        )

    rows: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    if skip_seeds > 0:
        rows = rows[skip_seeds:]
    seeds: list[Seed] = []
    skipped = 0

    for row in rows:
        inputs = row.get("inputs") or []
        outputs = row.get("outputs") or []
        if len(inputs) != len(outputs) or not inputs:
            skipped += 1
            continue

        # Encode each (input, output) pair as a JSON string for uniform storage.
        tests = [
            json.dumps({"input": str(inp), "output": str(out)})
            for inp, out in zip(inputs, outputs)
        ]
        split = _split_tests(tests, n_visible)
        if split is None:
            skipped += 1
            continue

        visible, hidden = split
        sols = row.get("solutions") or []
        reference_code = str(sols[0]) if sols else ""

        seeds.append(Seed(
            seed_id=f"apps-{row['problem_id']}",
            problem_text=(row.get("question") or "").strip(),
            visible_tests=tuple(visible),
            hidden_tests=tuple(hidden),
            source="apps",
            reference_code=reference_code,
            test_format="io",
        ))

        if max_seeds is not None and len(seeds) >= max_seeds:
            break

    logger.info(
        "APPS seeds: %d loaded, %d skipped (no IO / insufficient split)",
        len(seeds), skipped,
    )
    return seeds


# ---------------------------------------------------------------------------
# Custom JSON seeds
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Combined iterator
# ---------------------------------------------------------------------------

def iter_seeds(
    mbpp_path: Path | None = None,
    humaneval_path: Path | None = None,
    apps_path: Path | None = None,
    custom_paths: list[Path] | None = None,
    n_visible: int = 1,
    max_seeds: int | None = None,
    skip_seeds: int = 0,
) -> Iterator[Seed]:
    """
    Yield all seeds from MBPP, HumanEval, APPS, and any custom files.

    Each source is attempted in order; a missing cache is logged as a warning
    rather than raised, so single-source and custom-only runs still work.
    skip_seeds skips the first N rows of each source before yielding.
    """
    count = 0

    sources = [
        ("MBPP", lambda: load_mbpp(mbpp_path, n_visible=n_visible, max_seeds=max_seeds, skip_seeds=skip_seeds)),
        ("HumanEval", lambda: load_humaneval(humaneval_path, n_visible=n_visible, max_seeds=max_seeds, skip_seeds=skip_seeds)),
        ("APPS", lambda: load_apps(apps_path, n_visible=n_visible, max_seeds=max_seeds, skip_seeds=skip_seeds)),
    ]

    for name, loader in sources:
        if max_seeds is not None and count >= max_seeds:
            return
        try:
            for seed in loader():
                yield seed
                count += 1
                if max_seeds is not None and count >= max_seeds:
                    return
        except FileNotFoundError as exc:
            logger.warning("%s not available: %s", name, exc)

    for cp in (custom_paths or []):
        if max_seeds is not None and count >= max_seeds:
            return
        for seed in load_custom(cp, n_visible=n_visible):
            yield seed
            count += 1
            if max_seeds is not None and count >= max_seeds:
                return
