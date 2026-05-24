# CHANGELOG.md - ast-guard

## [1.1.0] - 2026-05-24

### Added
- **MCP Server Support**: Native Model Context Protocol integration for Claude Code, Cursor, and other MCP-compatible agents
- **TRACE-based Benchmark**: Comprehensive evaluation against the TRACE taxonomy (Deshpande et al., 2026) with 30+ test samples
- **FailProofAI Integration**: Custom policy support for coding agent harnesses (integration proposal)
- **Examples Directory**: Real-world code samples demonstrating reward hacking detection and legitimate optimizations
- **E2E CI/CD Guide**: GitHub Actions workflow example for automated code integrity checks

### Fixed
- Version consistency between `pyproject.toml` (1.1.0) and CHANGELOG.md

---

## [1.0.0] - 2026-05-21

### Added
- **Core Analyzer (`analyzer.py`)**: Structured AST-based metric extraction, cyclomatic complexity calculations (McCabe, including `match-case`), loops depth, literal counts, guard clause classification
- **Allowlist (`allowlist.py`)**: Code transformation pattern matchers for Loop-to-Comprehension, Functional Built-ins, Data Structure Swap, and Standard Library usage. Includes the flag-override-logic and anti-washing protection
- **Checks (`checks.py`)**: Implementing the four security analyses:
  - Check 1: Hardcoding Detection (If-Count, Literal-Count, Long Strings).
  - Check 2: Complexity Collapse (with binary override and wash-protection).
  - Check 3: Forbidden Calls and Anti-Obfuscation (diff-based call verification, assignment tracking, built-ins subscripts, getattr-block, eval/exec catch-all, chr-heuristics).
  - Check 4: Import Drift (blocklist, allowlist, and unknown warnings).
- **Config (`config.py`)**: Hierarchical loading logic (CLI > Project > User > Defaults) supporting native TOML via Python's `tomllib`.
- **Telemetry (`telemetry.py`)**: Anonymized local telemetry writing to JSONL, Machine Salt initialization, `scan_id` generation, `metrics_fingerprint` clustering, feedback submissions, and sharing opt-in.
- **Output (`output.py`)**: Built-in human-readable ANSI output styling and structured SARIF-compatible JSON formatter.
- **CLI (`cli.py`)**: Entry point supporting `check`, `feedback`, `export`, and `stats` subcommands.
- **MCP Server (`mcp_server.py`)**: Built-in Model Context Protocol server for agent integration.
- **Test Suite**: Comprehensive set of 43 tests validating all metrics, checks, overrides, telemetry, and integration flows under `tests/`.
- **Documentation**: Inline explanations, detailed `ALLOWLIST.md`, and complete setup guide in `README.md`.
