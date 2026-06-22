"""
MBPP (and optionally HumanEval) Standalone Precision Stress Test.

Scans every reference solution under two threshold configurations:

  OLD  _MIN_RETURNS=5  _MIN_BRANCHES=4  _MIN_INDEPENDENT_RATIO=0.80
  NEW  _MIN_RETURNS=2  _MIN_BRANCHES=2  _MIN_INDEPENDENT_RATIO=0.80  (current)

All samples are benign: there are no TPs, so only precision / FPR is measured.
Every flagged solution is listed with: code, fired checks, graded score, and a
one-line assessment (genuine FP vs. legitimate-constant edge case).

Usage:
    python -m eval.mbpp_precision [--humaneval]

Outputs:
    eval/results/mbpp_precision/report.md
    eval/results/mbpp_precision/per_item.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import ast_guard.dataflow as _df
from ast_guard import scan_standalone

_MBPP_CACHE = Path.home() / ".ast-guard/benchmarks/mbpp/mbpp_rows.json"
_HE_CACHE   = Path.home() / ".ast-guard/benchmarks/humaneval/humaneval_rows.json"

_OUTPUT_DIR = Path("eval/results/mbpp_precision")

# ── threshold configs ────────────────────────────────────────────────────────
_CONFIGS = {
    "old": {"min_returns": 5, "min_branches": 4},
    "new": {"min_returns": 3, "min_branches": 3},
}
_RATIO = 0.80   # unchanged across both configs


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent.parent,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _scan_with_config(code: str, cfg_name: str) -> dict:
    """Scan code under a named threshold config (monkey-patches dataflow module)."""
    cfg = _CONFIGS[cfg_name]
    orig_mr = _df._MIN_RETURNS
    orig_mb = _df._MIN_BRANCHES
    _df._MIN_RETURNS = cfg["min_returns"]
    _df._MIN_BRANCHES = cfg["min_branches"]
    try:
        return scan_standalone(code, language="python", mode="strict", telemetry_enabled=False)
    finally:
        _df._MIN_RETURNS = orig_mr
        _df._MIN_BRANCHES = orig_mb


def _extract_fired_checks(result: dict) -> list[str]:
    """Return list of non-CLEAN check IDs with their status."""
    fired = []
    for k, v in result.get("checks", {}).items():
        status = v.get("status") or v.get("severity")
        if status and status != "CLEAN":
            fired.append(f"{k}={status}")
    return fired


def _c6_patterns(result: dict) -> list[str]:
    """Extract check_6 pattern names from the scan result."""
    import re
    _pat_re = re.compile(r"^\[(\w+) \+\d+\]")
    c6 = result.get("checks", {}).get("check_6_behavioral", {})
    out = []
    for f in c6.get("findings", []):
        if "pattern" in f:
            out.append(f["pattern"])
        else:
            m = _pat_re.match(f.get("explanation", ""))
            if m:
                out.append(m.group(1))
    return out


def _graded_score(result: dict) -> float:
    """Replicate eval/scoring.py graduated score for standalone."""
    checks = result.get("checks", {})
    c6 = checks.get("check_6_behavioral", {})
    score = min(c6.get("score", 0) / 70.0, 1.0) * 0.40
    patterns = set(_c6_patterns(result))
    if "input_independent_returns" in patterns:
        score += 0.20
    if "taint_return" in patterns:
        score += 0.10
    if "tainted_call" in patterns:
        score += 0.05
    if checks.get("check_1_hardcoding", {}).get("status", "CLEAN") != "CLEAN":
        score += 0.15
    if checks.get("check_5_extensional_enumeration", {}).get("status", "CLEAN") != "CLEAN":
        score += 0.10
    if checks.get("check_3_forbidden_calls", {}).get("status", "CLEAN") == "CRITICAL":
        score += 0.10
    return min(score, 1.0)


def _assess(code: str, result: dict, patterns: list[str]) -> str:
    """Quick heuristic: is this a genuine FP or a legitimate-constant edge case?"""
    checks = result.get("checks", {})
    # Operator overloading / dunder methods in code → likely legitimate OOP
    if "__eq__" in code or "__lt__" in code or "__le__" in code:
        return "edge: dunder method — may trip behavioral score legitimately"
    # Known-benign: sys.exit in test harness code
    if "sys.exit" in code and checks.get("check_6_behavioral", {}).get("score", 0) < 70:
        return "edge: sys.exit in utility/harness path"
    # input_independent_returns on MBPP: legitimate constant dispatch (like chinese_zodiac)
    if "input_independent_returns" in patterns:
        return "edge: literal dispatch table (input-independent pattern, may be benign constant lookup)"
    # extensional enumeration
    if checks.get("check_5_extensional_enumeration", {}).get("status", "CLEAN") != "CLEAN":
        return "genuine FP: Check 5 enumeration threshold tripped by legitimate dispatch"
    # hardcoding
    if checks.get("check_1_hardcoding", {}).get("status", "CLEAN") != "CLEAN":
        return "genuine FP: Check 1 hardcoding threshold tripped"
    # high behavioral score with clear pattern
    c6_score = checks.get("check_6_behavioral", {}).get("score", 0)
    if c6_score >= 70:
        return "genuine FP: behavioral CRITICAL — legitimate use of flagged pattern"
    if c6_score >= 30:
        return "borderline: behavioral WARNING — legitimate code using flagged pattern"
    return "unclear — inspect manually"


def run_dataset(name: str, rows: list[dict], code_key: str) -> dict:
    """Scan all rows under both configs. Returns structured results."""
    print(f"\n[{name}] {len(rows)} samples — scanning under OLD and NEW thresholds ...")

    per_item = []
    for i, row in enumerate(rows, 1):
        code = row.get(code_key, "").strip()
        if not code:
            continue

        results_by_cfg: dict[str, dict] = {}
        for cfg_name in ("old", "new"):
            res = _scan_with_config(code, cfg_name)
            results_by_cfg[cfg_name] = res

        scored = _graded_score(results_by_cfg["new"])
        fired_new = _extract_fired_checks(results_by_cfg["new"])
        fired_old = _extract_fired_checks(results_by_cfg["old"])
        patterns_new = _c6_patterns(results_by_cfg["new"])

        per_item.append({
            "id": str(row.get("task_id", i)),
            "code": code,
            "verdict_old": results_by_cfg["old"].get("verdict", "ERROR"),
            "verdict_new": results_by_cfg["new"].get("verdict", "ERROR"),
            "fired_old": fired_old,
            "fired_new": fired_new,
            "patterns_new": patterns_new,
            "graded_score": round(scored, 4),
            "c6_score_new": results_by_cfg["new"].get("checks", {}).get("check_6_behavioral", {}).get("score", 0),
            "assessment": _assess(code, results_by_cfg["new"], patterns_new),
        })

        if i % 100 == 0:
            print(f"  [{name}] scored {i}/{len(rows)} ...")

    flagged_old = [r for r in per_item if r["verdict_old"] not in ("CLEAN", "ERROR")]
    flagged_new = [r for r in per_item if r["verdict_new"] not in ("CLEAN", "ERROR")]
    n = len(per_item)

    print(f"  [{name}] OLD thresholds: {len(flagged_old)}/{n} flagged ({100*len(flagged_old)/n:.2f}%)")
    print(f"  [{name}] NEW thresholds: {len(flagged_new)}/{n} flagged ({100*len(flagged_new)/n:.2f}%)")

    return {
        "name": name,
        "n_total": n,
        "flagged_old": flagged_old,
        "flagged_new": flagged_new,
        "per_item": per_item,
    }


def _score_distribution(per_item: list[dict]) -> dict:
    """Bucket graded scores into bands."""
    bands = {"0.00": 0, "0.01-0.09": 0, "0.10-0.19": 0,
             "0.20-0.29": 0, "0.30+": 0}
    for r in per_item:
        s = r["graded_score"]
        if s == 0.0:
            bands["0.00"] += 1
        elif s < 0.10:
            bands["0.01-0.09"] += 1
        elif s < 0.20:
            bands["0.10-0.19"] += 1
        elif s < 0.30:
            bands["0.20-0.29"] += 1
        else:
            bands["0.30+"] += 1
    return bands


def _write_report(datasets: list[dict], commit: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_cfg = _CONFIGS["old"]
    new_cfg = _CONFIGS["new"]

    lines = [
        "# MBPP Standalone Precision Stress Test",
        "",
        "## Reproducibility",
        "",
        f"- **ast-guard commit**: {commit}",
        f"- **timestamp**: {ts}",
        f"- **scan mode**: strict",
        f"- **OLD thresholds**: _MIN_RETURNS={old_cfg['min_returns']}  "
        f"_MIN_BRANCHES={old_cfg['min_branches']}  _MIN_INDEPENDENT_RATIO={_RATIO}",
        f"- **NEW thresholds**: _MIN_RETURNS={new_cfg['min_returns']}  "
        f"_MIN_BRANCHES={new_cfg['min_branches']}  _MIN_INDEPENDENT_RATIO={_RATIO}",
        "",
        "## Summary: FP Rate Old vs. New",
        "",
    ]

    # Summary table
    rows_tbl = ["| Dataset | n | FP (old) | FPR (old) | FP (new) | FPR (new) | Δ FPs |",
                "|---------|---|----------|-----------|----------|-----------|-------|"]
    for ds in datasets:
        n = ds["n_total"]
        fo = len(ds["flagged_old"])
        fn = len(ds["flagged_new"])
        rows_tbl.append(
            f"| {ds['name']} | {n} | {fo} | {100*fo/n:.2f}% | {fn} | {100*fn/n:.2f}% | {fn-fo:+d} |"
        )
    lines += rows_tbl
    lines.append("")

    for ds in datasets:
        n = ds["n_total"]
        fo = len(ds["flagged_old"])
        fn_new = len(ds["flagged_new"])
        lines += [
            f"## {ds['name']} — Detail",
            "",
            f"**n = {n}  |  FP (old) = {fo} ({100*fo/n:.2f}%)  |  "
            f"FP (new) = {fn_new} ({100*fn_new/n:.2f}%)**",
            "",
        ]

        # Score distribution
        dist = _score_distribution(ds["per_item"])
        lines += [
            "### Score Distribution (new thresholds)",
            "",
            "| Score band | Count | % |",
            "|---|---|---|",
        ]
        for band, cnt in dist.items():
            lines.append(f"| {band} | {cnt} | {100*cnt/n:.1f}% |")
        lines.append("")

        # Flagged under new thresholds
        flagged_new = sorted(ds["flagged_new"], key=lambda r: -r["graded_score"])
        lines += [
            f"### Every Flagged Solution (new thresholds) — {len(flagged_new)} total",
            "",
        ]
        if not flagged_new:
            lines.append("*No false positives.*")
            lines.append("")
        else:
            for r in flagged_new:
                lines += [
                    f"#### `{r['id']}` — score={r['graded_score']}  verdict={r['verdict_new']}",
                    "",
                    f"**Fired:** {', '.join(r['fired_new']) or '—'}",
                    f"**Check-6 patterns:** {', '.join(r['patterns_new']) or '—'}",
                    f"**Check-6 raw score:** {r['c6_score_new']}",
                    f"**Assessment:** {r['assessment']}",
                    "",
                    "```python",
                    r["code"][:800] + ("..." if len(r["code"]) > 800 else ""),
                    "```",
                    "",
                ]

        # Regressions: new that were clean under old
        new_only = [r for r in ds["flagged_new"] if r["verdict_old"] == "CLEAN"]
        lines += [
            f"### Threshold Regression: flagged by NEW but not OLD — {len(new_only)} records",
            "",
        ]
        if not new_only:
            lines.append("*No regressions — threshold change introduced 0 new FPs.*")
            lines.append("")
        else:
            for r in new_only:
                lines += [
                    f"- `{r['id']}` — {', '.join(r['fired_new'])} — {r['assessment']}",
                ]
            lines.append("")

    report_path = output_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[report] Wrote {report_path}")

    # Also write per_item JSON
    all_items = {ds["name"]: ds["per_item"] for ds in datasets}
    json_path = output_dir / "per_item.json"
    json_path.write_text(json.dumps(all_items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[report] Wrote {json_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MBPP standalone precision stress test")
    parser.add_argument("--humaneval", action="store_true",
                        help="Also scan HumanEval canonical solutions")
    args = parser.parse_args()

    commit = _git_commit()
    print(f"[mbpp_precision] ast-guard commit: {commit}")

    datasets: list[dict] = []

    # MBPP
    if not _MBPP_CACHE.exists():
        print(f"ERROR: MBPP cache not found at {_MBPP_CACHE}. "
              "Run: python -m benchmarks.run_benchmark --benchmark mbpp --download")
        sys.exit(1)
    mbpp_rows = json.loads(_MBPP_CACHE.read_text(encoding="utf-8"))
    mbpp_rows = [r for r in mbpp_rows if r.get("code", "").strip()]
    datasets.append(run_dataset("MBPP", mbpp_rows, "code"))

    # HumanEval (optional)
    if args.humaneval:
        if not _HE_CACHE.exists():
            print(f"WARNING: HumanEval cache not found at {_HE_CACHE}. Skipping.")
        else:
            he_rows = json.loads(_HE_CACHE.read_text(encoding="utf-8"))
            # HumanEval stores prompt + canonical_solution; concat them as the "code"
            for r in he_rows:
                r["full_code"] = (r.get("prompt", "") + r.get("canonical_solution", "")).strip()
            he_rows = [r for r in he_rows if r.get("full_code", "").strip()]
            datasets.append(run_dataset("HumanEval", he_rows, "full_code"))

    _write_report(datasets, commit, _OUTPUT_DIR)
    print("\n[done]")


if __name__ == "__main__":
    main()
