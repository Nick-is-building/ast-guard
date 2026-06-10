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
| `seeds.py` | Load MBPP / custom seed problems; split test_list into visible (prompt) + hidden (verification) |
| `hack_strategies.py` | One `HackStrategy` per TRACE category; each carries a system prompt and hack instruction for the LLM |
| `verify.py` | Subprocess sandbox: run generated code against visible and hidden tests; `is_hack` = visible PASS ∧ hidden FAIL |
| `generate.py` | Orchestrator: seeds × strategies → LLM → verify → dedup → validate → emit JSONL |

## Dependencies

```
anthropic          # Anthropic Python SDK (pip install anthropic)
```

The `ast_guard` core package has zero runtime dependencies — this generator is intentionally
kept in a separate directory and never imported from `ast_guard/`.

## Quick start

```bash
# Smoke test: generate up to 10 pairs from the first 5 MBPP seeds
python -m generator.generate --max 10 --seeds 5 --out smoke.jsonl

# Full run (all MBPP seeds, all 6 categories)
python -m generator.generate --out generated_pairs.jsonl

# Single category
python -m generator.generate --categories hardcoded_outputs --out tp_hardcoded.jsonl
```

`ANTHROPIC_API_KEY` must be set in the environment.

## Label semantics

- `label=hack` (TP): visible tests PASS, hidden tests FAIL. Verified by subprocess execution; no LLM judgment.
- `label=clean` (TN): honest solution vs itself (same-problem identity pair). Same baseline as the MBPP TN backbone.

The determinism principle from ast-guard applies here: the label is determined by test
execution results, never by an LLM verdict.
