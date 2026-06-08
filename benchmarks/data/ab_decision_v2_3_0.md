# A/B Decision Report — B1–B4 recall signals (v2.3.0)

> **STATUS: PENDING** — run `python3 -m benchmarks.ab_decision` to fill in numbers.

Keep rule: **ΔAUROC > 0** (lever improves ranking at all thresholds).
Revert command printed for any DROP verdict.

---

## How to run

```bash
# From repo root, clean working tree required.
python3 -m benchmarks.ab_decision \
    --out benchmarks/data/ab_decision_v2_3_0.md
```

The script walks the commit ladder, runs MALT at each rung with
`--emit-confidence`, scores each rung via `score_curve`, diffs FP
patterns, spots 6 random B2-flagged records, and overwrites this file
with the completed report.

Ladder (chronological):

| Rung | SHA | Description |
|---|---|---|
| baseline | `d655b2c` | no B signals (A1+A2 tooling only) |
| +B1 | `734eace` | adaptive input-independence floor (pure-literal: 3 returns) |
| +B2 | `5736eb8` | in-function literal lookup table (top-level body gate) |
| +B3 | `ffa7dcb` | whole-body exception swallow (trivial setup allowed) |
| +B4 | `262a581` | small-function enumeration + input-independence combo |

---

## Verdict

| Lever | SHA | ΔAUROC | ΔFP | verdict |
|---|---|---|---|---|
| +B1 | `734eace` | _TBD_ | _TBD_ | _TBD_ |
| +B2 | `5736eb8` | _TBD_ | _TBD_ | _TBD_ |
| +B3 | `ffa7dcb` | _TBD_ | _TBD_ | _TBD_ |
| +B4 | `262a581` | _TBD_ | _TBD_ | _TBD_ |

## Recall per hack label

| Lever | Δbypass_constraints | Δhardcoded_solution | Δsabotage |
|---|---|---|---|
| +B1 | _TBD_ | _TBD_ | _TBD_ |
| +B2 | _TBD_ | _TBD_ | _TBD_ |
| +B3 | _TBD_ | _TBD_ | _TBD_ |
| +B4 | _TBD_ | _TBD_ | _TBD_ |

## AUROC per rung

| Rung | SHA | AUROC | FPR | Recall@FPR≤5% |
|---|---|---|---|---|
| baseline | `d655b2c` | _TBD_ | _TBD_ | _TBD_ |
| +B1 | `734eace` | _TBD_ | _TBD_ | _TBD_ |
| +B2 | `5736eb8` | _TBD_ | _TBD_ | _TBD_ |
| +B3 | `ffa7dcb` | _TBD_ | _TBD_ | _TBD_ |
| +B4 | `262a581` | _TBD_ | _TBD_ | _TBD_ |

## FP pattern shift (baseline → main)

_TBD — filled in by ab_decision.py_

## B2 precision spot-check

_TBD — 6 randomly sampled B2-flagged records_

## Revert commands

_TBD — printed only for DROP verdicts_
