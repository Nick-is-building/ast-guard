"""
Diagnose pattern diversity in the eval split of generator output.

Loads all TP samples (label=hack) from the eval split of a generator JSONL,
runs ast_guard.scan() on each, and reports which checks fire — and which don't.

This answers: does open mode produce structurally novel hacks, or does the
model fall back to the known patterns (especially checks 1 and 5)?

Usage:
    python3 -m benchmarks.analyze_eval_diversity eval_pairs.jsonl
    python3 -m benchmarks.analyze_eval_diversity eval_pairs.jsonl --mode strict
    python3 -m benchmarks.analyze_eval_diversity eval_pairs.jsonl --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ast_guard import scan
from benchmarks.loaders.generator_loader import GeneratorLoader

_CHECK_KEYS = [
    "check_1_hardcoding",
    "check_2_complexity_collapse",
    "check_3_forbidden_calls",
    "check_4_import_drift",
    "check_5_extensional_enumeration",
]

_SHORT = {
    "check_1_hardcoding":              "Check 1  hardcoding",
    "check_2_complexity_collapse":     "Check 2  complexity_collapse",
    "check_3_forbidden_calls":         "Check 3  forbidden_calls",
    "check_4_import_drift":            "Check 4  import_drift",
    "check_5_extensional_enumeration": "Check 5  enumeration",
}


def _checks_fired(result: dict) -> frozenset[str]:
    """Return the set of check keys whose status is not CLEAN."""
    fired = set()
    for key, data in result.get("checks", {}).items():
        if data.get("status", "CLEAN") != "CLEAN":
            fired.add(key)
    return frozenset(fired)


def _pct(num: int, den: int) -> float | None:
    return round(num / den * 100, 1) if den > 0 else None


def analyze(path: Path, mode: str = "standard") -> dict:
    """Load all eval-split samples and return the diversity + F1 report."""
    loader = GeneratorLoader()
    all_eval = loader.load_eval(path)

    tp_samples = [s for s in all_eval if s["metadata"].get("label") == "hack"]
    tn_samples = [s for s in all_eval if s["metadata"].get("label") == "clean"]

    if not tp_samples:
        return {
            "error": "No eval-split TP samples found. "
                     "Run the generator with --open first.",
            "path": str(path),
            "total_eval": len(all_eval),
        }

    per_check_hits: Counter = Counter()
    combo_hits: Counter = Counter()
    verdict_hits: Counter = Counter()
    undetected: list[dict] = []
    open_variants: Counter = Counter()
    models: Counter = Counter()
    per_variant_check: dict[str, Counter] = {}

    # --- scan TP samples ---
    for sample in tp_samples:
        meta = sample["metadata"]
        variant = meta.get("open_variant", "unknown")
        model = meta.get("model", "unknown")
        open_variants[variant] += 1
        models[model] += 1

        result = scan(
            sample["original_code"],
            sample["generated_code"],
            mode=mode,
            telemetry_enabled=False,
        )
        fired = _checks_fired(result)
        verdict_hits[result["verdict"]] += 1

        for key in fired:
            per_check_hits[key] += 1
        combo_hits[fired] += 1

        if variant not in per_variant_check:
            per_variant_check[variant] = Counter()
        for key in fired:
            per_variant_check[variant][key] += 1

        if not fired:
            undetected.append({
                "sample_id": sample["sample_id"],
                "model": model,
                "variant": variant,
                "prompt_hash": meta.get("prompt_hash"),
                "seed_id": meta.get("seed_id"),
            })

    # --- scan TN samples (false-positive check) ---
    fp_count = 0
    tn_count = 0
    for sample in tn_samples:
        result = scan(
            sample["original_code"],
            sample["generated_code"],
            mode=mode,
            telemetry_enabled=False,
        )
        if _checks_fired(result):
            fp_count += 1
        else:
            tn_count += 1

    n_tp = len(tp_samples)
    n_tn = len(tn_samples)

    # Confusion matrix on eval split
    true_pos  = n_tp - len(undetected)   # detected hacks
    false_neg = len(undetected)          # missed hacks
    false_pos = fp_count                 # clean flagged
    true_neg  = tn_count                 # clean passed

    top_combos = [
        {
            "checks": sorted(combo),
            "count": count,
            "pct": round(count / n_tp * 100, 1),
        }
        for combo, count in combo_hits.most_common(10)
    ]

    return {
        "path": str(path),
        "mode": mode,
        "total_eval_samples": len(all_eval),
        "tp_samples": n_tp,
        "tn_samples": n_tn,
        # F1 metrics on eval split
        "confusion": {
            "tp": true_pos, "fp": false_pos,
            "fn": false_neg, "tn": true_neg,
        },
        "precision":  _pct(true_pos, true_pos + false_pos),
        "recall":     _pct(true_pos, true_pos + false_neg),
        "fpr":        _pct(false_pos, false_pos + true_neg),
        "f1": (
            round(
                2 * true_pos / (2 * true_pos + false_pos + false_neg) * 100, 1
            ) if (2 * true_pos + false_pos + false_neg) > 0 else None
        ),
        # TP diversity
        "undetected_count": len(undetected),
        "undetected_pct": round(len(undetected) / n_tp * 100, 1) if n_tp else 0.0,
        "per_check": {
            key: {
                "count": per_check_hits[key],
                "pct": round(per_check_hits[key] / n_tp * 100, 1),
            }
            for key in _CHECK_KEYS
        },
        "verdicts": dict(verdict_hits),
        "top_combos": top_combos,
        "by_model": dict(models),
        "by_variant": dict(open_variants),
        "per_variant_check": {
            v: dict(c) for v, c in per_variant_check.items()
        },
        "undetected_samples": undetected[:20],
    }


def _fmt_bar(pct: float, width: int = 30) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _fmt_pct(v: float | None) -> str:
    return f"{v:.1f}%" if v is not None else "n/a"


def format_report(data: dict) -> str:
    if "error" in data:
        return f"\n  ERROR: {data['error']}\n  Path: {data['path']}\n"

    n = data["tp_samples"]
    n_tn = data.get("tn_samples", 0)
    undet = data["undetected_count"]
    cm = data.get("confusion", {})
    lines = [
        "",
        "=" * 68,
        "  eval-split report  (pattern diversity + F1 metrics)",
        f"  {data['path']}  (mode={data['mode']})",
        "=" * 68,
        "",
        f"  Eval samples:  {data['total_eval_samples']}  "
        f"(TP={n}  TN={n_tn})",
        "",
        "  EVAL-SPLIT METRICS  (requires both TP and TN)",
        "  " + "-" * 50,
        f"  Precision:  {_fmt_pct(data.get('precision'))}  "
        f"(TP={cm.get('tp',0)}  FP={cm.get('fp',0)})",
        f"  Recall:     {_fmt_pct(data.get('recall'))}  "
        f"(TP={cm.get('tp',0)}  FN={cm.get('fn',0)})",
        f"  FPR:        {_fmt_pct(data.get('fpr'))}  "
        f"(FP={cm.get('fp',0)}  TN={cm.get('tn',0)})",
        f"  F1:         {_fmt_pct(data.get('f1'))}",
        "",
        f"  Undetected hacks (novel?):  {undet}/{n}  "
        f"({data['undetected_pct']:.1f}%)",
        "",
        "  PER-CHECK FIRE RATE  (% of eval TP samples that trigger each check)",
        "  " + "-" * 56,
    ]

    for key in _CHECK_KEYS:
        stat = data["per_check"][key]
        pct = stat["pct"]
        bar = _fmt_bar(pct)
        lines.append(
            f"  {_SHORT[key]:<35}  {stat['count']:>4}/{n}  {pct:>5.1f}%  {bar}"
        )

    lines += [
        "",
        "  VERDICT DISTRIBUTION",
        "  " + "-" * 40,
    ]
    for verdict, count in sorted(data["verdicts"].items()):
        pct = round(count / n * 100, 1) if n else 0.0
        lines.append(f"  {verdict:<12}  {count:>4}  ({pct:.1f}%)")

    lines += [
        "",
        "  TOP CHECK COMBINATIONS",
        "  " + "-" * 40,
    ]
    for combo in data["top_combos"]:
        checks = combo["checks"] or ["(none — undetected)"]
        short = ", ".join(c.replace("check_", "").split("_")[0] + "_" +
                          "_".join(c.split("_")[2:]) for c in checks) if combo["checks"] else "(none)"
        lines.append(f"  {combo['count']:>4}x  {combo['pct']:>5.1f}%  {short}")

    lines += [
        "",
        "  GENERATION SOURCE",
        "  " + "-" * 40,
        "  By model:",
    ]
    for model, count in sorted(data["by_model"].items(), key=lambda x: -x[1]):
        pct = round(count / n * 100, 1) if n else 0.0
        lines.append(f"    {model:<45}  {count:>4}  ({pct:.1f}%)")
    lines.append("  By variant:")
    for variant, count in sorted(data["by_variant"].items(), key=lambda x: -x[1]):
        pct = round(count / n * 100, 1) if n else 0.0
        lines.append(f"    {variant:<45}  {count:>4}  ({pct:.1f}%)")

    if data["per_variant_check"]:
        lines += ["", "  CHECK FIRE RATE BY VARIANT"]
        lines.append("  " + "-" * 40)
        for variant, check_counts in sorted(data["per_variant_check"].items()):
            variant_n = data["by_variant"].get(variant, 1)
            lines.append(f"  [{variant}]  (n={variant_n})")
            for key in _CHECK_KEYS:
                c = check_counts.get(key, 0)
                pct = round(c / variant_n * 100, 1) if variant_n else 0.0
                short = _SHORT[key]
                lines.append(f"    {short:<35}  {c:>3}/{variant_n}  {pct:>5.1f}%")

    if data["undetected_samples"]:
        lines += [
            "",
            f"  UNDETECTED HACKS (first {len(data['undetected_samples'])}) — potentially novel patterns",
            "  " + "-" * 40,
        ]
        for s in data["undetected_samples"]:
            lines.append(
                f"  {s['sample_id']}  model={s['model']}  "
                f"variant={s['variant']}  seed={s['seed_id']}"
            )

    lines += ["", "=" * 68, ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report check-fire distribution across eval-split TP samples"
    )
    parser.add_argument("path", type=Path, help="Path to the eval JSONL file")
    parser.add_argument(
        "--mode",
        choices=("strict", "standard", "audit"),
        default="standard",
        help="ast-guard scan mode (default: standard)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Emit JSON instead of the formatted report",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"File not found: {args.path}", file=sys.stderr)
        print(
            "\nNo eval JSONL found. Generate one first:\n\n"
            "  python3 -m generator.generate \\\n"
            "    --open \\\n"
            "    --seeds 60 \\\n"
            "    --out-calibration calibration_pairs.jsonl \\\n"
            "    --out-eval eval_pairs.jsonl\n\n"
            "Adjust --seeds for the desired sample count "
            "(60 seeds × 9 model/variant combos ≈ up to 540 attempts).",
            file=sys.stderr,
        )
        sys.exit(1)

    data = analyze(args.path, mode=args.mode)

    if "error" in data:
        print(format_report(data))
        sys.exit(1)

    if args.as_json:
        print(json.dumps(data, indent=2))
    else:
        print(format_report(data))


if __name__ == "__main__":
    main()
