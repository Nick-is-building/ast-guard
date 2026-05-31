"""
ast-guard Structural Benchmark Runner

Evaluates the 5-check static-analysis pipeline against a curated set of
hand-labelled code pairs. Reports per-sample pass/fail, per-category pass
rate, precision/recall on CLEAN vs. non-CLEAN, and wall-clock timing stats.

Usage:
    python -m benchmarks.structural_benchmark.runner
    python -m benchmarks.structural_benchmark.runner --json
    python -m benchmarks.structural_benchmark.runner --verbose
    python -m benchmarks.structural_benchmark.runner --export results/structural
"""
import sys
import json
import time
import statistics
import argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ast_guard import scan
from benchmarks.structural_benchmark.samples import ALL_SAMPLES, StructuralSample

_SEVERITY_RANK = {"CLEAN": 0, "WARNING": 1, "CRITICAL": 2}


def _at_least(actual: str, expected: str) -> bool:
    """Return True if actual severity is >= expected severity."""
    return _SEVERITY_RANK.get(actual, -1) >= _SEVERITY_RANK.get(expected, 0)


def run_structural_benchmark(mode: str = "strict", verbose: bool = False) -> dict:
    """
    Run all structural benchmark samples through scan() and collect results.

    Returns a dict with keys:
      samples        — per-sample result records
      by_category    — per-category aggregates
      timing         — wall-clock statistics (min/max/mean/median/total ms, samples/s)
      metrics        — precision, recall, F1, exact_match_rate, verdict_pass_rate
    """
    sample_results = []
    timings_ms: list[float] = []

    for sample in ALL_SAMPLES:
        t0 = time.perf_counter()
        result = scan(
            sample.original_code,
            sample.generated_code,
            mode=mode,
            telemetry_enabled=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        timings_ms.append(elapsed_ms)
        actual_verdict = result["verdict"]
        checks = result.get("checks", {})

        # Which checks actually fired (non-CLEAN status)?
        fired_checks = [
            name for name, chk in checks.items() if chk.get("status") != "CLEAN"
        ]

        # Did all expected checks fire?
        expected_fired = all(
            checks.get(ck, {}).get("status") != "CLEAN"
            for ck in sample.expected_checks
        )

        # Pass definitions:
        #   verdict_pass  — actual is at least as severe as expected
        #   exact_pass    — actual matches expected exactly
        verdict_pass = _at_least(actual_verdict, sample.expected_verdict)
        exact_pass = actual_verdict == sample.expected_verdict

        sample_results.append({
            "id": f"{sample.category}/{sample.description[:40].rstrip()}",
            "category": sample.category,
            "expected_verdict": sample.expected_verdict,
            "actual_verdict": actual_verdict,
            "expected_checks": sample.expected_checks,
            "fired_checks": fired_checks,
            "expected_checks_fired": expected_fired,
            "verdict_pass": verdict_pass,
            "exact_pass": exact_pass,
            "elapsed_ms": round(elapsed_ms, 3),
            "description": sample.description,
        })

    # ------------------------------------------------------------------ #
    # Timing statistics
    # ------------------------------------------------------------------ #
    n = len(timings_ms)
    total_ms = sum(timings_ms)
    timing_stats = {
        "n_samples": n,
        "min_ms": round(min(timings_ms), 3),
        "max_ms": round(max(timings_ms), 3),
        "mean_ms": round(statistics.mean(timings_ms), 3),
        "median_ms": round(statistics.median(timings_ms), 3),
        "total_ms": round(total_ms, 3),
        "samples_per_second": round(n / (total_ms / 1000.0), 1) if total_ms > 0 else 0.0,
    }

    # ------------------------------------------------------------------ #
    # Per-category aggregates
    # ------------------------------------------------------------------ #
    by_category: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "verdict_pass": 0, "exact_pass": 0,
        "checks_matched": 0, "timings_ms": [],
    })
    for rec in sample_results:
        cat = rec["category"]
        by_category[cat]["total"] += 1
        if rec["verdict_pass"]:
            by_category[cat]["verdict_pass"] += 1
        if rec["exact_pass"]:
            by_category[cat]["exact_pass"] += 1
        if rec["expected_checks_fired"]:
            by_category[cat]["checks_matched"] += 1
        by_category[cat]["timings_ms"].append(rec["elapsed_ms"])

    # Convert to plain dicts with rates
    cat_summary = {}
    for cat, stats in sorted(by_category.items()):
        t = stats["total"]
        cat_summary[cat] = {
            "total": t,
            "verdict_pass": stats["verdict_pass"],
            "exact_pass": stats["exact_pass"],
            "checks_matched": stats["checks_matched"],
            "verdict_pass_rate": round(stats["verdict_pass"] / t * 100, 1) if t else 0.0,
            "exact_pass_rate": round(stats["exact_pass"] / t * 100, 1) if t else 0.0,
            "mean_ms": round(statistics.mean(stats["timings_ms"]), 3) if stats["timings_ms"] else 0.0,
        }

    # ------------------------------------------------------------------ #
    # Precision / recall (positive = expected non-CLEAN)
    # ------------------------------------------------------------------ #
    tp = sum(1 for r in sample_results
             if r["expected_verdict"] != "CLEAN" and r["actual_verdict"] != "CLEAN")
    fp = sum(1 for r in sample_results
             if r["expected_verdict"] == "CLEAN" and r["actual_verdict"] != "CLEAN")
    fn = sum(1 for r in sample_results
             if r["expected_verdict"] != "CLEAN" and r["actual_verdict"] == "CLEAN")
    tn = sum(1 for r in sample_results
             if r["expected_verdict"] == "CLEAN" and r["actual_verdict"] == "CLEAN")

    precision = round(tp / (tp + fp) * 100, 1) if (tp + fp) > 0 else 0.0
    recall    = round(tp / (tp + fn) * 100, 1) if (tp + fn) > 0 else 0.0
    f1        = round(
        2 * precision * recall / (precision + recall), 1
    ) if (precision + recall) > 0 else 0.0

    total_samples = len(sample_results)
    verdict_pass_total = sum(1 for r in sample_results if r["verdict_pass"])
    exact_pass_total   = sum(1 for r in sample_results if r["exact_pass"])

    overall_metrics = {
        "total_samples": total_samples,
        "verdict_pass": verdict_pass_total,
        "exact_pass": exact_pass_total,
        "verdict_pass_rate": round(verdict_pass_total / total_samples * 100, 1),
        "exact_match_rate": round(exact_pass_total / total_samples * 100, 1),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }

    return {
        "samples": sample_results,
        "by_category": cat_summary,
        "timing": timing_stats,
        "metrics": overall_metrics,
    }


def format_report(data: dict, verbose: bool = False) -> str:
    """Format benchmark results as a human-readable CLI report."""
    m = data["metrics"]
    t = data["timing"]
    lines = [
        "",
        "=" * 70,
        "  ast-guard Structural Benchmark",
        "  First deterministic ground-truth benchmark for structural hack detection",
        "=" * 70,
    ]

    # ── Overall metrics ────────────────────────────────────────────────
    lines += [
        "",
        "  DETECTION METRICS",
        "  " + "-" * 40,
        f"  Samples:               {m['total_samples']}",
        f"  Verdict pass (≥ expected severity):   {m['verdict_pass']}/{m['total_samples']} ({m['verdict_pass_rate']}%)",
        f"  Exact match (== expected):             {m['exact_pass']}/{m['total_samples']} ({m['exact_match_rate']}%)",
        "",
        f"  True Positives  (hack detected):  {m['tp']}",
        f"  True Negatives  (clean passed):   {m['tn']}",
        f"  False Positives (clean flagged):   {m['fp']}",
        f"  False Negatives (hack missed):     {m['fn']}",
        "",
        f"  Precision:   {m['precision']:.1f}%",
        f"  Recall:      {m['recall']:.1f}%",
        f"  F1 Score:    {m['f1']:.1f}%",
    ]

    # ── Timing stats ───────────────────────────────────────────────────
    lines += [
        "",
        "  SCAN TIMING (wall clock)",
        "  " + "-" * 40,
        f"  Min:     {t['min_ms']:.3f} ms",
        f"  Max:     {t['max_ms']:.3f} ms",
        f"  Mean:    {t['mean_ms']:.3f} ms",
        f"  Median:  {t['median_ms']:.3f} ms",
        f"  Total:   {t['total_ms']:.1f} ms  ({t['n_samples']} samples)",
        f"  Throughput: {t['samples_per_second']:.0f} samples/second",
        "",
        "  vs. LLM-based reviewer:  500–2000 ms/call  ($0.01–0.10/scan)",
        f"  ast-guard is ~{int(500 / max(t['mean_ms'], 0.1))}–{int(2000 / max(t['mean_ms'], 0.1))}x faster, $0 marginal cost",
    ]

    # ── Per-category breakdown ─────────────────────────────────────────
    lines += [
        "",
        "  PER-CATEGORY RESULTS",
        "  " + "-" * 60,
        f"  {'Category':<38} {'Pass':>5} {'Total':>5} {'Rate':>6} {'ms/sample':>9}",
        "  " + "-" * 60,
    ]
    for cat, stats in data["by_category"].items():
        short = cat[7:] if cat.startswith("CAT_") else cat  # strip CAT_XX_ prefix
        status = "✓" if stats["verdict_pass_rate"] == 100.0 else ("△" if stats["verdict_pass_rate"] > 0 else "✗")
        lines.append(
            f"  {status} {short:<36} {stats['verdict_pass']:>5} {stats['total']:>5} "
            f" {stats['verdict_pass_rate']:>5.0f}%  {stats['mean_ms']:>7.2f} ms"
        )

    # ── Per-sample detail (always shown, verbose shows check details) ──
    lines += ["", "  SAMPLE RESULTS", "  " + "-" * 70]
    for rec in data["samples"]:
        icon = "✓" if rec["verdict_pass"] else "✗"
        exact_tag = "" if rec["exact_pass"] else f" (exact: {rec['actual_verdict']})"
        lines.append(
            f"  {icon} [{rec['expected_verdict']:<8}] {rec['elapsed_ms']:>6.2f}ms  "
            f"{rec['category'][7:30]:<24} {rec['description'][:45]}"
        )
        if not rec["verdict_pass"] or verbose:
            lines.append(f"       expected checks: {rec['expected_checks']}")
            lines.append(f"       fired checks:    {rec['fired_checks']}")
            if not rec["verdict_pass"]:
                lines.append(
                    f"       FAIL: expected {rec['expected_verdict']}, got {rec['actual_verdict']}"
                )

    lines += ["", "=" * 70, ""]
    return "\n".join(lines)


def export_results(data: dict, out_path: Path) -> None:
    """Write full results as JSON and a markdown summary table."""
    json_path = out_path.with_suffix(".json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    m = data["metrics"]
    t = data["timing"]
    rows = [
        "| Category | Pass | Total | Pass Rate | Mean ms |",
        "|----------|------|-------|-----------|---------|",
    ]
    for cat, stats in data["by_category"].items():
        short = cat[7:] if cat.startswith("CAT_") else cat
        rows.append(
            f"| {short} | {stats['verdict_pass']} | {stats['total']} "
            f"| {stats['verdict_pass_rate']:.0f}% | {stats['mean_ms']:.2f} ms |"
        )

    md = (
        "# ast-guard Structural Benchmark Results\n\n"
        f"**Total:** {m['total_samples']} samples  "
        f"**Verdict-pass:** {m['verdict_pass_rate']}%  "
        f"**Exact-match:** {m['exact_match_rate']}%  "
        f"**Precision:** {m['precision']}%  "
        f"**Recall:** {m['recall']}%  "
        f"**F1:** {m['f1']}%\n\n"
        f"**Timing:** mean {t['mean_ms']:.2f} ms/scan, "
        f"median {t['median_ms']:.2f} ms, "
        f"{t['samples_per_second']:.0f} samples/s\n\n"
        + "\n".join(rows) + "\n"
    )
    md_path = out_path.with_suffix(".md")
    md_path.write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="ast-guard structural benchmark")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show check details for every sample")
    parser.add_argument("--export", metavar="PATH",
                        help="Export results to PATH.json and PATH.md")
    parser.add_argument("--mode", choices=("strict", "standard", "audit"),
                        default="strict")
    args = parser.parse_args()

    data = run_structural_benchmark(mode=args.mode, verbose=args.verbose)

    if args.export:
        export_results(data, Path(args.export))

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(format_report(data, verbose=args.verbose))


if __name__ == "__main__":
    main()
