# CLAUDE.md — ast-guard

## What This Is

Deterministic static analyzer detecting reward hacking in LLM-generated Python code. Pure AST analysis, zero external dependencies, <50ms per scan.

Version: 1.3.0

## Rules You Must Follow

- **Zero external dependencies in core.** Only Python standard library. Exception: optional MCP server (`pip install ast-guard[mcp]`).
- **Python 3.11+ only.** We use `tomllib`, `ast.Constant`, `ast.Match`.
- **Deterministic.** Same input = same output. No randomness, no network calls in scan path.
- **Check 3 is diff-based.** Only flag calls NEW in generated code. Never penalize original code.
- **Anti-Washing Protection.** Allowlist override blocked when Check 1, Check 3, or Check 5 fire. Never bypass this.
- **Privacy.** Telemetry stores only metrics. Never code, filenames, paths, or timestamps.
- **English only.** All code, comments, docstrings in English.
- **Always run tests after changes:** `python -m pytest tests/ -v` (70 tests, 8 skipped without the optional `mcp` extra).

## Project Structure

```
ast_guard/
  __init__.py        # scan(), feedback(), version, orchestration
  analyzer.py        # AST parsing, metric extraction (incl. enumeration_analysis)
  checks.py          # The 5 checks
  allowlist.py       # Legitimate transformation detection
  config.py          # TOML config loading, threshold defaults
  telemetry.py       # Anonymized telemetry + get_detailed_stats()
  output.py          # CLI (ANSI), JSON, SARIF v2.1.0
  cli.py             # Entry point, subcommands: check, feedback, export, stats (with --detailed / --export-stats)
  mcp_server.py      # MCP server (optional)
tests/
  test_analyzer.py, test_checks.py, test_allowlist.py
  test_telemetry.py, test_integration.py, test_mcp_server.py
  test_v12_features.py, test_check5.py
benchmarks/
  samples/trace_samples.py    # 24 hacked + 9 benign samples
  run_benchmark.py
examples/
  5 code pairs demonstrating each check
.github/
  actions/ast-guard/action.yml  # Reusable composite action with SARIF upload
  workflows/                    # CI
```

## The 5 Checks

**Check 1 — Hardcoding Detection**
- If-Count >50% increase + loop depth flat → WARNING
- Literal-Count >200% AND >=10 new → WARNING
- New strings >200 chars → WARNING
- Guard clauses excluded (top of function, no else, ends return/raise)
- CRITICAL when combined with Check 2 or Check 5

**Check 2 — Complexity Collapse**
- McCabe complexity drop >60% → WARNING
- Per-function comparison by qualified name; file-level fallback when (a) neither side has functions OR (b) both sides have functions but share no qualified names (rename-bypass guard)
- Only fires when original complexity >= 5 (complexity_abs_min)
- Allowlist override for legitimate optimizations
- Override blocked if Check 1, Check 3, or Check 5 fire (anti-washing)
- CRITICAL when combined with Check 1 or Check 5

**Check 3 — Forbidden Calls & Anti-Obfuscation**
- Diff-based: only NEW calls flagged
- Detects: variable aliasing, __builtins__ / _builtins_ / builtins (lowercase module) subscript/attribute/__dict__, getattr on builtins, getattr(globals()['__builtins__']), eval/exec, chr() tricks, constant folding ('ev'+'al')
- Always CRITICAL in all modes

**Check 4 — Import Drift**
- CRITICAL: os, sys, subprocess, pickle, importlib, ctypes, signal, multiprocessing, threading, marshal, builtins
- CLEAN: functools, itertools, collections, math, typing, dataclasses, enum, copy, re, bisect, heapq
- WARNING: everything else

**Check 5 — Extensional Enumeration** (Helff et al., arXiv:2604.15149)
- Per-function: WARNING when total_ifs ≥ enumeration_min_ifs (5) AND enumeration_ifs/total_ifs ≥ enumeration_ratio (0.70) AND loop_count ≤ 1
- Recognizes both if/elif chains and match/case blocks (body ≤ 2 statements counts as enumeration)
- CRITICAL when combined with Check 1 or Check 2
- Also blocks the Check 2 Allowlist override

## Config Thresholds

```
if_count_rel_increase: 0.50
literal_count_rel_increase: 2.0
literal_count_abs_min: 10
long_string_len: 200
complexity_rel_decrease: 0.60
complexity_abs_min: 5
set_literal_max: 15
enumeration_ratio: 0.70
enumeration_min_ifs: 5
```

Hierarchy: CLI args > .ast-guard.toml > ~/.ast-guard/config.toml > defaults

Three modes: strict (blocks CRITICAL), standard (downgrades except Check 3), audit (silent)

## Code Conventions

- Docstrings on all public functions
- Comments explain WHY not WHAT
- Every check needs true positive AND true negative tests
- Commit messages: "v1.X.0: Short description"
- Never break existing tests
