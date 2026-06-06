"""
Analyse False-Positive-Ursachen in einem MALT-Benchmark-JSON.

Liest eine benchmarks/data/malt_*.json, filtert auf category=normal +
detected=true und zählt welche checks_fired / top_findings-Patterns
die verbleibenden FPs verursachen.

Ausgabe: Markdown-Tabellen auf stdout; optional als Datei speichern.

Verwendung:
    python3 -m benchmarks.analyze_fps benchmarks/data/malt_v2_1_1.json
    python3 -m benchmarks.analyze_fps benchmarks/data/malt_v2_1_1.json \
        --out benchmarks/data/fp_breakdown_v2_1_1.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


_FINDING_PREFIX_RE = re.compile(r"^\[([^\]]+)\]")


def _finding_key(s: str) -> str:
    """Extract the bracketed prefix like '[file_write_unknown_target +10]'."""
    m = _FINDING_PREFIX_RE.match(s)
    return f"[{m.group(1)}]" if m else s[:60]


def analyze(json_path: Path) -> str:
    with open(json_path) as f:
        data = json.load(f)

    # Support both top-level list and {"malt": {..., "details": [...]}} shapes
    if isinstance(data, list):
        details = data
    else:
        benchmark_data = next(iter(data.values()))
        details = benchmark_data.get("details", [])

    fps = [
        r for r in details
        if r.get("category") == "normal" and r.get("detected") is True
    ]

    if not fps:
        return "No normal FPs found.\n"

    checks_counter: Counter[str] = Counter()
    findings_counter: Counter[str] = Counter()
    combo_counter: Counter[tuple[str, ...]] = Counter()

    for rec in fps:
        fired = rec.get("checks_fired", [])
        for chk in fired:
            checks_counter[chk] += 1
        combo_counter[tuple(sorted(fired))] += 1

        for finding in rec.get("top_findings", []):
            findings_counter[_finding_key(finding)] += 1

    total = len(fps)
    lines: list[str] = []
    lines.append(f"# FP Breakdown — normal category (v2.1.1)\n")
    lines.append(f"Total normal FPs: **{total}**\n")

    lines.append("\n## Checks Fired (each FP may fire multiple)\n")
    lines.append("| Check | Count | % of FPs |")
    lines.append("|---|---|---|")
    for chk, cnt in checks_counter.most_common():
        lines.append(f"| `{chk}` | {cnt} | {cnt/total*100:.1f} % |")

    lines.append("\n## Top-Findings Patterns (first 4 per FP, deduplicated per FP)\n")
    lines.append("| Pattern | Count | % of FPs |")
    lines.append("|---|---|---|")
    for pat, cnt in findings_counter.most_common(25):
        lines.append(f"| `{pat}` | {cnt} | {cnt/total*100:.1f} % |")

    lines.append("\n## Most Common Check Combinations\n")
    lines.append("| Combination | Count | % of FPs |")
    lines.append("|---|---|---|")
    for combo, cnt in combo_counter.most_common(15):
        label = " + ".join(combo) if combo else "(none)"
        lines.append(f"| `{label}` | {cnt} | {cnt/total*100:.1f} % |")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path, help="Path to malt_*.json")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write Markdown output to this file")
    args = parser.parse_args()

    report = analyze(args.json_file)
    print(report)
    if args.out:
        args.out.write_text(report)
        print(f"\nWritten to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
