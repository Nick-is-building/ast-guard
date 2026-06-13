# Generator Split Artifacts

JSONL data files produced by the built-in generator
(`python3 -m generator.generate`). Each file is a snapshot of a specific
generation run, committed here so that all reported numbers are reproducible
from the artifacts, not just from re-running the generator.

Machine-readable evaluation history: `../generator_eval_log.json`.

---

## Seed Range Map

The MBPP loader skips the first 600 problems in the HuggingFace dataset
(IDs 1–600, which lack test suites or are low quality). The generator's
`--skip-seeds N` advances N rows in the filtered loader.

| Seed range | Role | File(s) |
|------------|------|---------|
| mbpp-601–660 | **Calibration** — Check 7+8 development, never used for final metrics | `eval_mbpp601-660.jsonl` |
| mbpp-661–700 | **Independent validation** — first unseen-seed evaluation | `eval_mbpp661-700.jsonl`, `calibration_mbpp661-700.jsonl` |
| mbpp-701–740 | **Check 7 compare-return extension** — secondary eval split | `eval_mbpp701-740.jsonl` |
| mbpp-741–780 | **Floor-lowering experiment** — floor=2 vs floor=1 comparison | `eval_mbpp741-780.jsonl`, `calibration_mbpp741-780.jsonl` |
| mbpp-601–740 | **All calibration pairs** (coupled strategies + TNs) | `calibration_mbpp601-740.jsonl` |

---

## File Descriptions

### `eval_mbpp601-660.jsonl`
- **Role:** Development split for Checks 7 and 8
- **Seeds:** mbpp-601–660 (60 seeds, `--skip-seeds 0`)
- **Records:** 569 (509 hacks, 60 easy TNs)
- **Generation:** `--open --seeds 60 --out-eval eval_pairs.jsonl`
- **Models:** claude-sonnet-4-6
- **Variants:** imperative, adversarial
- **Use:** Threshold calibration for `_ORIG_COMPLEXITY_FLOOR`, literal specificity
  filters, and taint analysis parameters. Not used for reported metrics.

### `eval_mbpp661-700.jsonl`
- **Role:** Independent validation split — primary published result (floor=2), later re-scored at floor=1
- **Seeds:** mbpp-661–700 (40 seeds, `--skip-seeds 60`)
- **Records:** 136 (57 hacks, 40 easy TNs, 39 hard TNs)
- **Generation:** `--open --seeds 40 --skip-seeds 60 --hard-tn`
- **Models:** claude-sonnet-4-6
- **Variants:** imperative, adversarial

**Results at floor=2 (original):**

| Recall | Prec easy TN | Prec hard TN | FPR | F1 |
|--------|--------------|--------------|-----|----|
| 0.684 | 1.000 | 0.897 | 0.051 | 0.780 |

**Results at floor=1 (after floor change, same file):**

| Recall | Prec easy TN | Prec hard TN | FPR | F1 |
|--------|--------------|--------------|-----|----|
| **0.965** | 1.000 | 0.897 | 0.051 | **0.957** |

Floor change: +28.1 pp recall, zero precision cost, zero new FPs.

### `calibration_mbpp661-700.jsonl`
- **Role:** Calibration-split TNs for the validation seeds (honest-vs-honest only)
- **Records:** 40 (all clean, calibration split)

### `eval_mbpp701-740.jsonl`
- **Role:** Secondary eval split for Check 7 compare-return extension
- **Seeds:** mbpp-701–740 (40 seeds, `--skip-seeds 100`)
- **Records:** 245 (171 hacks, 40 easy TNs, 34 hard TNs)
- **Generation:** `--open --seeds 40 --skip-seeds 100 --hard-tn`
- **Models:** claude-sonnet-4-6, claude-opus-4-7, claude-haiku-4-5-20251001
- **Variants:** imperative, adversarial, competitive

### `eval_mbpp741-780.jsonl`
- **Role:** Floor-lowering experiment — the primary evidence for the floor=1 decision
- **Seeds:** mbpp-741–780 (40 seeds, `--skip-seeds 140`)
- **Records:** 244 (169 hacks, 40 easy TNs, 35 hard TNs)
- **Generation:** `--open --seeds 40 --skip-seeds 140 --hard-tn`
- **Models:** claude-sonnet-4-6, claude-opus-4-7, claude-haiku-4-5-20251001
- **Variants:** imperative, adversarial, competitive

**Floor experiment results (four configs, same file):**

| Config | floor7 | floor8 | Recall | Prec easy | Prec hard | New FPs |
|--------|--------|--------|--------|-----------|-----------|---------|
| A (baseline) | 2 | 2 | 0.757 | 1.000 | 0.857 | — |
| B (both) | 1 | 1 | **0.864** | 1.000 | 0.857 | **0** |
| C (C7 only) | 1 | 2 | 0.805 | 1.000 | 0.857 | 0 |
| D (C8 only) | 2 | 1 | 0.817 | 1.000 | 0.857 | 0 |

Decision: floor=1 adopted for both checks. Full protocol in
`METHODOLOGY.md § Floor-Lowering Experiment`.

### `calibration_mbpp741-780.jsonl`
- **Role:** Calibration-split TNs and coupled-strategy TPs for the floor experiment seeds
- **Records:** 148 (108 hacks, 40 TNs)

### `calibration_mbpp601-740.jsonl`
- **Role:** Main calibration corpus — all generation runs from the development phase
- **Seeds:** mbpp-601–740 (100 seeds, cumulative)
- **Records:** 589 (417 hacks across 6 coupled strategies, 172 honest-vs-honest TNs)
- **Coupled strategies:** hardcoded_outputs, lookup_table, enumeration,
  complexity_collapse, forbidden_import, eval_obfuscation

---

## How to Re-Score

Any eval file can be re-scored against the current code:

```bash
python3 -m benchmarks.score_validation --path benchmarks/data/generator_splits/eval_mbpp661-700.jsonl
```

The floor experiment (four configs in one pass):

```bash
python3 -m benchmarks.floor_experiment --path benchmarks/data/generator_splits/eval_mbpp741-780.jsonl
```

## How to Reproduce the Generation

Each eval file can be reproduced from scratch (results will differ due to LLM
non-determinism, but the structural split and seed range are fixed):

```bash
# Independent validation split (mbpp-661-700)
python3 -m generator.generate \
  --open --seeds 40 --skip-seeds 60 --hard-tn \
  --out-eval benchmarks/data/generator_splits/eval_mbpp661-700_repro.jsonl \
  --out-calibration benchmarks/data/generator_splits/calibration_mbpp661-700_repro.jsonl

# Floor experiment split (mbpp-741-780)
python3 -m generator.generate \
  --open --seeds 40 --skip-seeds 140 --hard-tn \
  --out-eval benchmarks/data/generator_splits/eval_mbpp741-780_repro.jsonl \
  --out-calibration benchmarks/data/generator_splits/calibration_mbpp741-780_repro.jsonl
```
