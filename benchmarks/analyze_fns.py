"""
Analyze false-negative causes in an ast-guard MALT benchmark JSON.

Mirror of ``benchmarks/analyze_fps.py``. Filters a results set to
``label in {bypass_constraints, hardcoded_solution}`` AND ``detected == false``
(the hack-but-missed samples) and groups them by a coarse structural
fingerprint computed via ``ast``. Tells us which structural shapes the
detector is still missing, so candidate signals can be prioritised.

Reads either:
  - a top-level list of per-sample records, OR
  - ``{<benchmark>: {"details": [...]}}`` (the shape ``run_benchmark.py`` emits).

Each record is expected to expose at least:
  - ``category`` (MALT label)
  - ``detected`` (bool)
  - ``generated_code`` (str)   [preferred]
    or ``code`` / ``source`` as fallback fields.

Output: Markdown tables on stdout; optionally write to a file.

Usage:
    python3 -m benchmarks.analyze_fns benchmarks/data/malt_v2_2_0.json
    python3 -m benchmarks.analyze_fns benchmarks/data/malt_v2_2_0.json \\
        --out benchmarks/data/fn_breakdown_v2_2_0.md
    python3 -m benchmarks.analyze_fns benchmarks/data/malt_v2_2_0.json \\
        --max-examples 3 --top 25
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

# Labels we treat as "hacks" for the purposes of recall analysis. Matches the
# binary classification used in RESULTS.md.
_HACK_LABELS = frozenset({"bypass_constraints", "hardcoded_solution"})

# Snippet truncation for the example block.
_SNIPPET_MAX_LINES = 12
_SNIPPET_MAX_CHARS = 600


def _load_details(json_path: Path) -> list[dict]:
    with open(json_path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    # ``{<benchmark>: {"details": [...]}}`` shape.
    benchmark_data = next(iter(data.values()))
    return benchmark_data.get("details", [])


def _get_code(rec: dict) -> Optional[str]:
    for key in ("generated_code", "code", "source", "snippet"):
        v = rec.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _bucket_lines(n: int) -> str:
    if n <= 10:
        return "1-10"
    if n <= 30:
        return "11-30"
    if n <= 80:
        return "31-80"
    if n <= 200:
        return "81-200"
    return "200+"


def _bucket_ifs(n: int) -> str:
    if n == 0:
        return "0"
    if n <= 2:
        return "1-2"
    if n <= 4:
        return "3-4"
    if n <= 10:
        return "5-10"
    return "11+"


def _is_pure_literal(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_pure_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            k is not None and _is_pure_literal(k) and _is_pure_literal(v)
            for k, v in zip(node.keys, node.values)
        )
    return False


def _has_big_literal_dict(tree: ast.AST, min_size: int = 6) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict) and len(node.keys) >= min_size:
            if all(
                k is not None and isinstance(k, ast.Constant) and _is_pure_literal(v)
                for k, v in zip(node.keys, node.values)
            ):
                return True
    return False


def _has_literal_lookup_return(tree: ast.AST) -> bool:
    """``return TABLE[arg]`` / ``return TABLE.get(arg, ...)`` / ``return arg in {literals}``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        v = node.value
        if isinstance(v, ast.Subscript):
            return True
        if isinstance(v, ast.Call):
            func = v.func
            if isinstance(func, ast.Attribute) and func.attr == "get":
                return True
        if isinstance(v, ast.Compare) and len(v.ops) == 1 and isinstance(v.ops[0], ast.In):
            right = v.comparators[0]
            if isinstance(right, (ast.Set, ast.List, ast.Tuple)) and _is_pure_literal(right):
                return True
    return False


def _body_wrapped_in_try_except(tree: ast.AST) -> bool:
    """Any FunctionDef whose body is exactly one Try node."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            # Skip a leading docstring expression.
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            if len(body) == 1 and isinstance(body[0], ast.Try):
                return True
    return False


def _count_if_branches(tree: ast.AST) -> int:
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.If))


def _has_loop(tree: ast.AST) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, (ast.For, ast.While, ast.AsyncFor)):
            return True
    return False


def _returns_input_independent(tree: ast.Module) -> bool:
    """Use ast_guard.dataflow.analyze_input_independence with a relaxed copy."""
    try:
        from ast_guard.dataflow import analyze_input_independence
    except Exception:
        return False
    try:
        findings = analyze_input_independence(tree)
    except Exception:
        return False
    return bool(findings)


def _fingerprint(code: str) -> Optional[tuple]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    lines = code.count("\n") + 1
    return (
        ("big_literal_dict", _has_big_literal_dict(tree)),
        ("literal_lookup_return", _has_literal_lookup_return(tree)),
        ("body_is_try_except", _body_wrapped_in_try_except(tree)),
        ("ifs_bucket", _bucket_ifs(_count_if_branches(tree))),
        ("input_independent_returns", _returns_input_independent(tree)),
        ("has_loop", _has_loop(tree)),
        ("lines_bucket", _bucket_lines(lines)),
    )


def _fingerprint_label(fp: tuple) -> str:
    parts: list[str] = []
    for key, val in fp:
        if isinstance(val, bool):
            if val:
                parts.append(key)
        else:
            parts.append(f"{key}={val}")
    return ", ".join(parts) if parts else "(empty)"


def _truncate_snippet(code: str) -> str:
    lines = code.splitlines()
    if len(lines) > _SNIPPET_MAX_LINES:
        lines = lines[:_SNIPPET_MAX_LINES] + ["    # ... (truncated)"]
    out = "\n".join(lines)
    if len(out) > _SNIPPET_MAX_CHARS:
        out = out[:_SNIPPET_MAX_CHARS] + "\n# ... (truncated)"
    return out


def analyze(json_path: Path, top: int, max_examples: int) -> str:
    details = _load_details(json_path)

    misses = [
        r for r in details
        if r.get("category") in _HACK_LABELS and r.get("detected") is False
    ]

    if not misses:
        return "No hack-label false negatives found.\n"

    fp_counter: Counter[tuple] = Counter()
    fp_examples: dict[tuple, list[dict]] = defaultdict(list)
    by_label: Counter[str] = Counter()
    no_code = 0
    parse_errors = 0

    for rec in misses:
        by_label[rec.get("category", "?")] += 1
        code = _get_code(rec)
        if code is None:
            no_code += 1
            continue
        fp = _fingerprint(code)
        if fp is None:
            parse_errors += 1
            continue
        fp_counter[fp] += 1
        if len(fp_examples[fp]) < max_examples:
            fp_examples[fp].append({
                "sample_id": rec.get("sample_id", "?"),
                "label": rec.get("category", "?"),
                "code": code,
            })

    total_with_fp = sum(fp_counter.values())
    total = len(misses)

    lines: list[str] = []
    lines.append(f"# FN Breakdown — hack-label misses ({json_path.name})\n")
    lines.append(
        f"Total hack-label misses: **{total}** "
        f"(fingerprinted: {total_with_fp}, no code: {no_code}, parse errors: {parse_errors})\n"
    )

    lines.append("\n## By Label\n")
    lines.append("| Label | Count | % of misses |")
    lines.append("|---|---|---|")
    for lbl, cnt in by_label.most_common():
        pct = cnt / total * 100 if total else 0
        lines.append(f"| `{lbl}` | {cnt} | {pct:.1f} % |")

    lines.append("\n## Top Structural Fingerprints\n")
    lines.append("| Fingerprint | Count | % of fingerprinted |")
    lines.append("|---|---|---|")
    for fp, cnt in fp_counter.most_common(top):
        pct = cnt / total_with_fp * 100 if total_with_fp else 0
        lines.append(f"| `{_fingerprint_label(fp)}` | {cnt} | {pct:.1f} % |")

    lines.append("\n## Example Snippets\n")
    for fp, cnt in fp_counter.most_common(top):
        lines.append(f"### `{_fingerprint_label(fp)}` ({cnt} misses)\n")
        for ex in fp_examples[fp]:
            lines.append(f"**{ex['sample_id']}** ({ex['label']}):\n")
            lines.append("```python")
            lines.append(_truncate_snippet(ex["code"]))
            lines.append("```\n")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path, help="Path to malt_*.json results")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write Markdown output to this file")
    parser.add_argument("--top", type=int, default=20,
                        help="Number of top fingerprint buckets to show (default 20)")
    parser.add_argument("--max-examples", type=int, default=2,
                        help="Snippets per bucket (default 2)")
    args = parser.parse_args()

    report = analyze(args.json_file, top=args.top, max_examples=args.max_examples)
    print(report)
    if args.out:
        args.out.write_text(report)
        print(f"\nWritten to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
