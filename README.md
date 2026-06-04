# ast-guard

**Pre-Execution Gate for AI-Generated Code**

*The deterministic layer between LLM code generation and code execution. No LLM. No ML. No cost.*

[![Tests](https://github.com/Nick-is-building/ast-guard/actions/workflows/tests.yml/badge.svg)](https://github.com/Nick-is-building/ast-guard/actions/workflows/tests.yml) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/Nick-is-building/ast-guard/blob/main/LICENSE)

---

## What ast-guard Is

ast-guard sits between code generation and execution. It parses LLM-generated code into an AST and returns a deterministic verdict before any line runs. It is not a linter, not a security scanner, and not a sandbox — it is a deterministic structural check that cannot be talked into compliance and is not deceivable by a model's reasoning trace.

Two existing defense classes leave a gap:

- **Training-time alignment** (Anthropic, DeepMind) reduces incidence, not residual.
- **Inference-time LLM reviewers** (TRACE, RewardHackWatch, EvilGenie) share failure modes with the generator they monitor.

ast-guard is built as a deterministic third layer alongside those defenses. Today it reliably catches the structurally obvious bypasses at zero per-scan cost (see [Key Results](#key-results)); the active development direction is to broaden structural coverage over time, so semantic reviewers can concentrate on what only they can do — judging intent and meaning.

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
```

Two modes:

- **Pair Mode** — compares original code against LLM-generated code. Detects structural deviations.
- **Standalone Mode** — analyzes a single agent output with no baseline. Uses behavioral risk scoring.

---

## Key Results

All results are fully reproducible. See [benchmarks/RESULTS.md](benchmarks/RESULTS.md) for full methodology, confusion matrices, and per-category breakdowns.

| Benchmark | Mode | Samples | Key Metric | Value |
|-----------|------|---------|------------|-------|
| Structural Benchmark (curated ground-truth pairs) | Pair | 36 | F1 | **100%** |
| TRACE taxonomy (Deshpande et al. 2026) | Pair | 33 | F1 | **95.7%** |
| School of Reward Hacks (longtermrisk) | Pair | 26 | Recall | **96.2%** |
| Countdown-Code (Khan et al.) | Pair | 15,894 | True Negative Rate | **99.0%** |
| MALT (METR, 81,515 agent code blocks) | Standalone | 81,515 | Specificity† | **84.2%** |
| MALT — `hardcoded_solution` | Standalone | 429 | Detection Rate | **70.9%** |
| MALT — `bypass_constraints` | Standalone | 2,379 | Detection Rate | **41.7%** |

† TNR measured on the `normal` label only (77,369 samples); see [RESULTS.md](benchmarks/RESULTS.md) for the full confusion matrix.

### Comparison with Existing Approaches

These approaches are complementary, not competing. ast-guard handles structural analysis; LLM reviewers handle semantics.

| Approach | Method | Cost/scan | Latency | Deterministic | Scope |
|----------|--------|-----------|---------|---------------|-------|
| GPT-4o reviewer | LLM-as-judge | $0.01–0.10 | 500–2000ms | No | Semantic + Structural |
| RewardHackWatch | ML + Regex + AST | GPU required | varies | No | Trajectory-level |
| **ast-guard v2.0** | **Pure AST + heuristics** | **$0.00** | **<10ms** | **Yes** | **Structural only** |

---

## How It Works

ast-guard parses code into an Abstract Syntax Tree and evaluates structural properties. No execution, no sampling, no probabilistic inference.

### Six Checks

1. **Hardcoding Detection** — if-counts, literal counts, long-string growth vs. baseline. Guard-clauses excluded.
2. **Complexity Collapse** — per-function McCabe complexity drop >60% without a recognized legitimate optimization.
3. **Forbidden Calls & Obfuscation** — diff-based detection of new `eval`/`exec`/`subprocess`/`ctypes`/`SystemExit` calls, alias resolution, `chr()`-obfuscation, builtins subscript.
4. **Import Drift** — new imports against blocklist (CRITICAL) and safelist (CLEAN). Unknown imports → WARNING.
5. **Extensional Enumeration** — the RLVR shortcut documented by Helff et al.: flat if/elif or match/case chains covering ≥70% of branches with no loops.
6. **Behavioral Risk Scoring** (standalone only) — additive YARA/Semgrep-style score from AST patterns. CLEAN <30, WARNING 30–69, CRITICAL ≥70.

### Verdict Logic

```
CLEAN    → score below threshold, no blocklist triggers
WARNING  → suspicious patterns, manual review recommended
CRITICAL → high-confidence structural hack, block execution
```

Modes: `strict` blocks CRITICAL; `standard` logs everything; `audit` silent collection only.

---

## Quickstart

**Requirements:** Python 3.11+. Zero external dependencies for Python analysis.

```bash
git clone https://github.com/Nick-is-building/ast-guard.git
cd ast-guard
python -m pytest tests/ -q
```

### Python API

```python
from ast_guard import scan, scan_standalone

result = scan(original_code, generated_code, mode="strict")

if result["verdict"] == "CRITICAL":
    print("Blocked: structural hack detected.")
    print(result["checks"])
elif result["verdict"] == "WARNING":
    print("Suspicious. Review recommended.")

# Standalone: single agent output, no baseline
result = scan_standalone(agent_code)
print(result["verdict"], result["checks"]["check_6_behavioral"]["risk_score"])
```

### CLI

```bash
python -m ast_guard.cli check original.py generated.py            # standard
python -m ast_guard.cli check original.py generated.py --mode strict
python -m ast_guard.cli check original.py generated.py --json     # for pipelines
```

Exit code 0 on CLEAN/WARNING, exit code 1 on CRITICAL — drop-in for CI gates.

---

## Multi-Language Support

Python is native (zero deps). Bash and JavaScript are available via tree-sitter as an optional extra.

```bash
pip install ast-guard[multilang]
```

| Language | Backend | Detects |
|----------|---------|---------|
| Python | Native `ast` | All 6 checks |
| Bash | tree-sitter-bash | Dangerous calls (curl, wget, eval, rm, chmod), PATH manipulation, LD_PRELOAD |
| JavaScript | tree-sitter-javascript | eval, Function(), require('child_process'), execSync |

Bash and JS adapters are preview-quality: narrower pattern coverage than the Python core.

---

## Integration

### MCP Server

ast-guard includes a built-in [Model Context Protocol](https://modelcontextprotocol.io/) server.

```bash
pip install ast-guard[mcp]
```

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

Tools: `ast_guard_scan` (compare original vs. generated), `ast_guard_feedback` (submit triage feedback).

### GitHub Action

```yaml
- uses: ./.github/actions/ast-guard
  with:
    original: path/to/original.py
    generated: path/to/generated.py
    mode: strict
    upload-sarif: "true"
```

SARIF output is compatible with the GitHub Security Tab.

---

## Configuration

Thresholds, blocklists, and allowlists are configurable via TOML. Hierarchy: CLI args > `.ast-guard.toml` > `~/.ast-guard/config.toml` > defaults.

```toml
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

- **Deterministic.** Same input → same verdict. No randomness, no network calls.
- **Zero dependencies in core.** Python standard library only.
- **Real-time.** <10ms per scan, no degradation to the execution loop.
- **Complementary by design.** Structural analysis is one layer; semantic review is another.
- **Privacy-by-design.** Telemetry stores anonymized AST metrics only — never code, filenames, paths, or timestamps. Always opt-in.
- **Three modes** (`audit` → `standard` → `strict`) enable risk-free evaluation before commitment.

---

## Known Limitations

- **Standalone precision is lower than pair mode** by design. Without a baseline, contextual disambiguation is harder. The MALT false-positive rate on `normal` samples is the current calibration point — intentionally conservative.
- **Semantic hacks are outside scope.** Code that is structurally normal but logically wrong, or that games a task specification without a structural trace, requires semantic understanding. That is the job of LLM-based reviewers and downstream test suites.
- **Bash and JavaScript adapters are less mature than the Python core.** Pattern coverage is narrower; false-positive calibration is less refined.
- **Thresholds are empirically calibrated.** Defaults are informed starting points, not final optima. See [METHODOLOGY.md](benchmarks/METHODOLOGY.md) for the full iteration history.

---

## Evaluation

- [benchmarks/RESULTS.md](benchmarks/RESULTS.md) — precision, recall, F1, confusion matrices across all datasets.
- [benchmarks/METHODOLOGY.md](benchmarks/METHODOLOGY.md) — the 6-iteration calibration history, including regressions.
- [benchmarks/structural_benchmark/](benchmarks/structural_benchmark/) — 36 curated ground-truth pairs across 12 structural hack categories.

Reproduce:

```bash
python -m benchmarks.run_benchmark --benchmark structural
python -m benchmarks.run_benchmark --benchmark all
# MALT requires the dataset at ~/.ast-guard/benchmarks/malt-public/
python -m benchmarks.run_benchmark --benchmark malt --mode strict
```

---

## Related Work

- **TRACE** (Deshpande et al. 2026, [arXiv:2601.20103](https://arxiv.org/abs/2601.20103)) — 54-category reward-hacking taxonomy. ast-guard covers 15 structural categories at 95.7% F1; the remainder are semantic.
- **MALT** (METR 2025) — 10,919 manually reviewed agent transcripts, 81,515 extracted code blocks. The largest labeled dataset in the field.
- **Helff et al.** ([arXiv:2604.15149](https://arxiv.org/abs/2604.15149)) — Extensional enumeration shortcuts in RLVR-trained models. Directly motivates Check 5.
- **RewardHackWatch** — Runtime detector combining ML + regex + AST. ast-guard is its deterministic structural complement.
- **EvilGenie** — Inference-time LLM reviewer; one of ast-guard's benchmark loaders.
- **ZeroFalse** ([arXiv:2510.02534](https://arxiv.org/abs/2510.02534)) — Calibrated confidence levels for static-analysis findings. Motivates ast-guard's confidence-score module (`ast_guard/confidence.py`).

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

*ast-guard is actively developed. See [CHANGELOG.md](CHANGELOG.md) for version history and [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.*
