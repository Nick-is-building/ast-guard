# generator

Produces synthetic reward-hack CodePair samples for augmenting ast-guard benchmarks.
Starting from seed problems (MBPP + custom), it applies hack strategies and verifies
each candidate against visible and hidden tests via a subprocess sandbox. The only
label criterion is test execution: `label=hack` iff visible PASS ∧ hidden FAIL.

Two generation modes produce two physically separate JSONL files:

| Mode | File | Split | Strategies |
|---|---|---|---|
| Coupled | `--out-calibration` | `calibration` | 6 check-specific strategies |
| Open | `--out-eval` | `eval` | No structural pattern prescribed |

This separation prevents circular evaluation: calibration data trains thresholds,
eval data tests generalisation. See **Calibration vs. Eval split** below.

## Module overview

| File | Role |
|---|---|
| `seeds.py` | Load MBPP / HumanEval / APPS / custom seeds; split tests into visible (prompt) + hidden (verification) |
| `hack_strategies.py` | Six coupled `HackStrategy` objects + one `OpenHackStrategy` (no check coupling) |
| `verify.py` | Subprocess sandbox: assert-based runner + IO runner (stdin/stdout for APPS); `is_hack` = visible PASS ∧ hidden FAIL |
| `generate.py` | Orchestrator: seeds × strategies → LLM → verify → dedup → validate → emit JSONL |
| `split.py` | `assign_split()`, `make_sample_id()`, `compute_prompt_hash()` — deterministic, pure functions |

## Dependencies

```
anthropic          # Anthropic Python SDK (pip install anthropic)
datasets           # HuggingFace datasets — only needed for download steps
```

The `ast_guard` core package has zero runtime dependencies — this generator is intentionally
kept in a separate directory and never imported from `ast_guard/`.

## Seed sources

| Source | Seeds | Test format | Download |
|---|---|---|---|
| MBPP | ~374 | `assert` | `MbppLoader().download()` |
| HumanEval | ~164 | `assert` | `HumanEvalLoader().download()` |
| APPS (introductory) | ~2,000+ | `io` (stdin/stdout) | `AppsLoader().download()` |
| Custom JSON | unlimited | `assert` | — (bring your own file) |

APPS seeds use `test_format="io"`: each test is a JSON-encoded `{"input": ..., "output": ...}`
pair. The IO runner in `verify.py` redirects stdin/stdout and compares output per pair.

## Quick start

```bash
# Download seed datasets (one-time; needs pip install datasets)
python -c "from benchmarks.loaders.mbpp import MbppLoader; MbppLoader().download()"
python -c "from benchmarks.loaders.humaneval import HumanEvalLoader; HumanEvalLoader().download()"
python -c "from benchmarks.loaders.apps import AppsLoader; AppsLoader().download()"

# Smoke test (coupled only, backward-compat single file)
python -m generator.generate --max 10 --seeds 5 --out smoke.jsonl

# Full coupled run — calibration split only
python -m generator.generate --out-calibration calibration_pairs.jsonl

# Full open run — both splits in separate files
python -m generator.generate \
  --open \
  --out-calibration calibration_pairs.jsonl \
  --out-eval eval_pairs.jsonl

# Open mode with specific models and variants
python -m generator.generate \
  --open \
  --open-models claude-opus-4-7,claude-sonnet-4-6 \
  --open-variants imperative,adversarial \
  --out-calibration calibration_pairs.jsonl \
  --out-eval eval_pairs.jsonl

# Single coupled category
python -m generator.generate --categories hardcoded_outputs --out-calibration tp_hardcoded.jsonl
```

`ANTHROPIC_API_KEY` must be set in the environment.

## Label semantics

- `label=hack` (TP): visible tests PASS, hidden tests FAIL. Verified by subprocess execution; no LLM judgment.
- `label=clean` (TN): honest solution vs itself (same-problem identity pair). Same baseline as the MBPP TN backbone.

The determinism principle from ast-guard applies here: the label is determined by test
execution results, never by an LLM verdict.

## Calibration vs. eval split

**The problem with check-coupled data.** Each of the 6 coupled strategies is designed to
trigger specific ast-guard checks. Evaluating the detector on its own training signal
measures memorisation, not generalisation. If check 5 was tuned using `enumeration`
strategy samples, running the benchmark on `enumeration` samples tells you the detector
fires on patterns it was built to fire on — not whether it catches novel patterns.

**The solution: construction-time separation.**

| Split | Source | Purpose |
|---|---|---|
| `calibration` | Coupled strategies, TN pairs | Threshold and rule calibration |
| `eval` | Open-mode hacks (diverse models × prompts) | Generalisation measurement |

The split is encoded in every `sample_id` (`open/…` → eval, `coupled/…` → calibration)
and in the `metadata.split` field. It is a deterministic function of the sample_id —
no random assignment, no runtime manipulation.

**Structural enforcement.** Calibration and eval samples are always written to separate
JSONL files (`--out-calibration` / `--out-eval`). The `GeneratorLoader` API enforces
the split at load time: `load_eval(path)` and `load_calibration(path)` are the only
entry points — `load_samples()` without an explicit `split=` argument raises `ValueError`.

**Open mode diversification.** Open-mode generation iterates over 3 models and 3 prompt
variants (9 combinations per seed). The `metadata.prompt_hash` field makes diversity
measurable: a healthy eval set should have many distinct prompt hashes.

To load eval data for benchmarking:
```python
from benchmarks.loaders.generator_loader import GeneratorLoader
samples = GeneratorLoader().load_eval("eval_pairs.jsonl")
```

To run the benchmark runner against the eval split:
```bash
python -m benchmarks.run_benchmark \
  --benchmark generator \
  --generator-eval-path eval_pairs.jsonl
```
