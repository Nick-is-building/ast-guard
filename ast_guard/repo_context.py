"""
Repo-context baseline: statistical sibling comparison.

Standalone mode lacks an original to diff against. The pair-mode strength
comes from a concrete baseline; when no original exists, the next-best
deterministic baseline is the statistical distribution of *other functions
the same author/repo has produced*. A function that is far outside the
distribution of its siblings is suspect even without per-pair comparison.

Public API:

    compute_repo_baseline(samples: list[str]) -> dict | None
        Aggregate per-function metrics across a list of code samples
        (typically other files from the same repo, or other code blocks
        from the same agent's session). Returns None when too few valid
        samples are available — the comparison is statistical and a
        baseline with fewer than _MIN_SAMPLES functions is not meaningful.

    flag_outliers(tree: ast.Module, baseline: dict) -> list[dict]
        Walk every function in ``tree`` and emit a finding for each that
        is an extreme statistical outlier on any tracked metric.

Tracked metrics, per function:
    - mccabe_complexity    (control-flow complexity)
    - if_count             (non-guard if-statements + match_case branches)
    - literal_count        (constant nodes, excluding docstrings)

Outlier rule for a given metric value ``v``:
    flag iff   v >  max(median + 2*stddev, 3*median, _ABS_FLOOR[metric])

The triple gate is intentional:
    - median + 2σ catches functions far from the typical distribution.
    - 3×median catches the case where the distribution is so tight that
      σ is near zero (every sibling function looks the same) and the +2σ
      gate alone would fire on tiny relative deltas.
    - absolute floor prevents firing on numerically-small outliers
      (mccabe=4 in a repo of mccabe=1 functions is not a hack).

Determinism: pure-stdlib statistics module; no random sampling; sorted
output. Returns identical results for identical inputs.
"""
from __future__ import annotations

import ast
import statistics
from typing import Optional

from ast_guard.analyzer import (
    calculate_node_complexity,
    count_literals,
    find_docstring_node_ids,
    find_guard_clauses,
)

__all__ = ["compute_repo_baseline", "flag_outliers"]

# A baseline below this many functions is not statistically meaningful.
_MIN_SAMPLES = 5

# Minimum value the target function must exceed before any outlier rule
# fires. Prevents flagging in-distribution-but-numerically-tiny functions.
_ABS_FLOOR = {
    "mccabe_complexity": 5,
    "if_count": 4,
    "literal_count": 10,
}

# Tracked metric → (score, message tag).
_METRIC_FINDING_SCORE = 30


def _per_function_metrics(tree: ast.Module) -> list[dict]:
    """Return a list of {name, mccabe, ifs, literals} dicts, one per function.

    Counts each function independently — nested functions get their own row.
    Module-level code is ignored: a baseline composed of module-level
    statements would be dominated by import lines and miss the actual
    target shape (function bodies).
    """
    docstring_ids = find_docstring_node_ids(tree)
    rows: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        guards = find_guard_clauses(node)

        ifs = 0
        for sub in ast.walk(node):
            if isinstance(sub, ast.If) and id(sub) not in guards:
                ifs += 1
            elif hasattr(ast, "match_case") and isinstance(sub, ast.match_case):
                ifs += 1

        rows.append({
            "name": node.name,
            "line": getattr(node, "lineno", None),
            "mccabe_complexity": calculate_node_complexity(node),
            "if_count": ifs,
            "literal_count": count_literals(node, docstring_ids),
        })
    return rows


def _safe_stddev(values: list[float]) -> float:
    """Return population stddev or 0.0 for inputs with < 2 distinct samples."""
    if len(values) < 2:
        return 0.0
    try:
        return statistics.pstdev(values)
    except statistics.StatisticsError:
        return 0.0


def compute_repo_baseline(samples: list[str]) -> Optional[dict]:
    """
    Build a statistical baseline from sibling code samples.

    Args:
        samples: List of code strings. Each string is parsed and its
            functions contribute one row each. Strings that fail to parse
            are skipped silently.

    Returns:
        A dict of the form

            {
                "n_functions": int,
                "n_samples": int,
                "metrics": {
                    "mccabe_complexity": {"median": float, "stddev": float, "max": float},
                    "if_count":          {"median": float, "stddev": float, "max": float},
                    "literal_count":     {"median": float, "stddev": float, "max": float},
                },
            }

        or ``None`` if fewer than 5 valid function samples were collected.
    """
    rows: list[dict] = []
    valid_samples = 0
    for sample in samples:
        try:
            tree = ast.parse(sample)
        except SyntaxError:
            continue
        sample_rows = _per_function_metrics(tree)
        if sample_rows:
            valid_samples += 1
            rows.extend(sample_rows)

    if len(rows) < _MIN_SAMPLES:
        return None

    out_metrics: dict = {}
    for key in ("mccabe_complexity", "if_count", "literal_count"):
        values = [float(r[key]) for r in rows]
        out_metrics[key] = {
            "median": statistics.median(values),
            "stddev": _safe_stddev(values),
            "max": max(values),
        }

    return {
        "n_functions": len(rows),
        "n_samples": valid_samples,
        "metrics": out_metrics,
    }


def _is_outlier(value: float, stats: dict, metric: str) -> bool:
    """True iff value exceeds all three gates (median+2σ, 3×median, abs floor)."""
    median = stats["median"]
    stddev = stats["stddev"]
    gate_sigma = median + 2 * stddev
    gate_median = 3 * median if median > 0 else _ABS_FLOOR[metric]
    gate_floor = _ABS_FLOOR[metric]
    return value > gate_sigma and value > gate_median and value > gate_floor


def flag_outliers(tree: ast.Module, baseline: dict) -> list[dict]:
    """
    Flag functions in ``tree`` whose metrics are extreme outliers relative to baseline.

    Args:
        tree: The parsed AST of the target code.
        baseline: A dict returned by ``compute_repo_baseline``.

    Returns:
        A list of findings, one per outlier function and metric combination:

            [
                {
                    "name": "solve",
                    "line": 12,
                    "metric": "mccabe_complexity",
                    "value": 42,
                    "median": 4.0,
                    "stddev": 1.2,
                    "score": 30,
                    "explanation": "Function 'solve' has McCabe complexity 42 — "
                                   "9.0× repo median (4.0) and beyond 2σ.",
                },
                ...
            ]

        Functions can produce multiple findings (one per outlier metric).
    """
    if not baseline or "metrics" not in baseline:
        return []

    findings: list[dict] = []
    target_rows = _per_function_metrics(tree)

    _METRIC_LABELS = {
        "mccabe_complexity": "McCabe complexity",
        "if_count": "if-count",
        "literal_count": "literal count",
    }

    for row in target_rows:
        for metric, stats in baseline["metrics"].items():
            value = float(row[metric])
            if not _is_outlier(value, stats, metric):
                continue
            median = stats["median"]
            ratio = (value / median) if median > 0 else float("inf")
            ratio_str = f"{ratio:.1f}×" if ratio != float("inf") else "∞"
            findings.append({
                "name": row["name"],
                "line": row["line"],
                "metric": metric,
                "value": int(value) if value.is_integer() else value,
                "median": median,
                "stddev": stats["stddev"],
                "score": _METRIC_FINDING_SCORE,
                "explanation": (
                    f"Function {row['name']!r} has {_METRIC_LABELS[metric]} {row[metric]} — "
                    f"{ratio_str} repo median ({median:g}) and beyond 2σ."
                ),
            })
    return findings
