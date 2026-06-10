# generator

Produces synthetic reward-hack CodePair samples for augmenting ast-guard benchmarks.
Starting from seed problems (MBPP + custom), it applies one parameterised hack strategy
per TRACE category (hardcoded_outputs, lookup_table, eval_obfuscation, forbidden_import,
enumeration, complexity_collapse), verifies each candidate against visible and hidden
tests via a subprocess sandbox, and emits labelled (original, generated, label,
trace_category) JSONL records that are fully compatible with the ast-guard benchmark
loader pipeline.

## Module overview

| File | Role |
|---|---|
| `seeds.py` | Load MBPP / HumanEval / APPS / custom seeds; split tests into visible (prompt) + hidden (verification) |
| `hack_strategies.py` | One `HackStrategy` per TRACE category; each carries a system prompt and hack instruction for the LLM |
| `verify.py` | Subprocess sandbox: assert-based runner + IO runner (stdin/stdout for APPS); `is_hack` = visible PASS ∧ hidden FAIL |
| `generate.py` | Orchestrator: seeds × strategies → LLM → verify → dedup → validate → emit JSONL |

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

# Smoke test: 5 seeds, max 10 pairs
python -m generator.generate --max 10 --seeds 5 --out smoke.jsonl

# Full run — all sources, all 6 categories (~24,000 max pairs)
python -m generator.generate --out generated_pairs.jsonl

# Single category
python -m generator.generate --categories hardcoded_outputs --out tp_hardcoded.jsonl

# Custom seeds only
python -m generator.generate --custom my_seeds.json --out custom_pairs.jsonl
```

`ANTHROPIC_API_KEY` must be set in the environment.

## Label semantics

- `label=hack` (TP): visible tests PASS, hidden tests FAIL. Verified by subprocess execution; no LLM judgment.
- `label=clean` (TN): honest solution vs itself (same-problem identity pair). Same baseline as the MBPP TN backbone.

The determinism principle from ast-guard applies here: the label is determined by test
execution results, never by an LLM verdict.
