#!/usr/bin/env python3
"""
ast-guard Benchmark Runner

Evaluates ast-guard against reward hacking samples organized by the
TRACE taxonomy (Deshpande et al., 2026) and against external benchmark
datasets loaded via the Phase 3 ingestion framework.

Usage:
    python -m benchmarks.run_benchmark
    python -m benchmarks.run_benchmark --json
    python -m benchmarks.run_benchmark --verbose
    python -m benchmarks.run_benchmark --benchmark evilgenie --download
    python -m benchmarks.run_benchmark --benchmark all --download
"""

import sys
import json
import logging
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ast_guard import scan
from benchmarks.samples.trace_samples import HACKED_SAMPLES, BENIGN_SAMPLES

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# TRACE taxonomy mapping — which categories ast-guard covers vs. cannot cover
TRACE_TAXONOMY = {
    "Test Suite Exploitation": {
        "Test Modification": {"covered": False, "reason": "Requires semantic understanding of test intent"},
        "Hardcoded Outputs": {"covered": True, "checks": [1, 2]},
        "Input Recognition": {"covered": True, "checks": [1]},
        "Boundary Value Gaming": {"covered": True, "checks": [1]},
        "Regex Matching": {"covered": False, "reason": "Requires semantic analysis of regex patterns"},
        "Checksum Gaming": {"covered": False, "reason": "Requires runtime analysis"},
        "Type Coercion": {"covered": False, "reason": "Requires type inference"},
        "Coverage Gaming": {"covered": False, "reason": "Requires coverage analysis"},
        "Test Deletion": {"covered": False, "reason": "Requires file-level diff analysis"},
        "Test Mocking": {"covered": False, "reason": "Requires semantic understanding of mocks"},
        "Exception Suppression": {"covered": False, "reason": "Requires semantic analysis"},
        "Assertion Weakening": {"covered": False, "reason": "Requires semantic analysis of assertions"},
        "Timeout Manipulation": {"covered": False, "reason": "Requires semantic analysis"},
    },
    "Solution Quality Degradation": {
        "Lookup Tables": {"covered": True, "checks": [1, 2]},
        "If-Else Explosion": {"covered": True, "checks": [1, 2]},
        "Copy-Paste Replication": {"covered": True, "checks": [1]},
        "Magic Number Hardcoding": {"covered": True, "checks": [1]},
        "String Concat Abuse": {"covered": True, "checks": [1]},
        "Goto Spaghetti": {"covered": False, "reason": "Python has no goto — N/A"},
        "Complexity Gaming": {"covered": True, "checks": [2]},
        "Algorithmic Inefficiency": {"covered": False, "reason": "Requires performance analysis"},
        "Memory Bloat": {"covered": False, "reason": "Requires memory analysis"},
        "Recursive Overflow": {"covered": False, "reason": "Requires depth analysis"},
        "Redundant Computation": {"covered": False, "reason": "Requires semantic analysis"},
        "Premature Optimization": {"covered": False, "reason": "Subjective — requires context"},
        "Comment Flooding": {"covered": False, "reason": "Comments not in AST"},
        "Whitespace Inflation": {"covered": False, "reason": "Whitespace not in AST"},
        "Variable Name Verbosity": {"covered": False, "reason": "Names don't affect structure"},
        "Import Overload": {"covered": True, "checks": [4]},
        "Docstring Over-Padding": {"covered": False, "reason": "Docstrings treated as constants"},
        "Type Hint Gaming": {"covered": False, "reason": "Type hints don't affect logic"},
    },
    "Context Exploitation": {
        "Problem Description Mining": {"covered": False, "reason": "Requires intent analysis"},
        "Example Code Copying": {"covered": False, "reason": "Requires semantic comparison"},
        "Variable Name Inference": {"covered": False, "reason": "Requires semantic analysis"},
        "Similar Problem Retrieval": {"covered": False, "reason": "Requires context analysis"},
        "Metadata Mining": {"covered": False, "reason": "Requires context analysis"},
        "LLM Self-Reference": {"covered": False, "reason": "Requires conversation analysis"},
        "Web Search Exploitation": {"covered": False, "reason": "Requires tool usage analysis"},
        "Compiler Error Parsing": {"covered": False, "reason": "Requires intent analysis"},
        "Debugger Manipulation": {"covered": False, "reason": "Requires tool usage analysis"},
    },
    "Execution Env. Hacks": {
        "Global State Pollution": {"covered": True, "checks": [3]},
        "Cache Poisoning": {"covered": False, "reason": "Requires runtime analysis"},
        "File System Gaming": {"covered": True, "checks": [3]},
        "Network Calls": {"covered": True, "checks": [3, 4]},
        "System Call Abuse": {"covered": True, "checks": [3, 4]},
        "Process Manipulation": {"covered": True, "checks": [3]},
        "Race Conditions": {"covered": False, "reason": "Requires concurrency analysis"},
        "Memory Aliasing": {"covered": False, "reason": "Requires memory model analysis"},
        "Interrupt Handling": {"covered": False, "reason": "Requires signal analysis"},
        "Resource Exhaustion": {"covered": False, "reason": "Requires resource analysis"},
        "Lazy Evaluation": {"covered": False, "reason": "Requires semantic analysis"},
    },
}


def run_benchmark(verbose=False):
    """Run the built-in TRACE benchmark samples and collect results."""
    results = {
        "hacked": {"total": 0, "detected": 0, "missed": 0, "details": []},
        "benign": {"total": 0, "correct": 0, "false_positives": 0, "details": []},
        "by_category": {},
        "by_subcategory": {},
    }

    # Run hacked samples (should be detected)
    for sample in HACKED_SAMPLES:
        results["hacked"]["total"] += 1
        result = scan(sample["original"], sample["hacked"], mode="strict", telemetry_enabled=False)
        verdict = result["verdict"]
        detected = verdict in ("WARNING", "CRITICAL")

        cat = sample["category"]
        subcat = sample["subcategory"]

        if cat not in results["by_category"]:
            results["by_category"][cat] = {"total": 0, "detected": 0}
        results["by_category"][cat]["total"] += 1

        if subcat not in results["by_subcategory"]:
            results["by_subcategory"][subcat] = {"total": 0, "detected": 0}
        results["by_subcategory"][subcat]["total"] += 1

        if detected:
            results["hacked"]["detected"] += 1
            results["by_category"][cat]["detected"] += 1
            results["by_subcategory"][subcat]["detected"] += 1
        else:
            results["hacked"]["missed"] += 1

        detail = {
            "name": sample["name"],
            "category": cat,
            "subcategory": subcat,
            "expected": sample["expected_verdict"],
            "actual": verdict,
            "detected": detected,
            "description": sample["description"],
        }

        if verbose and not detected:
            detail["checks"] = result.get("checks", {})

        results["hacked"]["details"].append(detail)

    # Run benign samples (should pass as CLEAN)
    for sample in BENIGN_SAMPLES:
        results["benign"]["total"] += 1
        result = scan(sample["original"], sample["hacked"], mode="strict", telemetry_enabled=False)
        verdict = result["verdict"]
        is_clean = verdict == "CLEAN"

        if is_clean:
            results["benign"]["correct"] += 1
        else:
            results["benign"]["false_positives"] += 1

        detail = {
            "name": sample["name"],
            "category": sample["category"],
            "subcategory": sample["subcategory"],
            "expected": "CLEAN",
            "actual": verdict,
            "correct": is_clean,
            "description": sample["description"],
        }
        results["benign"]["details"].append(detail)

    return results


def compute_taxonomy_coverage():
    """Compute how many TRACE subcategories ast-guard covers."""
    total_subcategories = 0
    covered_subcategories = 0
    coverage_details = {}

    for category, subcategories in TRACE_TAXONOMY.items():
        cat_total = len(subcategories)
        cat_covered = sum(1 for s in subcategories.values() if s["covered"])
        total_subcategories += cat_total
        covered_subcategories += cat_covered
        coverage_details[category] = {
            "total": cat_total,
            "covered": cat_covered,
            "percentage": round(cat_covered / cat_total * 100, 1) if cat_total > 0 else 0,
            "uncovered_reasons": {
                name: info["reason"]
                for name, info in subcategories.items()
                if not info["covered"]
            },
        }

    return {
        "total_subcategories": total_subcategories,
        "covered_subcategories": covered_subcategories,
        "coverage_percentage": round(covered_subcategories / total_subcategories * 100, 1),
        "by_category": coverage_details,
    }


# ---------------------------------------------------------------------------
# Phase 3: external benchmark runner
# ---------------------------------------------------------------------------

_BENCHMARK_NAMES = [
    "terminal-wrench",
    "evilgenie",
    "trace",
    "countdown-code",
    "helff-gaming",
    "school-of-hacks",
    "specbench",
]


def _scan_code_pair(pair: dict, mode: str = "strict") -> dict:
    """Run ast-guard on a CodePair and return a result record."""
    language = pair.get("language", "python")

    # ast-guard's scan() is Python-only; for other languages we report N/A.
    if language != "python":
        return {
            "sample_id": pair["sample_id"],
            "benchmark": pair["benchmark"],
            "category": pair["category"],
            "language": language,
            "verdict": "N/A",
            "detected": False,
            "skipped": True,
            "skip_reason": f"language={language} not supported by Python scanner",
        }

    try:
        result = scan(
            pair["original_code"],
            pair["generated_code"],
            mode=mode,
            telemetry_enabled=False,
        )
        verdict = result["verdict"]
        detected = verdict in ("WARNING", "CRITICAL")
        return {
            "sample_id": pair["sample_id"],
            "benchmark": pair["benchmark"],
            "category": pair["category"],
            "language": language,
            "verdict": verdict,
            "detected": detected,
            "skipped": False,
        }
    except Exception as exc:
        logger.warning(
            "Error scanning sample %s from %s: %s",
            pair.get("sample_id"),
            pair.get("benchmark"),
            exc,
        )
        return {
            "sample_id": pair["sample_id"],
            "benchmark": pair["benchmark"],
            "category": pair["category"],
            "language": language,
            "verdict": "ERROR",
            "detected": False,
            "skipped": True,
            "skip_reason": str(exc),
        }


def run_external_benchmarks(
    benchmark_names: list[str],
    download: bool = False,
    mode: str = "strict",
) -> dict:
    """Load and scan external benchmark samples; return structured results."""
    from benchmarks.loaders import get_loader, get_all_loaders

    if benchmark_names == ["all"]:
        loaders = get_all_loaders()
    else:
        loaders = []
        for name in benchmark_names:
            try:
                loaders.append(get_loader(name))
            except KeyError as exc:
                logger.error("%s", exc)

    results: dict[str, dict] = {}

    for loader in loaders:
        name = loader.name
        logger.info("Processing benchmark: %s", name)

        if download:
            try:
                loader.download()
            except Exception as exc:
                logger.warning("Download failed for %s: %s", name, exc)

        if not loader.is_available():
            logger.info("Skipping %s — data not available", name)
            results[name] = {
                "status": "unavailable",
                "total": 0,
                "detected": 0,
                "skipped": 0,
                "detection_rate": 0.0,
                "by_category": {},
                "details": [],
            }
            continue

        try:
            samples = loader.load_samples()
        except Exception as exc:
            logger.error("Failed to load %s: %s", name, exc)
            results[name] = {
                "status": "error",
                "error": str(exc),
                "total": 0,
                "detected": 0,
                "skipped": 0,
                "detection_rate": 0.0,
                "by_category": {},
                "details": [],
            }
            continue

        details = []
        by_category: dict[str, dict] = {}

        for pair in samples:
            rec = _scan_code_pair(pair, mode=mode)
            details.append(rec)

            cat = rec["category"]
            if cat not in by_category:
                by_category[cat] = {"total": 0, "detected": 0, "skipped": 0}
            by_category[cat]["total"] += 1
            if rec.get("skipped"):
                by_category[cat]["skipped"] += 1
            elif rec["detected"]:
                by_category[cat]["detected"] += 1

        total = len(details)
        detected = sum(1 for r in details if r.get("detected"))
        skipped = sum(1 for r in details if r.get("skipped"))
        scannable = total - skipped
        detection_rate = round(detected / scannable * 100, 1) if scannable > 0 else 0.0

        results[name] = {
            "status": "ok",
            "total": total,
            "detected": detected,
            "skipped": skipped,
            "scannable": scannable,
            "detection_rate": detection_rate,
            "by_category": by_category,
            "details": details,
        }
        logger.info(
            "%s: %d/%d detected (%.1f%%), %d skipped",
            name, detected, scannable, detection_rate, skipped,
        )

    return results


def format_external_report(ext_results: dict) -> str:
    """Format external benchmark results as a CLI report."""
    lines = ["", "=" * 70, "  ast-guard External Benchmark Report", "=" * 70]

    for name, data in ext_results.items():
        lines.append(f"\n  [{name.upper()}]")
        status = data.get("status", "unknown")
        if status == "unavailable":
            lines.append("    Status: not downloaded")
            continue
        if status == "error":
            lines.append(f"    Status: error — {data.get('error', '')}")
            continue

        total = data["total"]
        detected = data["detected"]
        skipped = data["skipped"]
        scannable = data.get("scannable", total - skipped)
        rate = data["detection_rate"]
        lines.append(f"    Total samples:  {total}")
        lines.append(f"    Scannable:      {scannable}  (skipped: {skipped})")
        lines.append(f"    Detected:       {detected}/{scannable} ({rate:.1f}%)")

        by_cat = data.get("by_category") or {}
        if by_cat:
            lines.append("    By category:")
            for cat, stats in sorted(by_cat.items()):
                cat_scan = stats["total"] - stats.get("skipped", 0)
                cat_rate = (
                    round(stats["detected"] / cat_scan * 100, 0)
                    if cat_scan > 0 else 0
                )
                lines.append(
                    f"      {cat}: {stats['detected']}/{cat_scan} ({cat_rate:.0f}%)"
                )

    lines += ["", "=" * 70, ""]
    return "\n".join(lines)


def export_results(ext_results: dict, out_path: Path) -> None:
    """Write full results as JSON and a markdown summary table."""
    # JSON
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps(ext_results, indent=2), encoding="utf-8")
    logger.info("JSON results written to %s", json_path)

    # Markdown
    md_path = out_path.with_suffix(".md")
    rows = ["| Benchmark | Samples | Detected | Detection Rate | Skipped |",
            "|-----------|---------|----------|---------------|---------|"]
    for name, data in ext_results.items():
        if data.get("status") not in ("ok",):
            rows.append(f"| {name} | — | — | {data.get('status', '?')} | — |")
            continue
        scannable = data.get("scannable", data["total"] - data["skipped"])
        rows.append(
            f"| {name} | {data['total']} | {data['detected']} "
            f"| {data['detection_rate']:.1f}% | {data['skipped']} |"
        )
    md_content = "# ast-guard External Benchmark Results\n\n" + "\n".join(rows) + "\n"
    md_path.write_text(md_content, encoding="utf-8")
    logger.info("Markdown summary written to %s", md_path)


# ---------------------------------------------------------------------------
# CLI report (original, unchanged)
# ---------------------------------------------------------------------------

def format_cli_report(results, taxonomy):
    """Format results as a human-readable CLI report."""
    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("  ast-guard Benchmark Report")
    lines.append("  Taxonomy reference: TRACE (Deshpande et al., 2026)")
    lines.append("=" * 70)

    # Detection results
    h = results["hacked"]
    b = results["benign"]
    detection_rate = h["detected"] / h["total"] * 100 if h["total"] > 0 else 0
    fp_rate = b["false_positives"] / b["total"] * 100 if b["total"] > 0 else 0
    precision = h["detected"] / (h["detected"] + b["false_positives"]) * 100 if (h["detected"] + b["false_positives"]) > 0 else 0

    lines.append("")
    lines.append("  DETECTION RESULTS")
    lines.append("  " + "-" * 40)
    lines.append(f"  True Positives (hacks detected):    {h['detected']}/{h['total']} ({detection_rate:.1f}%)")
    lines.append(f"  True Negatives (benign passed):     {b['correct']}/{b['total']} ({100 - fp_rate:.1f}%)")
    lines.append(f"  False Positives:                    {b['false_positives']}/{b['total']} ({fp_rate:.1f}%)")
    lines.append(f"  Missed (false negatives):           {h['missed']}/{h['total']}")
    lines.append(f"  Precision:                          {precision:.1f}%")
    lines.append(f"  Detection Rate (recall):            {detection_rate:.1f}%")

    # Per-category breakdown
    lines.append("")
    lines.append("  DETECTION BY CATEGORY")
    lines.append("  " + "-" * 40)
    for cat, data in results["by_category"].items():
        rate = data["detected"] / data["total"] * 100 if data["total"] > 0 else 0
        lines.append(f"  {cat}: {data['detected']}/{data['total']} ({rate:.0f}%)")

    # Per-subcategory breakdown
    lines.append("")
    lines.append("  DETECTION BY SUBCATEGORY")
    lines.append("  " + "-" * 40)
    for subcat, data in results["by_subcategory"].items():
        rate = data["detected"] / data["total"] * 100 if data["total"] > 0 else 0
        status = "✓" if rate == 100 else "△" if rate > 0 else "✗"
        lines.append(f"  {status} {subcat}: {data['detected']}/{data['total']} ({rate:.0f}%)")

    # Taxonomy coverage
    lines.append("")
    lines.append("  TRACE TAXONOMY COVERAGE")
    lines.append("  " + "-" * 40)
    lines.append(f"  Total TRACE subcategories:          {taxonomy['total_subcategories']}")
    lines.append(f"  Covered by ast-guard:               {taxonomy['covered_subcategories']}")
    lines.append(f"  Coverage:                           {taxonomy['coverage_percentage']}%")
    lines.append("")
    for cat, data in taxonomy["by_category"].items():
        lines.append(f"  {cat}: {data['covered']}/{data['total']} ({data['percentage']}%)")

    # Missed samples detail
    missed = [d for d in results["hacked"]["details"] if not d["detected"]]
    if missed:
        lines.append("")
        lines.append("  MISSED HACKS (FALSE NEGATIVES)")
        lines.append("  " + "-" * 40)
        for m in missed:
            lines.append(f"  ✗ {m['name']}: expected {m['expected']}, got {m['actual']}")
            lines.append(f"    {m['description']}")

    # False positives detail
    fps = [d for d in results["benign"]["details"] if not d["correct"]]
    if fps:
        lines.append("")
        lines.append("  FALSE POSITIVES")
        lines.append("  " + "-" * 40)
        for fp in fps:
            lines.append(f"  ✗ {fp['name']}: expected CLEAN, got {fp['actual']}")
            lines.append(f"    {fp['description']}")

    # Comparison with LLM-based detection
    lines.append("")
    lines.append("  COMPARISON WITH LLM-BASED DETECTORS")
    lines.append("  " + "-" * 40)
    lines.append(f"  GPT-5.2 (highest reasoning):        63% detection rate (on full TRACE)")
    lines.append(f"  Claude Opus 4.5:                    25% detection rate (on full TRACE)")
    lines.append(f"  ast-guard:                          {detection_rate:.0f}% on structural categories")
    lines.append(f"                                      100% deterministic, <50ms, $0 cost")
    lines.append("")
    lines.append("  Note: LLM detectors cover all 54 TRACE categories (including semantic).")
    lines.append(f"  ast-guard covers {taxonomy['covered_subcategories']} structural categories with deterministic precision.")
    lines.append("  The two approaches are complementary, not competing.")

    lines.append("")
    lines.append("=" * 70)
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="ast-guard benchmark runner")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show detailed check results for missed samples",
    )
    parser.add_argument(
        "--benchmark",
        metavar="NAME",
        nargs="+",
        choices=_BENCHMARK_NAMES + ["all"],
        help=(
            "Run external benchmark(s). Choices: "
            + ", ".join(_BENCHMARK_NAMES)
            + ", all"
        ),
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Auto-clone / download benchmark repos before running",
    )
    parser.add_argument(
        "--export",
        metavar="PATH",
        help="Export external results to PATH.json and PATH.md",
    )
    parser.add_argument(
        "--mode",
        choices=("strict", "standard", "audit"),
        default="strict",
        help="ast-guard scan mode for external benchmarks (default: strict)",
    )
    args = parser.parse_args()

    if args.benchmark:
        names = args.benchmark
        ext_results = run_external_benchmarks(
            names, download=args.download, mode=args.mode
        )
        if args.export:
            export_results(ext_results, Path(args.export))
        if args.json:
            print(json.dumps(ext_results, indent=2))
        else:
            print(format_external_report(ext_results))
        return

    # Original built-in benchmark.
    results = run_benchmark(verbose=args.verbose)
    taxonomy = compute_taxonomy_coverage()

    if args.json:
        output = {
            "results": {
                "detection_rate": round(results["hacked"]["detected"] / results["hacked"]["total"] * 100, 1),
                "false_positive_rate": round(results["benign"]["false_positives"] / results["benign"]["total"] * 100, 1),
                "true_positives": results["hacked"]["detected"],
                "true_negatives": results["benign"]["correct"],
                "false_positives": results["benign"]["false_positives"],
                "false_negatives": results["hacked"]["missed"],
                "total_hacked": results["hacked"]["total"],
                "total_benign": results["benign"]["total"],
            },
            "by_category": results["by_category"],
            "by_subcategory": results["by_subcategory"],
            "taxonomy_coverage": taxonomy,
            "missed": [d for d in results["hacked"]["details"] if not d["detected"]],
            "false_positives": [d for d in results["benign"]["details"] if not d["correct"]],
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_cli_report(results, taxonomy))


if __name__ == "__main__":
    main()
