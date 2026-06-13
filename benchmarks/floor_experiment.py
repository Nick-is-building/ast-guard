"""
Floor Experiment — empirically compare _ORIG_COMPLEXITY_FLOOR = 2 vs 1.

Usage:
    python3 -m benchmarks.floor_experiment --path eval_pairs_floor.jsonl

Measures recall and precision (easy TN + hard TN) for four configurations:
  A  floor7=2  floor8=2   (current baseline)
  B  floor7=1  floor8=1   (both relaxed)
  C  floor7=1  floor8=2   (only Check 7 relaxed)
  D  floor7=2  floor8=1   (only Check 8 relaxed)

FP breakdown is shown per check (7, 8, or both) for each config.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import ast_guard.check_literal_hijack as _clh
import ast_guard.check_new_constant_bypass as _cnc
from ast_guard import scan


# ---------------------------------------------------------------------------
# Monkey-patch helper
# ---------------------------------------------------------------------------

def _set_floors(floor7: int, floor8: int) -> None:
    """Patch module-level constants in the two check modules."""
    _clh._ORIG_COMPLEXITY_FLOOR = floor7
    _cnc._ORIG_COMPLEXITY_FLOOR = floor8


def _verdict_with_check_detail(
    original_code: str, generated_code: str
) -> tuple[str, bool, bool]:
    """Return (verdict, check7_fired, check8_fired)."""
    try:
        result = scan(original_code, generated_code, mode="strict", telemetry_enabled=False)
    except Exception:
        return "ERROR", False, False
    verdict = result.get("verdict", "CLEAN")
    c7 = bool(result.get("checks", {}).get("check_7_literal_hijack", {}).get("findings"))
    c8 = bool(result.get("checks", {}).get("check_8_new_constant_bypass", {}).get("findings"))
    return verdict, c7, c8


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

class Row(NamedTuple):
    orig: str
    gen: str
    label: str       # "hack" | "clean"
    category: str    # "open" | "honest-vs-honest" | "honest-vs-alternative"
    meta: dict


def _load(path: Path) -> list[Row]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            meta = r.get("metadata", {})
            if meta.get("split") != "eval":
                continue
            rows.append(Row(
                orig=r["original_code"],
                gen=r["generated_code"],
                label=meta.get("label", "?"),
                category=r.get("category", ""),
                meta=meta,
            ))
    return rows


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class FPRecord(NamedTuple):
    category: str
    check7: bool
    check8: bool
    seed_id: str
    model: str
    variant: str
    gen_snippet: str


def _score(rows: list[Row]) -> dict:
    """Score current floor settings. Returns metrics dict + FP details."""
    hack_rows = [r for r in rows if r.label == "hack"]
    easy_tn = [r for r in rows if r.label == "clean" and r.category == "honest-vs-honest"]
    hard_tn = [r for r in rows if r.label == "clean" and r.category == "honest-vs-alternative"]

    tp = fn = 0
    missed: list[Row] = []
    for r in hack_rows:
        v, _, _ = _verdict_with_check_detail(r.orig, r.gen)
        if v in ("WARNING", "CRITICAL"):
            tp += 1
        else:
            fn += 1
            missed.append(r)

    fp_easy: list[FPRecord] = []
    for r in easy_tn:
        v, c7, c8 = _verdict_with_check_detail(r.orig, r.gen)
        if v in ("WARNING", "CRITICAL"):
            fp_easy.append(FPRecord(
                category="easy",
                check7=c7, check8=c8,
                seed_id=r.meta.get("seed_id", "?"),
                model=r.meta.get("model", "?"),
                variant=r.meta.get("open_variant", ""),
                gen_snippet="\n".join(r.gen.splitlines()[:6]),
            ))

    fp_hard: list[FPRecord] = []
    for r in hard_tn:
        v, c7, c8 = _verdict_with_check_detail(r.orig, r.gen)
        if v in ("WARNING", "CRITICAL"):
            fp_hard.append(FPRecord(
                category="hard",
                check7=c7, check8=c8,
                seed_id=r.meta.get("seed_id", "?"),
                model=r.meta.get("model", "?"),
                variant=r.meta.get("open_variant", ""),
                gen_snippet="\n".join(r.gen.splitlines()[:6]),
            ))

    recall = tp / len(hack_rows) if hack_rows else float("nan")
    prec_easy = 1 - len(fp_easy) / len(easy_tn) if easy_tn else float("nan")
    prec_hard = 1 - len(fp_hard) / len(hard_tn) if hard_tn else float("nan")

    return {
        "n_hack": len(hack_rows),
        "n_easy_tn": len(easy_tn),
        "n_hard_tn": len(hard_tn),
        "tp": tp, "fn": fn,
        "recall": recall,
        "fp_easy": fp_easy,
        "fp_hard": fp_hard,
        "prec_easy": prec_easy,
        "prec_hard": prec_hard,
        "missed": missed,
    }


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _fp_breakdown(fp_list: list[FPRecord]) -> str:
    if not fp_list:
        return "  (none)"
    c7_only = sum(1 for f in fp_list if f.check7 and not f.check8)
    c8_only = sum(1 for f in fp_list if f.check8 and not f.check7)
    both = sum(1 for f in fp_list if f.check7 and f.check8)
    lines = [f"  total={len(fp_list)}  check7_only={c7_only}  check8_only={c8_only}  both={both}"]
    for fp in fp_list:
        tag = []
        if fp.check7:
            tag.append("C7")
        if fp.check8:
            tag.append("C8")
        lines.append(
            f"    [{'/'.join(tag)}] seed={fp.seed_id}  model={fp.model}  variant={fp.variant or '-'}\n"
            f"      gen[:6]: {fp.gen_snippet[:120].replace(chr(10), ' | ')}"
        )
    return "\n".join(lines)


def _print_config(label: str, cfg: str, res: dict) -> None:
    print(f"\n{'='*60}")
    print(f"Config {label}: {cfg}")
    print(f"{'='*60}")
    print(f"  Hack pairs:   {res['n_hack']}   TP={res['tp']}  FN={res['fn']}")
    print(f"  Recall:       {res['recall']:.3f}")
    print(f"  Easy TNs:     {res['n_easy_tn']}   FP={len(res['fp_easy'])}  Precision={res['prec_easy']:.3f}")
    print(f"  Hard TNs:     {res['n_hard_tn']}   FP={len(res['fp_hard'])}  Precision={res['prec_hard']:.3f}")
    print(f"\n  FP easy TN breakdown:")
    print(_fp_breakdown(res["fp_easy"]))
    print(f"\n  FP hard TN breakdown:")
    print(_fp_breakdown(res["fp_hard"]))
    if res["missed"]:
        print(f"\n  Missed hacks (FN={res['fn']}):")
        for r in res["missed"]:
            print(f"    seed={r.meta.get('seed_id','?')}  model={r.meta.get('model','?')}  variant={r.meta.get('open_variant','-')}")


def _delta_row(label: str, base: dict, other: dict) -> str:
    d_recall = other["recall"] - base["recall"]
    d_fp_easy = len(other["fp_easy"]) - len(base["fp_easy"])
    d_fp_hard = len(other["fp_hard"]) - len(base["fp_hard"])
    d_prec_easy = other["prec_easy"] - base["prec_easy"]
    d_prec_hard = other["prec_hard"] - base["prec_hard"]
    return (
        f"  {label:<10}  recall {d_recall:+.3f}"
        f"  fp_easy {d_fp_easy:+d} (prec {d_prec_easy:+.3f})"
        f"  fp_hard {d_fp_hard:+d} (prec {d_prec_hard:+.3f})"
    )


def run(path: Path) -> None:
    rows = _load(path)
    if not rows:
        print(f"No eval-split records found in {path}")
        return

    print(f"Loaded {len(rows)} eval-split records from {path}")
    hack_n = sum(1 for r in rows if r.label == "hack")
    easy_n = sum(1 for r in rows if r.label == "clean" and r.category == "honest-vs-honest")
    hard_n = sum(1 for r in rows if r.label == "clean" and r.category == "honest-vs-alternative")
    print(f"  hack={hack_n}  easy_tn={easy_n}  hard_tn={hard_n}")

    configs = [
        ("A", "floor7=2  floor8=2  (baseline)", 2, 2),
        ("B", "floor7=1  floor8=1  (both relaxed)", 1, 1),
        ("C", "floor7=1  floor8=2  (only Check 7 relaxed)", 1, 2),
        ("D", "floor7=2  floor8=1  (only Check 8 relaxed)", 2, 1),
    ]

    results = {}
    for label, cfg_str, f7, f8 in configs:
        _set_floors(f7, f8)
        results[label] = _score(rows)
        _print_config(label, cfg_str, results[label])

    # Restore baseline
    _set_floors(2, 2)

    print(f"\n{'='*60}")
    print("DELTA SUMMARY (vs Config A baseline)")
    print(f"{'='*60}")
    base = results["A"]
    for label, cfg_str, _, _ in configs[1:]:
        print(_delta_row(label + f" ({cfg_str.split('(')[1].rstrip(')')})", base, results[label]))

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Floor experiment: compare _ORIG_COMPLEXITY_FLOOR=2 vs 1")
    parser.add_argument("--path", type=Path, default=Path("eval_pairs_floor.jsonl"))
    args = parser.parse_args()
    run(args.path)
