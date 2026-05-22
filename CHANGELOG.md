# CHANGELOG.md - ast-guard v1.0

## [1.0.0] - 2026-05-21

### Added
- **Core Analyzer (`analyzer.py`)**: Structured AST-based metric extraction, cyclomatic complexity calculations (McCabe, including `match-case`), loops depth, literal counts, guard clause classification, import and call tracking.
- **Allowlist (`allowlist.py`)**: Code transformation pattern matchers for Loop-to-Comprehension, Functional Built-ins, Data Structure Swap, and Standard Library usage. Includes the flag-override-logic.
- **Checks (`checks.py`)**: Implementing the four security analyses:
  - Check 1: Hardcoding Detection (If-Count, Literal-Count, Long Strings).
  - Check 2: Complexity Collapse (with binary override and wash-protection).
  - Check 3: Forbidden Calls and Anti-Obfuscation (diff-based call verification, assignment tracking, built-ins subscripts, getattr-block, eval/exec catch-all, chr-heuristics).
  - Check 4: Import Drift (blocklist, allowlist, and unknown warnings).
- **Config (`config.py`)**: Hierarchical loading logic (CLI > Project > User > Defaults) supporting native TOML via Python's `tomllib`.
- **Telemetry (`telemetry.py`)**: Anonymized local telemetry writing to JSONL, Machine Salt initialization, `scan_id` generation, `metrics_fingerprint` clustering, feedback submissions, and sharing prompt heuristics.
- **Output (`output.py`)**: Built-in human-readable ANSI output styling and structured SARIF-compatible JSON formatter.
- **CLI (`cli.py`)**: Entry point supporting `check`, `feedback`, `export`, and `stats` subcommands.
- **Test Suite**: Comprehensive set of 35 tests validating all metrics, checks, overrides, telemetry, and integration flows under `tests/`.
- **Documentation**: Inline explanations, detailed `ALLOWLIST.md`, and complete setup guide in `README.md`.
