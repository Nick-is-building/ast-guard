"""
eval — offline evaluation harness for ast-guard.

Modules:
    record    — EvalRecord and ScoredRecord dataclasses
    scoring   — score_record(): binary verdict + graduated suspicion score
    metrics   — compute_metrics(): PR-AUC, P@R, R@P, F1, confusion matrix
    report    — write_report(): per_item.csv, metrics.json, report.md
    adapters  — dataset adapter interface + SORH adapter
    run       — CLI entry point

Usage:
    python -m eval.run --dataset sorh --output results/sorh/
"""
