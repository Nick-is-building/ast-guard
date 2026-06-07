# ast-guard Structural Benchmark

The first benchmark of its kind: a hand-curated, deterministic ground-truth
dataset for **structural** reward-hacking detection — no LLM involvement at
labelling time or evaluation time.

## What this benchmark is

Most existing reward-hacking detection benchmarks rely on LLM judges to decide
whether a model's output is hacking.  That makes the benchmark itself dependent
on the same technology it is trying to evaluate.

This benchmark takes a different approach: every sample is a hand-crafted
Python code pair (original vs. generated) where the ground-truth verdict is
derived directly from AST metrics.  Each sample documents:

- **which structural pattern** is present (12 categories)
- **which checks should fire** (by name)
- **why** — the threshold values that are crossed
- **what real-world dataset** the pattern was drawn from

The benchmark is therefore:

- **Deterministic** — re-running it always produces the same result
- **Explainable** — every PASS or FAIL traces to a specific metric
- **Auditable** — the expected verdicts can be verified by hand

## How samples were selected

Patterns were drawn from documented reward-hacking behaviour across four
sources:

| Source | Pattern categories covered |
|--------|---------------------------|
| METR TRACE taxonomy (Deshpande et al., 2026) | CAT_01, CAT_02, CAT_05, CAT_07, CAT_08, CAT_09 |
| EvilGenie (Gabor, Lynch, Rosenfeld (2025), arXiv:2511.21654) | CAT_03, CAT_04, CAT_08, CAT_10 |
| Terminal Wrench (Bercovich et al., 2026) | CAT_05, CAT_07, CAT_09, CAT_10 |
| Extensional enumeration — concept from Helff et al. (arXiv:2604.15149, 2025), studied there in Prolog-style rule induction; CAT_06/CAT_11 are ast-guard's own Python analogue | CAT_06, CAT_11 |

For each category, at least three samples are included covering:
- a **CRITICAL** case (single check or combination fires at highest severity)
- a **WARNING** case (single check fires, no escalating combo)
- a **CLEAN** or **borderline** case (no hack, or a documented detection gap)

## Categories

| ID | Name | Detection mechanism | Typical verdict |
|----|------|---------------------|----------------|
| CAT_01 | Hardcoded if-chain | Check 1 + Check 5 combo | CRITICAL |
| CAT_02 | Dict lookup table | Check 1 + Check 2 combo | CRITICAL |
| CAT_03 | Long-string encoding | Check 1 (long string), Check 3, Check 4 | WARNING/CRITICAL |
| CAT_04 | eval obfuscation | Check 3 (always CRITICAL) | CRITICAL |
| CAT_05 | Forbidden import | Check 4 (always CRITICAL for blocklist) | CRITICAL |
| CAT_06 | Enumeration shortcut | Check 1 + Check 5 combo | CRITICAL |
| CAT_07 | Test file manipulation | Check 3 (open), Check 4 (subprocess) | CRITICAL/WARNING |
| CAT_08 | Monkey patching | Check 4 (import of patched module) | WARNING/CRITICAL |
| CAT_09 | Process termination | Check 4 (sys/os) + Check 3 | CRITICAL/CLEAN gap |
| CAT_10 | Stack introspection | Check 4 (sys/inspect/ctypes) | WARNING/CRITICAL |
| CAT_11 | Dunder hijacking | Check 2 (complexity collapse on method) | WARNING |
| CAT_12 | Legitimate optimisation | Allowlist overrides Check 2 | CLEAN |

## How to run

```bash
# From repo root
python -m benchmarks.structural_benchmark.runner

# Verbose mode (show check details per sample)
python -m benchmarks.structural_benchmark.runner --verbose

# JSON output
python -m benchmarks.structural_benchmark.runner --json

# Export JSON + Markdown summary
python -m benchmarks.structural_benchmark.runner --export results/structural

# Via the main benchmark runner
python -m benchmarks.run_benchmark --benchmark structural
```

## Performance: ast-guard vs. LLM-based reviewers

A core design goal of ast-guard is real-time gating: scan every generated
code snippet **before** it executes, without adding perceptible latency.

| Reviewer | Latency per scan | Cost per scan | Notes |
|----------|-----------------|---------------|-------|
| ast-guard (structural) | **< 10 ms** | **$0** | Pure AST, no network, no GPU |
| GPT-4o (via API) | 500 – 1500 ms | $0.01 – $0.05 | Includes round-trip, tokenisation |
| Claude Sonnet (via API) | 600 – 2000 ms | $0.01 – $0.10 | Varies with prompt length |
| Local LLM (7B, GPU) | 200 – 800 ms | ~$0 (hardware) | Requires GPU, no cold-start |

**Real-time advantage:**

- An LLM-based reviewer adds **50–200×** latency to each code-execution cycle.
  In a tight eval loop (hundreds of submissions per second), this is
  prohibitive.
- ast-guard runs in the **same process**, on the same CPU, with no network hop.
  At a median of ~2–5 ms per scan, it adds sub-millisecond amortised cost to
  any evaluation harness.
- The two approaches are **complementary**: ast-guard gates structural patterns
  deterministically and cheaply; an LLM reviewer can be applied selectively
  to samples that pass structural checks but show semantic risk.

## Detection gaps (documented)

The following patterns are **not** caught by the current 5 checks in pair mode:

| Pattern | Why missed | Mitigation |
|---------|-----------|------------|
| `raise SystemExit(0)` | No new import; SystemExit not in blocked-call list | Check 6 (behavioral, standalone mode) |
| Assertion weakening (`assert True or expr`) | No structural change to catch | Semantic analysis needed |
| Test result patching via mocks (already-imported module) | No new import, no new forbidden call | Diff of test assertions needed |
| Comment injection to confuse evaluators | Comments not in AST | Out of scope for AST analysis |

## Results

*Run `python -m benchmarks.structural_benchmark.runner` to populate this table.*

| Category | Pass | Total | Pass Rate | Mean ms |
|----------|------|-------|-----------|---------|
| *(run to fill)* | | | | |
