"""
CLI entry point for the ast-guard eval harness.

Usage:
    python -m eval.run --dataset sorh [--output results/sorh/] [--mode strict]

Outputs:
    <output>/per_item.csv
    <output>/metrics.json
    <output>/report.md

The held_out split is scored but NEVER used to tune thresholds.
Only dev-split records appear in the printed summary.
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.adapters import get_adapter
from eval.metrics import compute_metrics
from eval.record import ScoredRecord
from eval.report import write_report
from eval.scoring import score_record


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent.parent,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _dataset_revision(dataset: str) -> str:
    """Return a short provenance string for the dataset (cache mtime)."""
    from pathlib import Path as P
    # Adapter name "sorh" → stored under "school-of-hacks"
    _NAME_MAP = {"sorh": "school-of-hacks"}
    storage_name = _NAME_MAP.get(dataset, dataset)
    candidates = [
        P.home() / ".ast-guard" / "benchmarks" / storage_name / "syvb_coding.json",
        P.home() / ".ast-guard" / "benchmarks" / storage_name,
        P.home() / ".ast-guard" / "benchmarks" / dataset / "syvb_coding.json",
        P.home() / ".ast-guard" / "benchmarks" / dataset,
    ]
    for p in candidates:
        if p.exists():
            import os
            mtime = os.path.getmtime(p)
            return datetime.datetime.now(datetime.timezone.utc).fromtimestamp(mtime).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
    return "unknown"


def run(
    dataset: str,
    output_dir: str,
    mode: str = "strict",
    dev_ratio: float = 0.8,
    split_seed: int = 42,
    print_examples: int = 3,
) -> None:
    print(f"[eval] Loading adapter: {dataset}")
    adapter = get_adapter(dataset)

    records = adapter.load_with_split(dev_ratio=dev_ratio, seed=split_seed)
    n_dev = sum(1 for r in records if r.split == "dev")
    n_held = sum(1 for r in records if r.split == "held_out")
    print(f"[eval] {len(records)} records — {n_dev} dev / {n_held} held_out")

    # ── score all records ─────────────────────────────────────────────────
    scored: list[ScoredRecord] = []
    n_abstain = 0
    for i, rec in enumerate(records, 1):
        sr = score_record(rec, mode=mode)
        scored.append(sr)
        if sr.standalone_abstain:
            n_abstain += 1
        if i % 20 == 0:
            print(f"[eval]   scored {i}/{len(records)} ...")
    print(f"[eval] Done. Abstain: {n_abstain}/{len(records)} "
          f"({100*n_abstain/len(records):.1f}%)")

    # ── compute metrics ───────────────────────────────────────────────────
    metrics = compute_metrics(scored, split="dev")
    # Pair-mode metrics for records that have an original (TP records only).
    # TN records have identical original/code → pair mode is skipped.
    pair_eligible = [r for r in scored if r.pair_score is not None]
    if pair_eligible:
        metrics["pair_mode"] = compute_metrics(
            pair_eligible, split="dev",
            score_key="pair_score",
            binary_key="pair_binary",
        )

    meta = {
        "ast_guard_commit": _git_commit(),
        "dataset": dataset,
        "dataset_revision": _dataset_revision(dataset),
        "split_seed": split_seed,
        "dev_ratio": dev_ratio,
        "scan_mode": mode,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_total": len(records),
        "n_dev": n_dev,
        "n_held_out": n_held,
    }

    # ── write reports ─────────────────────────────────────────────────────
    write_report(scored, metrics, output_dir, meta)

    # ── print summary ─────────────────────────────────────────────────────
    gm = metrics["global"]
    print()
    print("=" * 60)
    print(f"  dataset : {dataset}  |  split: dev  |  mode: {mode}")
    print("=" * 60)
    print(f"  n       : {gm.get('n_total')}  "
          f"(hack={gm.get('n_hack')}, benign={gm.get('n_benign')}, "
          f"abstain={gm.get('n_abstain')})")
    print(f"  PR-AUC  : {gm.get('pr_auc'):.4f}")
    print(f"  F1      : {gm.get('f1'):.4f}  "
          f"P={gm.get('precision'):.4f}  R={gm.get('recall'):.4f}")
    cm = gm.get("confusion_matrix", {})
    print(f"  CM      : TP={cm.get('tp')} FP={cm.get('fp')} "
          f"TN={cm.get('tn')} FN={cm.get('fn')}")
    print("=" * 60)

    # Pair-mode summary (TP records only)
    pm = metrics.get("pair_mode", {})
    if pm:
        pgm = pm.get("global", {})
        pcm = pgm.get("confusion_matrix", {})
        print(f"  [pair-mode, TP records only]")
        print(f"  n       : {pgm.get('n_total')}  (hack={pgm.get('n_hack')}, "
              f"benign={pgm.get('n_benign')}, abstain={pgm.get('n_abstain')})")
        print(f"  PR-AUC  : {pgm.get('pr_auc', 0):.4f}")
        print(f"  F1      : {pgm.get('f1', 0):.4f}  "
              f"P={pgm.get('precision', 0):.4f}  R={pgm.get('recall', 0):.4f}")
        print(f"  CM      : TP={pcm.get('tp')} FP={pcm.get('fp')} "
              f"TN={pcm.get('tn')} FN={pcm.get('fn')}")
    print("=" * 60)

    # Syntactic / semantic boundary map
    for typ, tm in sorted(metrics.get("by_syntactic_semantic", {}).items()):
        print(f"  [{typ:10}]  n={tm.get('n_total'):3}  "
              f"F1={tm.get('f1', '—')}  AUC={tm.get('pr_auc', '—')}")

    # ── print examples ────────────────────────────────────────────────────
    if print_examples > 0:
        _print_examples(scored, print_examples)


def _print_examples(scored: list[ScoredRecord], n: int = 3) -> None:
    """Print n scored examples: one clear hack, one benign, one abstain."""
    print()
    print("── Scored examples ─────────────────────────────────────────")

    def _first(predicate) -> ScoredRecord | None:
        for r in scored:
            if predicate(r):
                return r
        return None

    # clear hack: high standalone score
    hack_ex = _first(
        lambda r: r.label == "hack" and r.split == "dev"
                  and not r.standalone_abstain and r.standalone_score >= 0.3
    ) or _first(lambda r: r.label == "hack" and r.split == "dev")

    # benign partner: same problem ID as hack, if available
    benign_ex = _first(
        lambda r: r.label == "benign" and r.split == "dev"
                  and not r.standalone_abstain
    )

    # abstain example
    abstain_ex = _first(lambda r: r.standalone_abstain)

    for label, ex in [("HACK", hack_ex), ("BENIGN", benign_ex), ("ABSTAIN", abstain_ex)]:
        if ex is None:
            print(f"\n[{label}] no example found")
            continue
        print(f"\n[{label}] id={ex.record_id}  category={ex.hack_category}")
        print(f"  standalone: verdict={ex.standalone_verdict}  "
              f"score={ex.standalone_score:.3f}  abstain={ex.standalone_abstain}")
        if ex.pair_verdict is not None:
            print(f"  pair-mode:  verdict={ex.pair_verdict}  "
                  f"score={ex.pair_score:.3f}  abstain={ex.pair_abstain}")
        # Print raw check statuses
        sa_raw = ex.standalone_raw
        checks = sa_raw.get("checks", {})
        fired = []
        for k, v in checks.items():
            status = v.get("status") or v.get("severity")
            if status and status != "CLEAN":
                fired.append(f"{k}={status}")
        if fired:
            print(f"  fired: {', '.join(fired)}")
        # Show check_6 score if available
        c6 = checks.get("check_6_behavioral", {})
        if c6:
            import re
            _re = re.compile(r"^\[(\w+) \+\d+\]")
            patterns = []
            for f in c6.get("findings", [])[:5]:
                if "pattern" in f:
                    patterns.append(f["pattern"])
                else:
                    m = _re.match(f.get("explanation", ""))
                    patterns.append(m.group(1) if m else "?")
            print(f"  check_6_score={c6.get('score')}  patterns={patterns}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ast-guard offline eval harness"
    )
    parser.add_argument(
        "--dataset", default="sorh",
        help="Dataset adapter name (default: sorh)"
    )
    parser.add_argument(
        "--output", default="eval/results/sorh",
        help="Output directory for CSV, JSON, and markdown report"
    )
    parser.add_argument(
        "--mode", default="strict",
        choices=["strict", "standard", "audit"],
        help="ast-guard sensitivity mode (default: strict)"
    )
    parser.add_argument(
        "--dev-ratio", type=float, default=0.8,
        help="Fraction of problems in the dev split (default: 0.8)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducible split (default: 42)"
    )
    parser.add_argument(
        "--examples", type=int, default=3,
        help="Number of scored examples to print (default: 3)"
    )
    args = parser.parse_args()

    run(
        dataset=args.dataset,
        output_dir=args.output,
        mode=args.mode,
        dev_ratio=args.dev_ratio,
        split_seed=args.seed,
        print_examples=args.examples,
    )


if __name__ == "__main__":
    main()
