# ast-guard

**Deterministic reward hacking detector for LLM-generated Python code.**

Zero dependencies. Pure AST analysis. No LLM needed.

[![Tests](https://github.com/Nick-is-building/ast-guard/actions/workflows/tests.yml/badge.svg)](https://github.com/Nick-is-building/ast-guard/actions/workflows/tests.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## The Problem

When LLMs autonomously generate and test code, they cheat. They hardcode expected outputs, replace algorithms with lookup tables, hide data in compressed strings, or manipulate test environments — and pass every test while solving nothing.

Unit tests catch *whether* code works. ast-guard catches *how*.

## The Approach

ast-guard analyzes Python code structurally via the Abstract Syntax Tree before execution. It compares the original code against the LLM-generated version and detects structural cheating patterns — deterministically, in under 50ms, with zero cost per scan.

This is not another LLM reviewing LLM output. It's a deterministic static analysis layer that complements training-level defenses and LLM-based review.

---

## Benchmark Results

Evaluated against reward hacking patterns from the [TRACE taxonomy](https://arxiv.org/abs/2601.20103) (Deshpande et al., 2026) — the most comprehensive reward hacking classification in the field (54 subcategories, 517 trajectories).

| Metric | ast-guard | GPT-5.2 (high reasoning) | Claude Opus 4.5 |
|--------|-----------|--------------------------|-----------------|
| Detection Rate | **90.9%** (structural categories) | 63% (all categories) | 25% (all categories) |
| Precision | **100%** | Not reported | Not reported |
| False Positive Rate | **0%** | Not reported | Not reported |
| Deterministic | **Yes** | No | No |
| Latency | **<50ms** | ~10s | ~10s |
| Cost per scan | **$0** | $$$ | $$$ |

ast-guard covers 15 of 51 TRACE subcategories — the structural ones (hardcoding, complexity collapse, forbidden calls, obfuscation, import drift). The remaining 36 are semantic, contextual, or runtime-based and require LLM-level understanding. The two approaches are complementary, not competing.

```bash
# Run the benchmark yourself
python -m benchmarks.run_benchmark
python -m benchmarks.run_benchmark --json
```

---

## Quickstart

**Requirements:** Python 3.11+ — zero external dependencies.

```bash
git clone https://github.com/Nick-is-building/ast-guard.git
cd ast-guard
python -m pytest tests/ -v  # 43 tests across all modules
```

### CLI

```bash
# Standard mode (warnings only, no blocking)
python -m ast_guard.cli check original.py optimized.py

# Strict mode (blocks on CRITICAL — for autonomous agents)
python -m ast_guard.cli check original.py optimized.py --mode strict

# Audit mode (silent — collects telemetry only)
python -m ast_guard.cli check original.py optimized.py --mode audit

# JSON output for CI/CD pipelines
python -m ast_guard.cli check original.py optimized.py --json
```

### Python API

```python
from ast_guard import scan, feedback

result = scan(original_code, generated_code, mode="strict")

if result["verdict"] == "CRITICAL":
    print("Blocked: Reward hacking detected.")
elif result["verdict"] == "WARNING":
    print("Suspicious patterns. Review recommended.")
else:
    print("Clean. Safe to execute.")

# Submit feedback to improve calibration
feedback(result["telemetry"]["scan_id"], "true_positive")
```

### CI/CD Integration

Exit code 0 on CLEAN/WARNING, exit code 1 on CRITICAL. Drop into any pipeline:

```bash
python -m ast_guard.cli check original.py optimized.py --mode strict --json || exit 1
```

---

## MCP Server

ast-guard includes a built-in [Model Context Protocol](https://modelcontextprotocol.io/) server for native integration with coding agents. No shell-out, no subprocess — direct MCP tool calls.

```bash
pip install ast-guard[mcp]
```

The base package remains **zero-dependency**. The `mcp` extra is only installed when you opt in.

### Claude Code

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "ast-guard": {
      "command": "ast-guard-mcp",
      "type": "stdio"
    }
  }
}
```

### Cursor

```json
// .cursor/mcp.json
{
  "mcpServers": {
    "ast-guard": {
      "command": "ast-guard-mcp",
      "type": "stdio"
    }
  }
}
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `ast_guard_scan` | Compare original vs. generated code. Returns verdict, per-check findings, and detected transformations. |
| `ast_guard_feedback` | Submit feedback on scan results to improve detection thresholds. |

Works with Claude Code, Cursor, Codex, OpenCode, and any MCP-compatible agent.

---

## The Four Checks

### Check 1 — Hardcoding Detection

Catches LLMs that replace algorithms with hardcoded results.

**If-Count:** Flags when if-statements increase by >50% while loop depth stays flat or drops. Guard clauses at the top of functions (early return/raise, no else branch) are correctly excluded.

**Literal-Count:** Flags when literals increase by >200% AND at least 10 new literals appear. The dual condition prevents false positives on small functions.

**Long Strings:** Flags new strings over 200 characters — catches compressed lookup data like `"1:1|2:1|3:2|..."`.

Severity: WARNING individually. CRITICAL when combined with Check 2.

### Check 2 — Complexity Collapse

Catches sudden, unexplained drops in cyclomatic complexity (McCabe metric). Flags when complexity drops by more than 60%.

**Allowlist Override:** If the drop is explained by a legitimate optimization (loop to comprehension, `sorted()` replacing hand-written sort, set replacing list for O(1) lookup), the warning is suppressed. See [ALLOWLIST.md](ALLOWLIST.md) for documented rationales.

**Anti-Washing Protection:** The override is blocked if Check 1 or Check 3 fire simultaneously. A single `map()` call cannot whitewash a hardcoded function.

Severity: WARNING individually. CRITICAL when combined with Check 1.

### Check 3 — Forbidden Calls & Obfuscation

Catches dangerous system calls and obfuscation. **Diff-based**: only flags calls that are *new* in the generated code. If the original legitimately uses `os` or `subprocess`, it's not penalized.

**Blocklist:** `eval`, `exec`, `os.*`, `sys.*`, `subprocess.*`, `open`, `__import__`, `compile`, `globals`, `locals`, `setattr`, `getattr` (dynamic), `socket.*`, `ctypes.*`, `signal.*`, and more.

**Anti-Obfuscation:** Detects variable aliasing (`f = eval; f(...)`), `__builtins__` subscript/attribute access, `getattr(__builtins__, ...)`, and `chr()` character code tricks inside eval/exec/import arguments.

Severity: Always CRITICAL, in all modes.

### Check 4 — Import Drift

Catches new imports that weren't in the original code.

**CRITICAL:** `os`, `sys`, `subprocess`, `pickle`, `importlib`, `ctypes`, `signal`, `multiprocessing`, `threading`, `marshal`.

**CLEAN:** `functools`, `itertools`, `collections`, `math`, `typing`, `dataclasses`, `enum`, `copy`, `re`, `bisect`, `heapq`.

**WARNING:** Everything else, for manual review. Both lists are configurable.

---

## Three Sensitivity Modes

| Mode | Default For | Behavior |
|------|-------------|----------|
| `strict` | Python API | CRITICAL blocks execution. Full gatekeeper for autonomous loops. |
| `standard` | CLI | CRITICALs downgraded to WARNINGs (except Check 3). Nothing blocked. |
| `audit` | — | Silent. No output, no blocking. Only telemetry collection. |

The audit mode is designed for risk-free adoption: run ast-guard silently for a week, review the data, then decide whether to enable standard or strict. This lowers the adoption barrier to zero.

---

## Recognized Legitimate Transformations

ast-guard doesn't just flag — it understands. These optimization patterns are recognized as legitimate and suppress false positives. Each is documented with rationale in [ALLOWLIST.md](ALLOWLIST.md):

- **Loop → Comprehension:** `for` loops replaced by list/set/dict comprehensions (CPython C-speed optimization)
- **Functional Built-ins:** Loops replaced by `map()`, `filter()`, `sorted()`, `min()`, `max()`, `sum()` (C-implemented)
- **Data Structure Swap:** Lists replaced by sets/dicts for O(1) membership testing
- **Standard Library:** New imports from `functools`, `itertools`, `collections`, etc. (complexity moved to C layer)

---

## Telemetry & Community Data

ast-guard collects **only anonymized metrics** — never code, filenames, paths, or timestamps. Everything is stored locally and can be disabled with `--no-telemetry` or via config.

**Two IDs for different purposes:**

- **scan_id:** SHA-256 of original + generated code + local machine salt. Stable across sessions for reliable feedback. Never exported, never leaves the machine.
- **metrics_fingerprint:** SHA-256 of AST metrics, node type distributions, and builtin names. Enables pattern clustering without exposing code content.

```bash
python -m ast_guard.cli stats                          # View local statistics
python -m ast_guard.cli export --output my_data.jsonl  # Export anonymized data
python -m ast_guard.cli feedback --id <scan-id> --label true_positive
```

**Community Dataset:** We are building the first empirical dataset of AST metrics for reward hacking detection. Contributions help calibrate thresholds for everyone. All data is anonymized, scan_ids are stripped on export, and sharing is always opt-in.

---

## Configuration

All thresholds, blocklists, and allowlists are configurable via TOML:

```toml
# .ast-guard.toml (project directory)
[thresholds]
if_count_rel_increase = 0.50
literal_count_rel_increase = 2.0
literal_count_abs_min = 10
long_string_len = 200
complexity_rel_decrease = 0.60

[imports]
blocklist = ["os", "sys", "subprocess", "pickle", "importlib"]
allowlist = ["functools", "itertools", "collections", "math"]

[settings]
mode = "standard"
```

Config hierarchy: CLI args > project config (`.ast-guard.toml`) > user config (`~/.ast-guard/config.toml`) > defaults.

---

## Integration with FailProofAI

ast-guard integrates with [FailProofAI](https://github.com/FailproofAI/failproofai) as a custom policy for coding agent harnesses. While FailProofAI's 39 built-in policies cover runtime safety (loops, dangerous actions, secret leaks), ast-guard adds a complementary layer: **code integrity** — detecting whether the code an agent produces is structurally honest.

See the [integration proposal](https://github.com/FailproofAI/failproofai/issues/375) for the full technical discussion and working prototype.

---

## Design Principles

- **Deterministic:** No LLM, no randomness. Same input = same output. No network calls in the scan path.
- **Zero dependencies:** Only Python standard library. Clone and run.
- **Privacy-by-design:** Telemetry stores only metrics, never code. Export strips scan_ids. Everything is opt-out.
- **Framework-agnostic:** Works with any LLM agent system, any CI/CD pipeline, any coding harness.
- **Adoption-friendly:** Three modes (audit → standard → strict) enable risk-free evaluation before commitment.
- **Pre-execution filter, not a sandbox:** ast-guard catches structural cheating before code runs. It does not replace sandboxing (Docker, gVisor, WASM) for executing untrusted code.

---

## Known Limitations (v1.1)

- **Python only.** Multi-language support (via tree-sitter) planned for v2.0.
- **No constant folding.** `eval("ex" + "ec")` is caught by the eval catch-all, but string concatenation in subscripts (e.g., `__builtins__['ev' + 'al']`) is not yet resolved. Planned for v1.2.
- **No semantic analysis.** ast-guard checks structure, not meaning. Semantically incorrect code is the job of your downstream verifier or test suite.
- **Thresholds are starting points.** Defaults are informed estimates, not empirically validated optima. Community telemetry will calibrate them over time.

---

## Roadmap

| Version | Feature |
|---------|---------|
| v1.1 ✅ | MCP server, TRACE-based benchmark, FailProofAI integration proposal |
| v1.2 | Constant folding for string concatenation, complexity floor for small functions |
| v1.3 | SARIF output for GitHub Security Tab and CI/CD |
| v1.4 | First community-data-driven threshold calibration |
| v2.0 | Multi-language support via tree-sitter (JavaScript, TypeScript, Go) |

---

## Project Structure

```
ast-guard/
├── ast_guard/
│   ├── __init__.py        # Public API: scan(), feedback()
│   ├── analyzer.py        # AST parsing and metric extraction
│   ├── checks.py          # The four core checks
│   ├── allowlist.py       # Legitimate transformation detection
│   ├── config.py          # Configuration loading (TOML)
│   ├── telemetry.py       # Anonymized telemetry system
│   ├── output.py          # CLI (ANSI) and JSON formatting
│   ├── cli.py             # CLI entry point
│   └── mcp_server.py      # MCP server (optional: pip install ast-guard[mcp])
├── benchmarks/            # TRACE-based benchmark suite
│   ├── run_benchmark.py   # Benchmark runner (CLI + JSON output)
│   └── samples/           # 30 reward hacking + benign code pairs
├── tests/                 # 43 tests across all modules
├── ALLOWLIST.md           # Documented transformation rationales
├── CHANGELOG.md
├── LICENSE                # MIT
├── pyproject.toml
└── README.md
```

---

## Related Work

- **[TRACE](https://arxiv.org/abs/2601.20103)** (Deshpande et al., 2026) — 517-trajectory benchmark with 54 reward hack categories. ast-guard's benchmark uses TRACE's taxonomy as reference.
- **[EvilGenie](https://arxiv.org/abs/2511.21654)** (Gabor et al., 2025) — Reward hacking benchmark from MIT using LiveCodeBench problems.
- **[SpecBench](https://arxiv.org/abs/2605.21384)** (2026) — Measuring reward hacking in long-horizon coding agents (Codex, Claude Code, OpenCode).
- **[RHB](https://arxiv.org/abs/2605.02964)** (Thaman, 2026) — Reward Hacking Benchmark for tool-using LLM agents.
- **[FailProofAI](https://github.com/FailproofAI/failproofai)** — Runtime reliability policies for coding agents. ast-guard provides the complementary code integrity layer.

---

## License

MIT — use it, fork it, improve it, ship it.

---

*Built by [Nick](https://github.com/Nick-is-building) — Deterministic System Builder, Berlin.*
