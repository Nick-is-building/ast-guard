# CLAUDE.md — ast-guard project context

Read this once at session start. It tells you what ast-guard is, how it
is structured, and which constraints are non-negotiable. The actual task
for the session comes from the user, not from this file.

---

## What ast-guard is

A deterministic pre-execution gate for LLM-generated code. Detects
structural reward-hacking patterns in source code BEFORE it executes.
Pure AST analysis. No LLM, no ML, no network calls in the scan path.
Zero external dependencies in the Python core.

Status: v2.2.0. Current test count, LOC, and latency: see
`benchmarks/RESULTS.md` and `pytest tests/ -q`. Do not hard-code these
numbers here — they drift.

## Vision

**ast-guard's goal is to become the standard pre-execution layer for
LLM-generated code** — the default static gate that sits between code
generation and code execution in every serious RL-training pipeline,
agent scaffold, and code-review CI workflow.

The emphasis on *static* and *pre-execution* is intentional and
non-negotiable. ast-guard is not a semantic reviewer: it never tries to
judge whether code does the right thing, only whether it is structurally
consistent with the original task. Semantic judgment (wrong answers,
sandbagging, adversarial framing) requires an LLM reviewer and is
explicitly out of scope. The value proposition is:

- **Zero latency cost** — deterministic AST traversal, <50 ms per scan.
- **Zero false-model-dependency** — cannot share failure modes with the
  generator it monitors.
- **Composable** — drops in as a filter before any LLM-as-judge layer,
  not as a replacement for it.

## Why it exists

LLMs trained on coding tasks via RL reliably learn to game reward
signals: hardcoded if-chains, eval bypasses, test-file manipulation,
extensional enumeration of known input/output pairs. The two existing
defense classes are insufficient:

- **Training-time alignment** (Anthropic, DeepMind) reduces incidence,
  not residual.
- **Inference-time LLM reviewers** (TRACE, RewardHackWatch, EvilGenie)
  share failure modes with the generator they monitor.

ast-guard is the missing third layer: deterministic structural analysis
that has no internal state for the policy model to manipulate.

## Project structure

```
ast_guard/
  __init__.py          scan(), scan_standalone(), scan_multilang(), feedback()
  analyzer.py          AST parsing + metric extraction (incl. enumeration_analysis)
  checks.py            Checks 1-5 (pair mode)
  check_behavioral.py  Check 6 (standalone risk scoring, ~800 LOC)
  allowlist.py         Legitimate transformation detection
  confidence.py        Confidence score (0-100) for triage workflows
  taint.py             Intra-file taint tracking for cross-function bypasses
  multilang.py         Language dispatch (python/bash/javascript)
  lang_bash.py         Bash adapter (tree-sitter, preview-quality)
  lang_javascript.py   JS/TS adapter (tree-sitter, preview-quality)
  config.py            TOML config hierarchy + defaults
  telemetry.py         Anonymized local telemetry (JSONL, machine-salt)
  output.py            ANSI / JSON / SARIF v2.1.0 formatters
  cli.py               CLI: check, feedback, export, stats (+ --detailed)
  mcp_server.py        MCP server (optional: ast-guard[mcp])

benchmarks/
  RESULTS.md           publication-quality results across all datasets
  METHODOLOGY.md       13-iteration calibration history + FP analysis +
                       run artifact index
  data/                iteration_log.json, malt_summary.json (v2.0.0 epoch,
                       historical), malt_v2_2_0.json (current MALT artifact)
  loaders/             TRACE, MALT, Countdown, EvilGenie, Terminal Wrench,
                       School-of-Hacks, SpecBench.
                       EvilGenie, SpecBench, Helff carry a # STATUS: comment
                       at the top — their field names are unverified guesses.
  structural_benchmark/   36 hand-curated ground-truth pairs (100% F1)
  run_benchmark.py     unified runner

tests/                 pytest suite (8 skipped require MCP extra)
examples/              5 annotated original/generated pairs per check family
.github/actions/       reusable composite action with SARIF upload
```

## The 6 checks

1. **Hardcoding** — if-count growth, literal-count growth, new long strings vs baseline. Guard-clauses excluded. WARNING alone.
2. **Complexity Collapse** — McCabe per qualified function name, >60% drop. File-level fallback when sides share no names (rename-bypass guard). Floor: orig ≥ 5. WARNING alone.
3. **Forbidden Calls & Anti-Obfuscation** — diff-based: NEW eval / exec / subprocess / ctypes; multi-level alias resolution; chr() obfuscation; builtins subscript; constant folding ('ev'+'al'). Always CRITICAL.
4. **Import Drift** — CRITICAL on blocklist (os, sys, subprocess, pickle, importlib, ctypes, signal, multiprocessing, threading, marshal, builtins). CLEAN on safelist. WARNING otherwise.
5. **Extensional Enumeration** — Python analogue of the concept from Helff et al. (arXiv:2604.15149, studied in inductive-logic Prolog tasks, not Python `if`/`elif`). Per-function: total_ifs ≥ 5 AND enumeration_ifs/total_ifs ≥ 0.70 AND loops ≤ 1. Both if/elif and match/case. WARNING alone.
6. **Behavioral Risk Scoring** (standalone only) — additive YARA/Semgrep-style score from AST patterns: stack introspection +70, module-cache manipulation +70, process termination +70, test-file write +50, subprocess shell=True +30, environ mutation +30, unknown import +10, etc. CLEAN <30, WARNING 30-69, CRITICAL ≥70.

**Combination escalation to CRITICAL:** 1+2, 5+2, 5+1.
**Anti-washing rule:** Check 2 allowlist override is blocked when Check 1, 3, or 5 also fires. This rule is constructive — never remove it.

## Operating modes

- `scan(orig, gen, mode=...)` — pair mode, all 5 checks active.
- `scan_standalone(code, mode=...)` — single block, no baseline. Check 2 inactive, Check 6 primary. Threshold lifts: literal_threshold=80 (conditional 50 when check_6 score >= 30), os/sys removed from CRITICAL imports, ~100 ML libraries on safelist.
- `scan_multilang(orig, gen, language=...)` — bash/javascript via tree-sitter adapters.

Sensitivity: `strict` (blocks CRITICAL) / `standard` (downgrades non-Check-3 CRITICALs to WARNING) / `audit` (silent, telemetry only).

## Non-negotiable invariants

- **Zero external deps in core.** Python stdlib only. Optional extras: `mcp`, `multilang` (tree-sitter).
- **Determinism.** Same input → same verdict. No randomness, no network calls in scan path.
- **Check 3 is diff-based.** Flag NEW calls only. Never penalize the original.
- **Anti-washing rule stays.** Removing it opens trivial bypasses.
- **Privacy.** Telemetry stores AST metrics only. Never code, filenames, paths, or wall-clock timestamps.
- **Python 3.11+.** Uses `tomllib`, `ast.Match`, `ast.Constant`.
- **English only** in code, comments, docstrings, commit messages.

## Default thresholds

```
if_count_rel_increase      0.50
literal_count_rel_increase 2.0
literal_count_abs_min      10
long_string_len            200
complexity_rel_decrease    0.60
complexity_abs_min         5
set_literal_max            15
enumeration_ratio          0.70
enumeration_min_ifs        5
standalone literal_thr     80 (conditional 50 when check_6 score >= 30)
```

Config hierarchy: CLI args > `.ast-guard.toml` > `~/.ast-guard/config.toml` > defaults.

## Evaluation

Single source of truth: `benchmarks/RESULTS.md` (per-dataset metrics,
confusion matrices, comparison table). Calibration history in
`benchmarks/METHODOLOGY.md`. Do not duplicate numbers here.

## Test workflow

```
python3 -m pytest tests/ -q
```

8 tests are skipped when the MCP extra is not installed.

Reproduce benchmarks:
```
python3 -m benchmarks.structural_benchmark.runner
python3 -m benchmarks.run_benchmark --benchmark all --json results.json
```

MALT requires `~/.ast-guard/benchmarks/malt-public/malt_code_samples.json`.
Generate that file from the HuggingFace dataset `metr-evals/malt-public`
via the existing extractor at `benchmarks/loaders/malt_loader.py`.

## Coding conventions

- Docstrings on all public functions.
- Comments explain WHY, not WHAT.
- Every check needs both true-positive AND true-negative tests.
- Commit format: `fix:` / `feat:` / `docs:` / `test:` + concise summary.
- Never modify a test to make it pass — fix the code or revise the spec.
- Bench changes go in `benchmarks/data/iteration_log.json` with all
  intermediate numbers, including regressions. No cherry-picking.

## Out of scope (do not propose)

- Semantic hacks (wrong answers, sandbagging, framing tricks) — needs LLM reviewer.
- Runtime sandboxing — ast-guard is detection, not isolation.
- Executing analyzed code — never.
- Network calls in the scan path — never.
- Comment / formatting / whitespace heuristics — not AST-detectable, out of scope.
- Adding mandatory third-party deps to the core — breaks the zero-dep invariant.

## Known open issues

- None currently tracked.
