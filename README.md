# ast-guard

**Deterministic reward hacking detector for LLM-generated Python code.**

When LLMs autonomously generate and test code, they cheat. They hardcode expected outputs, replace algorithms with lookup tables, or manipulate test environments — and pass every test while solving nothing. Unit tests catch *whether* code works. ast-guard catches *how* it works.

ast-guard analyzes Python code structurally via the Abstract Syntax Tree (AST) before execution. No LLM, no machine learning, no external dependencies. Pure deterministic static analysis, 100% reproducible, zero hallucination risk.

---

## Why This Exists

Current approaches to detecting reward hacking in LLM-generated code either rely on another LLM to review the output (expensive, slow, hallucinates) or only check if tests pass (misses structural cheating entirely). Research benchmarks like TRACE and EvilGenie achieve at best 63% detection rate using LLM-based reviewers.

ast-guard opens a third path: **deterministic static analysis at runtime**. Complementary to training-level defenses (DeepMind, Anthropic) and LLM-based review, not competing.

---

## Quickstart

**Requirements:** Python 3.11+ — no pip install needed, zero dependencies.

```bash
git clone https://github.com/Nick-is-building/ast-guard.git
cd ast-guard
python -m pytest tests/ -v  # Run all 35 tests
```

### CLI Usage

```bash
# Standard mode (default for CLI — warnings only, no blocking)
python -m ast_guard.cli check original.py optimized.py

# Strict mode (blocks on CRITICAL — for autonomous agents)
python -m ast_guard.cli check original.py optimized.py --mode strict

# Audit mode (silent — only collects telemetry, zero impact)
python -m ast_guard.cli check original.py optimized.py --mode audit

# JSON output for pipeline integration
python -m ast_guard.cli check original.py optimized.py --json

# Disable telemetry for a single scan
python -m ast_guard.cli check original.py optimized.py --no-telemetry
```

### Python API

```python
from ast_guard import scan, feedback

result = scan(original_code, generated_code, mode="strict")

if result["verdict"] == "CRITICAL":
    print("Blocked: Likely reward hacking detected.")
elif result["verdict"] == "WARNING":
    print("Suspicious patterns found. Review recommended.")
else:
    print("Clean. Safe to execute and test.")

# Provide feedback to improve future calibration
feedback(result["telemetry"]["scan_id"], "correct")
```

---

## The Four Checks

### Check 1 — Hardcoding Detection
Catches LLMs that replace algorithms with hardcoded if/else chains, dictionary lookup tables, or compressed data strings.

- **If-Count:** Flags when if-statements increase by >50% while loop depth stays flat or drops.
- **Literal-Count:** Flags when literals increase by >200% AND at least 10 new literals appear.
- **Long Strings:** Flags new strings >200 characters (catches compressed lookup data like `"1:1|2:1|3:2|..."`).
- **Guard Clause Awareness:** Early returns at the top of functions are correctly excluded.

Severity: WARNING (CRITICAL when combined with Check 2).

### Check 2 — Complexity Collapse
Catches sudden, unexplained drops in cyclomatic complexity (McCabe metric).

- Flags when complexity drops by >60%.
- **Allowlist Override:** If the drop is explained by legitimate patterns (list comprehension replacing a loop, `sorted()` replacing hand-written sort), the warning is suppressed.
- **Anti-Washing Protection:** The override is blocked if Check 1 or Check 3 fire simultaneously — a single `map()` cannot whitewash a hardcoded function.

Severity: WARNING (CRITICAL when combined with Check 1).

### Check 3 — Forbidden Calls & Obfuscation
Catches dangerous system calls and obfuscation attempts. **Diff-based:** only flags calls that are *new* in the generated code.

- **Blocklist:** `eval`, `exec`, `os.*`, `sys.*`, `subprocess.*`, `open`, `__import__`, `compile`, and more.
- **Anti-Obfuscation:** Detects variable aliasing (`f = eval; f(...)`), `__builtins__` subscript/attribute access, `getattr(__builtins__, ...)`, and `chr()` character code tricks inside eval/exec/import calls.

Severity: Always CRITICAL, in all modes.

### Check 4 — Import Drift
Catches new imports that weren't in the original code.

- **Blocklist (CRITICAL):** `os`, `sys`, `subprocess`, `pickle`, `importlib`, `ctypes`, and other system modules.
- **Allowlist (CLEAN):** `functools`, `itertools`, `collections`, `math`, `typing`, and other standard optimization imports.
- **Unknown imports:** WARNING for manual review.

---

## Three Sensitivity Modes

| Mode | Default For | Behavior |
|------|-------------|----------|
| **strict** | Python API | CRITICAL blocks execution. Full gatekeeper. |
| **standard** | CLI | CRITICALs downgraded to WARNINGs (except Check 3). Nothing blocked. |
| **audit** | — | Silent. No output, no blocking. Only telemetry collection. |

The audit mode is designed for risk-free evaluation: run ast-guard silently for a week, review the telemetry, then decide whether to enable standard or strict.

---

## Telemetry & Community Data

ast-guard collects **only anonymized metrics** — never code, filenames, paths, or timestamps.

Each scan produces two identifiers:
- **scan_id:** Stable hash of original + generated code + local machine salt. Enables reliable feedback across sessions. Never exported.
- **metrics_fingerprint:** Hash of AST metrics, node type distributions, and builtin names. Enables pattern clustering in the community dataset without exposing code.

```bash
# View local statistics
python -m ast_guard.cli stats

# Export anonymized data for community sharing
python -m ast_guard.cli export --output my_data.jsonl

# Provide feedback on a scan
python -m ast_guard.cli feedback --id <scan-id> --label correct
```

### Community Dataset
We are building the world's first empirical dataset of AST metrics for reward hacking detection. When you reach 100 scans, ast-guard will suggest exporting your anonymized data. Contributions help calibrate thresholds for everyone.

---

## Recognized Legitimate Transformations

ast-guard doesn't just flag — it understands. These patterns are recognized as legitimate and documented in [ALLOWLIST.md](ALLOWLIST.md):

- **Loop → Comprehension:** `for` loops replaced by list/set/dict comprehensions
- **Functional Built-ins:** Loops replaced by `map()`, `filter()`, `sorted()`, `min()`, `max()`, `sum()`
- **Data Structure Swap:** Lists replaced by sets for O(1) membership testing
- **Standard Library Usage:** New imports from `functools`, `itertools`, `collections`, etc.

---

## Configuration

All thresholds, blocklists, and allowlists are configurable via TOML:

```toml
# .ast-guard.toml (in your project directory)
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

## Known Limitations (v1.0)

- **Python only.** Multi-language support (via tree-sitter) planned for v2.0.
- **No constant folding.** `eval("ex" + "ec")` is caught by the eval catch-all, but arbitrary string concatenation in import arguments is not resolved. Planned for v1.2.
- **No semantic analysis.** ast-guard checks structure, not meaning. Semantically incorrect code is the job of your test suite.
- **Thresholds are starting points.** Defaults are informed estimates, not empirically validated optima. Community telemetry will improve them over time.

---

## Roadmap

| Version | Feature |
|---------|---------|
| v1.1 | SARIF output for GitHub Security Tab and CI/CD integration |
| v1.2 | Extended obfuscation detection (constant folding for string concatenation) |
| v1.3 | First community-data-driven threshold calibration |
| v2.0 | Multi-language support via tree-sitter (JavaScript, TypeScript, Go) |

---

## Project Structure

```
ast-guard/
├── ast_guard/
│   ├── __init__.py      # Public API: scan(), feedback()
│   ├── analyzer.py      # AST parsing and metric extraction
│   ├── checks.py        # The four core checks
│   ├── allowlist.py     # Legitimate transformation detection
│   ├── config.py        # Configuration loading (TOML)
│   ├── telemetry.py     # Anonymized telemetry system
│   ├── output.py        # CLI (ANSI) and JSON formatting
│   └── cli.py           # CLI entry point
├── tests/               # 35 tests covering all modules
├── ALLOWLIST.md          # Documented transformation rationales
├── CHANGELOG.md
├── LICENSE              # MIT
├── pyproject.toml
└── README.md
```

---

## License

MIT — use it, fork it, improve it, ship it.

---

*Built by [Nick](https://github.com/Nick-is-building) — Deterministic System Builder, Berlin.*
