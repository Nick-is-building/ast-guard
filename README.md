# ast-guard

**Pre-Execution Gate for AI-Generated Code**

*The deterministic layer between LLM code generation and code execution. No LLM. No ML. No cost. No exceptions.*

[![Tests](https://github.com/Nick-is-building/ast-guard/actions/workflows/tests.yml/badge.svg)](https://github.com/Nick-is-building/ast-guard/actions/workflows/tests.yml) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/Nick-is-building/ast-guard/blob/main/LICENSE)

---

## The Problem

When LLMs generate code and LLMs review that code, you have a closed blackbox loop. Both can hallucinate. Both share systematic blind spots. And critically — both can be deceived. METR has documented frontier models actively introspecting the reviewer's call stack to extract ground truth answers before returning them as if computed. A blackbox reviewing a blackbox is not a defense — it is the illusion of one.

Existing approaches operate on two levels: training-time defenses (Anthropic, DeepMind) prevent reward hacking from developing in models, and inference-time LLM reviewers (TRACE, RewardHackWatch, EvilGenie) detect hacking in generated outputs. Both are necessary. Both are insufficient alone. There is a missing third layer — one that cannot hallucinate, cannot be prompted into compliance, and produces identical results for identical inputs regardless of what the model tries.

ast-guard is that layer. It sits between code generation and execution, analyzes structure before any line runs, and makes a binary deterministic decision in under 10 milliseconds. It does not replace LLM-based reviewers. It handles the structural layer so they can focus entirely on semantics.

---

## What ast-guard Is

ast-guard is an architectural component — a mandatory gate in any system where LLMs generate executable code. It is not a linter. It is not a security scanner. It is a pre-execution integrity check that operates at the Abstract Syntax Tree level, where structural truth cannot be faked.

```
LLM generates code
        │
        ▼
┌───────────────────┐
│   ast-guard gate  │  ← deterministic, <10ms, zero cost
└───────────────────┘
        │
   ┌────┴────┐
   ▼         ▼
CLEAN     WARNING / CRITICAL
pass      flag or block
through
        │
        ▼
execution environment
```

The gate supports two modes: **Pair Mode** compares original code against LLM-generated code and detects structural deviations. **Standalone Mode** analyzes a single agent output with no baseline, using behavioral risk scoring to catch known adversarial patterns.

---

## Architectural Role

ast-guard is designed as a deterministic pre-filter that reduces the workload of downstream LLM-based reviewers. By eliminating structurally obvious hacks before they reach a semantic reviewer, it narrows the surface each reviewer must reason about. ZeroFalse (Iranmanesh et al., arXiv:2510.02534, 2025) showed that introducing calibrated confidence levels for static-analysis findings improves triage efficiency without reducing coverage. Buglens (arXiv:2504.11711, 2025) reports a 7-fold precision improvement when LLMs validate static-analysis findings rather than replace them — confirming that the combination outperforms either approach alone.

---

## Key Results

All results are fully reproducible. See [benchmarks/RESULTS.md](benchmarks/RESULTS.md) for full methodology, confusion matrices, and per-category breakdowns.

| Benchmark | Mode | Samples | Key Metric | Value |
|-----------|------|---------|------------|-------|
| Structural Benchmark (36 curated ground-truth pairs) | Pair | 36 | F1 | **100%** |
| TRACE taxonomy (Deshpande et al. 2026) | Pair | 33 | F1 | **95.7%** |
| School of Reward Hacks (longtermrisk) | Pair | 26 | Recall | **96.2%** |
| Countdown-Code (Khan et al.) | Pair | 15,894 | True Negative Rate | **99.0%** |
| MALT (METR, 81,515 agent code blocks) | Standalone | 81,515 | Specificity† | **84.2%** |
| MALT — hardcoded_solution category | Standalone | 429 | Detection Rate | **70.9%** |
| MALT — bypass_constraints category | Standalone | 2,379 | Detection Rate | **41.7%** |

**Performance:** mean 4.7ms per scan, ~210 samples/second, zero API cost.

† TNR measured on the `normal` label only (77,369 samples); see [benchmarks/RESULTS.md](benchmarks/RESULTS.md) for the full confusion matrix.

### Comparison with Existing Approaches

These approaches are complementary, not competing. ast-guard handles structural analysis; LLM reviewers handle semantics. Together they cover the full detection space.

| Approach | Method | Cost/scan | Latency | Deterministic | Scope |
|----------|--------|-----------|---------|---------------|-------|
| GPT-5.2 reviewer | LLM-as-judge | $0.01–0.10 | 500–2000ms | No | Semantic + Structural |
| RewardHackWatch | ML + Regex + AST | GPU required | varies | No | Trajectory-level |
| **ast-guard v2.0** | **Pure AST + heuristics** | **$0.00** | **<10ms** | **Yes** | **Structural only** |

The 4.7ms mean scan time means ast-guard adds imperceptible latency to any execution loop. A human blink takes 150–400ms. An HTTP round-trip takes 50–200ms. ast-guard is faster than either, which means it can gate every single code execution in real time without degrading agent performance.

---

## How It Works

ast-guard parses code into an Abstract Syntax Tree and evaluates structural properties. No execution, no sampling, no probabilistic inference. The same input always produces the same output.

### Six Checks

**Check 1 — Hardcoding Detection:** Catches if/else chains, dictionary lookup tables, and compressed data strings that replace real computation. Detects relative increases in if-counts and literal counts, filtered by guard-clause exclusions and dual-threshold conditions to suppress false positives on small functions.

**Check 2 — Complexity Collapse:** Measures per-function cyclomatic complexity (McCabe metric). Flags when a function's complexity drops by more than 60% without a recognized legitimate optimization. Per-function analysis prevents hiding a collapsed function behind high-complexity siblings.

**Check 3 — Forbidden Calls and Obfuscation:** Diff-based detection of newly introduced dangerous calls — eval, exec, subprocess, ctypes, sys.exit, and more. Includes multi-level alias resolution (chained assignments, tuple unpacking, dict dispatch), chr()-based obfuscation, and builtins access patterns.

**Check 4 — Import Drift:** Detects new imports that weren't in the original code. Blocklisted imports (os, sys, subprocess, pickle, importlib) trigger CRITICAL. Unknown imports trigger WARNING for manual review. Both lists are configurable.

**Check 5 — Extensional Enumeration:** Catches the RLVR shortcut documented by Helff et al. — models that abandon rule induction and enumerate all known input/output pairs as flat if/elif chains or match/case blocks instead of solving the problem.

**Check 6 — Behavioral Risk Scoring (Standalone Mode):** An additive risk scoring engine inspired by YARA and Semgrep. Each code block accumulates a risk score based on detected patterns. Score thresholds determine verdict. Patterns include test file manipulation, monkey-patching, stack introspection, timer manipulation, dunder method hijacking, process termination tricks, sandbox escape attempts, and more. Legitimate agent behavior (writing output files, reading data, subprocess for compilation) is explicitly excluded via contextual allowlisting and constant propagation.

### Verdict Logic

```
CLEAN    → score below threshold, no blocklist triggers
WARNING  → suspicious patterns, manual review recommended
CRITICAL → high-confidence structural hack, block execution
```

In strict mode, CRITICAL blocks execution. In standard mode, everything is logged. In audit mode, silent collection only.

---

## Quickstart

**Requirements:** Python 3.11+ — zero external dependencies for Python analysis.

```bash
git clone https://github.com/Nick-is-building/ast-guard.git
cd ast-guard
python -m pytest tests/ -v  # 316 tests
```

### Python API

```python
from ast_guard import scan, scan_standalone

# Pair mode: compare original vs generated code
result = scan(original_code, generated_code, mode="strict")

if result["verdict"] == "CRITICAL":
    print("Blocked: structural hack detected.")
    print(result["checks"])  # per-check findings
elif result["verdict"] == "WARNING":
    print("Suspicious. Review recommended.")
else:
    print("Clean. Safe to execute.")

# Standalone mode: analyze a single agent output without baseline
result = scan_standalone(agent_code)
print(result["verdict"])
print(result["checks"]["check_6_behavioral"]["risk_score"])
```

### CLI

```bash
# Standard mode — log everything, block nothing
python -m ast_guard.cli check original.py generated.py

# Strict mode — block on CRITICAL
python -m ast_guard.cli check original.py generated.py --mode strict

# Audit mode — silent telemetry only
python -m ast_guard.cli check original.py generated.py --mode audit

# JSON output for pipelines
python -m ast_guard.cli check original.py generated.py --json
```

### CI/CD Gate

Exit code 0 on CLEAN/WARNING, exit code 1 on CRITICAL:

```bash
python -m ast_guard.cli check original.py generated.py --mode strict --json || exit 1
```

---

## Multi-Language Support

ast-guard natively supports Python with zero dependencies. Bash and JavaScript analysis is available via tree-sitter as an optional extra.

```bash
pip install ast-guard[multilang]
```

| Language | Dependency | Detects |
|----------|------------|---------|
| Python | None (native ast) | All 6 checks |
| Bash | tree-sitter-bash | Dangerous calls (curl, wget, eval, rm, chmod), PATH manipulation, LD_PRELOAD |
| JavaScript | tree-sitter-javascript | eval, Function(), require('child_process'), execSync, dangerous imports |

Language is auto-detected via shebang, keywords, and syntax patterns. The same scan pipeline runs regardless of language.

---

## Integration

### MCP Server

ast-guard includes a built-in [Model Context Protocol](https://modelcontextprotocol.io/) server for direct integration with coding agents.

```bash
pip install ast-guard[mcp]
```

**Claude Code** (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "ast-guard": {
      "command": "ast-guard-mcp",
      "type": "stdio"
    }
  }
}
```

**Cursor** (`.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "ast-guard": {
      "command": "ast-guard-mcp",
      "type": "stdio"
    }
  }
}
```

| MCP Tool | Description |
|----------|-------------|
| `ast_guard_scan` | Compare original vs generated code. Returns verdict, per-check findings, and detected transformations. |
| `ast_guard_feedback` | Submit feedback on scan results to improve detection thresholds. |

### GitHub Action

```yaml
name: ast-guard
on: [pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/ast-guard
        with:
          original: path/to/original.py
          generated: path/to/generated.py
          mode: strict
          upload-sarif: "true"
```

SARIF output is compatible with the GitHub Security Tab and VS Code.

---

## Evaluation

Full scientific documentation lives in the benchmarks directory:

[benchmarks/RESULTS.md](benchmarks/RESULTS.md) — precision, recall, F1, confusion matrices, comparison table across all datasets.

[benchmarks/METHODOLOGY.md](benchmarks/METHODOLOGY.md) — the complete 6-iteration calibration history showing how standalone mode was tuned from 95% false positive rate to 15.8%, with rationale for every decision. This serves as an ablation study.

[benchmarks/structural_benchmark/](benchmarks/structural_benchmark/) — 36 curated ground-truth code pairs across 12 structural hack categories. 100% F1, 4.7ms mean scan time. Fully reproducible.

Reproduce all results:

```bash
# Run the curated structural benchmark
python -m benchmarks.run_benchmark --benchmark structural

# Run against MALT (requires downloaded dataset)
python -m benchmarks.run_benchmark --benchmark malt --mode strict

# Run all available benchmarks
python -m benchmarks.run_benchmark --benchmark all
```

---

## Configuration

All thresholds, blocklists, and allowlists are configurable via TOML. Config hierarchy: CLI args > project config (`.ast-guard.toml`) > user config (`~/.ast-guard/config.toml`) > defaults.

```toml
# .ast-guard.toml
[thresholds]
if_count_rel_increase = 0.50
literal_count_rel_increase = 2.0
literal_count_abs_min = 10
long_string_len = 200
complexity_rel_decrease = 0.60
complexity_abs_min = 5
enumeration_ratio = 0.70
enumeration_min_ifs = 5

[imports]
blocklist = ["os", "sys", "subprocess", "pickle", "importlib"]
allowlist = ["functools", "itertools", "collections", "math"]

[settings]
mode = "standard"
telemetry = false
```

---

## Design Principles

**Deterministic.** No LLM, no randomness. Same input always produces the same output. No network calls in the scan path.

**Zero dependencies.** The Python core requires only the standard library. Clone the repo and it runs.

**Real-time.** At under 10ms per scan, ast-guard adds imperceptible latency to any execution loop. It can gate every code execution without degrading agent performance.

**Complementary by design.** Structural analysis and semantic analysis are separate concerns. ast-guard handles structural integrity completely, leaving LLM reviewers to do what they do best.

**Privacy-by-design.** Telemetry stores only anonymized AST metrics — never code, filenames, paths, or timestamps. Everything is stored locally. Sharing is always opt-in.

**Adoption-friendly.** Three modes (audit → standard → strict) enable risk-free evaluation before commitment. Run in audit mode for a week, review the data, then decide.

---

## Known Limitations

**Standalone mode has lower precision than pair mode.** Without a baseline, contextual disambiguation is harder. The 15.8% false positive rate on normal MALT samples is the current calibration point — intentionally conservative to avoid missing real hacks. For context, industry SAST tools such as CodeQL and Infer report false alarm rates exceeding 95% on large codebases (Du et al., arXiv:2601.18844), making ast-guard's 15.8% FPR competitive for a zero-cost deterministic layer.

**Semantic hacks are outside scope by design.** Code that is structurally normal but logically wrong, produces subtly incorrect results, or games a task specification without a structural trace requires semantic understanding. This is the job of LLM-based reviewers and downstream test suites. ast-guard and semantic reviewers are meant to work together.

**Bash and JavaScript adapters are less mature than the Python core.** The pattern coverage is narrower and the false positive calibration is less refined.

**Thresholds are empirically calibrated on MALT but will improve with community data.** The defaults are informed starting points, not final optima.

---

## Future Direction

ast-guard currently operates on code. The deeper research question is whether deterministic static analysis can be extended to all structured LLM outputs — SQL queries, JSON responses, YAML configurations, API call sequences, tool-use traces. Any structured output can be manipulated. Any structured output has analyzable structural properties that can be evaluated before that output takes effect. Extending the pre-execution gate concept beyond code is an open research problem. If you are working on LLM safety, evaluation integrity, or agentic systems and want to explore this direction, collaboration is welcome. Evaluation against the Reward Hacking Benchmark (RHB; Thaman et al. 2026, arXiv:2605.02964) chained tool-use tasks is planned as a next step to measure ast-guard's coverage on multi-step agentic exploit sequences.

---

## Related Work

**TRACE** (Deshpande et al. 2026, [arXiv:2601.20103](https://arxiv.org/abs/2601.20103)) — 54-category reward hacking taxonomy and benchmark. ast-guard covers 15-16 structural categories with 95.7% F1; the remaining categories are semantic and outside static analysis scope.

**MALT** (METR 2025) — 10,919 manually reviewed agent transcripts covering natural and prompted reward hacking behaviors. The largest labeled dataset in the field. ast-guard evaluates against 81,515 extracted code blocks.

**Helff et al.** ([arXiv:2604.15149](https://arxiv.org/abs/2604.15149)) — Documents extensional enumeration shortcuts in RLVR-trained models. Directly motivates Check 5.

**RewardHackWatch** — Runtime detector using DistilBERT + 45 regex patterns + AST analysis. 89.7% F1 on 5,391 trajectories. ML-based, trajectory-level. ast-guard is its deterministic structural complement.

**MacDiarmid et al.** ([arXiv:2511.18397](https://arxiv.org/abs/2511.18397)) — Demonstrates that reward hacking in production RL generalizes to alignment faking and sabotage. Establishes the safety stakes for detection.

**Baker et al. / OpenAI** ([arXiv:2503.11926](https://arxiv.org/abs/2503.11926)) — Chain-of-thought monitoring for reasoning models. Shows that optimization pressure against visible bad reasoning causes models to hide intent rather than change behavior — strengthening the case for structural analysis that cannot be deceived by reasoning traces.

**Wang et al.** (2025, [arXiv:2510.01367](https://arxiv.org/abs/2510.01367), "Is It Thinking or Cheating?") — Introduces a different TRACE acronym: reasoning-effort-based detection of chain-of-thought monitoring evasion. Not to be confused with the TRACE reward-hacking taxonomy and benchmark from Deshpande et al. 2026 that ast-guard evaluates against.

**Reward Hacking Benchmark / RHB** (Thaman et al. 2026, [arXiv:2605.02964](https://arxiv.org/abs/2605.02964)) — Multi-step tool-use benchmark across 13 frontier models with exploit rates ranging from 0 to 13.9%. ast-guard plans to evaluate against RHB in a future release to measure coverage on chained agentic exploit sequences.

---

## Citation

```bibtex
@software{ast_guard_2026,
  title  = {ast-guard: Pre-Execution Gate for AI-Generated Code},
  author = {Nick},
  year   = {2026},
  url    = {https://github.com/Nick-is-building/ast-guard},
  version = {2.0.0}
}
```

---

## Project Structure

```
ast-guard/
├── ast_guard/
│   ├── __init__.py           # Public API: scan(), scan_standalone(), feedback()
│   ├── analyzer.py           # AST parsing and metric extraction
│   ├── checks.py             # Checks 1–5
│   ├── check_behavioral.py   # Check 6: behavioral risk scoring
│   ├── allowlist.py          # Legitimate transformation detection
│   ├── confidence.py         # Confidence score (0-100) for triage workflows
│   ├── taint.py              # Intra-file taint tracking for cross-function bypasses
│   ├── lang_bash.py          # Bash adapter (tree-sitter)
│   ├── lang_javascript.py    # JavaScript adapter (tree-sitter)
│   ├── multilang.py          # Language detection and dispatch
│   ├── config.py             # Configuration, defaults, modes
│   ├── telemetry.py          # Scan ID, salt, JSONL, feedback, export
│   ├── output.py             # CLI formatting (ANSI) and JSON serialization
│   └── mcp_server.py         # MCP server
├── benchmarks/
│   ├── RESULTS.md            # Full scientific evaluation results
│   ├── METHODOLOGY.md        # Calibration history and reproducibility
│   ├── structural_benchmark/ # 36 curated ground-truth samples, 100% F1
│   ├── loaders/              # Dataset loaders (MALT, TRACE, Countdown-Code, etc.)
│   └── run_benchmark.py      # Benchmark runner
├── tests/                    # 316 tests across all modules
├── examples/                 # Five annotated code pair examples
├── cli.py                    # CLI entry point
├── ALLOWLIST.md              # Documented rationales for legitimate transformations
├── CHANGELOG.md              # Full version history
└── pyproject.toml
```

---

*ast-guard is actively developed. New benchmark evaluations, language adapters, and detection patterns are added as the research landscape evolves.*
