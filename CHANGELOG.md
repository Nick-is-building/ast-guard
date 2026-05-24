# CHANGELOG.md - ast-guard

## [1.1.0] - 2026-05-24

### Added
- **MCP Server (`mcp_server.py`)**: Integrated Model Context Protocol server directly into ast-guard with two tools: `ast_guard_scan` and `ast_guard_feedback`. Installable as optional dependency via `pip install ast-guard[mcp]`. Entry point: `ast-guard-mcp` command.
- **MCP Test Suite**: 8 dedicated tests for the MCP server in `tests/test_mcp_server.py`.
- **TRACE Benchmark Suite (`benchmarks/`)**: 22 hacked samples across 14 TRACE subcategories and 8 clean/benign samples. CLI runner with `--json` and `--verbose` options. Results: 90.9% detection rate, 100% precision, 0% false positives.
- **TRACE Taxonomy Mapping**: Coverage of 15 out of 51 TRACE subcategories with documentation for why the remaining 36 are out of scope.
- **FailProofAI Integration**: Issue [#375](https://github.com/FailProofAI/failproofai/issues/375) opened with working policy prototype using PreToolUse hook. `deny()` on CRITICAL, `instruct()` on WARNING, `allow()` on CLEAN. Fail-open on errors.
- **GitHub Actions CI**: Automated testing across Python 3.11, 3.12, and 3.13.

### Changed
- **Full English Translation**: All German strings in code, comments, docstrings, and category names translated to English.
- **README.md**: Complete rewrite with benchmark results, MCP server documentation, FailProofAI integration section, design principles, related work, and updated roadmap.
- **ALLOWLIST.md**: Fully rewritten in English with updated category names (Loop to Comprehension, Functional Built-ins, Data Structure Swap, Standard Library Optimization).
- **Roadmap Updated**: v1.1 features marked complete; v1.2–v2.0 planned features added.

### Fixed
- `import builtins` moved from function scope to module scope in `telemetry.py`.
- SARIF comment in `output.py` corrected to "Serialize the full scan result dict".
- `pyproject.toml`: License format fixed from `{ text = "MIT" }` to `"MIT"` for Python 3.13 compatibility. Added authors, keywords, classifiers, and URLs.
- `__version__ = "1.1.0"` and `__all__` added to `__init__.py`.
- `tests/__init__.py` created.
- Test count corrected from 33 to 35.

## [1.0.0] - 2026-05-21

### Added
- **Core Analyzer (`analyzer.py`)**: Structured AST-based metric extraction, cyclomatic complexity calculations (McCabe, including `match-case`), loops depth, literal counts, guard clause classification, import and call tracking.
- **Allowlist (`allowlist.py`)**: Code transformation pattern matchers for Loop-to-Comprehension, Functional Built-ins, Data Structure Swap, and Standard Library usage. Includes the flag-override-logic.
- **Checks (`checks.py`)**: Implementing the four security analyses:
  * Check 1: Hardcoding Detection (If-Count, Literal-Count, Long Strings).
  * Check 2: Complexity Collapse (with binary override and wash-protection).
  * Check 3: Forbidden Calls and Anti-Obfuscation (diff-based call verification, assignment tracking, built-ins subscripts, getattr-block, eval/exec catch-all, chr-heuristics).
  * Check 4: Import Drift (blocklist, allowlist, and unknown warnings).
- **Config (`config.py`)**: Hierarchical loading logic (CLI > Project > User > Defaults) supporting native TOML via Python's `tomllib`.
- **Telemetry (`telemetry.py`)**: Anonymized local telemetry writing to JSONL, Machine Salt initialization, `scan_id` generation, `metrics_fingerprint` clustering, feedback submissions, and sharing prompt heuristics.
- **Output (`output.py`)**: Built-in human-readable ANSI output styling and structured SARIF-compatible JSON formatter.
- **CLI (`cli.py`)**: Entry point supporting `check`, `feedback`, `export`, and `stats` subcommands.
- **Test Suite**: Comprehensive set of 35 tests validating all metrics, checks, overrides, telemetry, and integration flows under `tests/`.
- **Documentation**: Inline explanations, detailed `ALLOWLIST.md`, and complete setup guide in `README.md`.
