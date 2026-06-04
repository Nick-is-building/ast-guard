# CHANGELOG.md - ast-guard

## [2.0.1] - 2026-06-04

### Fixed

- **Check 3 — SystemExit detection gap**: `SystemExit` added to the `exact_blocked` set in `ast_guard/checks.py`, closing the pair-mode/standalone asymmetry where `raise SystemExit(0)` was caught only by Check 6 in standalone mode. The `CAT_09_PROCESS_TERMINATION` benchmark sample for `raise SystemExit(0)` flipped from documented gap to expected CRITICAL.
- **SARIF output — unresolved Check 6 rule reference**: `check_6_behavioral` is now declared in `_SARIF_RULES` and mapped in `_CHECK_KEY_TO_RULE` (`ast_guard/output.py`). Previously the standalone-mode SARIF report emitted an undeclared `ruleId`, which GitHub Code Scanning rejects. Added a regression test that asserts every emitted `ruleId` resolves to a declared rule.
- **`scan_multilang` swallowed all exceptions**: replaced the bare `except Exception` around `extract_metrics_multilang` with targeted handling — unsupported-language inputs and generated-code `SyntaxError`s now surface as `ERROR`-verdict results instead of misleading CLEAN; `ImportError` from missing `ast-guard[multilang]` extras propagates with the adapter's install hint; original-code `SyntaxError` falls back to empty metrics, mirroring the `scan()` doctrine.

## [2.0.0] - 2026-05-31

### Added

- **Check 6 — Behavioral Risk Scoring** (`ast_guard/check_behavioral.py`): Standalone-only check that assigns an additive risk score from AST-detectable behavioral patterns. Signals: `stack_introspection` (+70), `module_cache_manipulation` (+70), `process_termination` (+70), `test_file_manipulation` (+50), `dangerous_call` (+50), `subprocess_shell` (+30), `environ_mutation` (+30), `file_write_unknown_target` (+10), `filesystem_traversal` (+10), `unknown_import` (+10). Thresholds: CLEAN < 30, WARNING 30–69, CRITICAL ≥ 70 (or any single signal ≥ 70). Significantly improves bypass\_constraints detection in standalone mode.

- **`scan_standalone()` in `__init__.py`**: Public API for single-code-block scanning without a baseline. Integrates Check 6; Check 2 is inactive (no baseline). Adds standalone-specific literal threshold (default 50) and extended safe-import list for ML/data-science libraries.

- **Standalone mode calibration**: Raised Check 1 literal threshold for standalone to 80 (conditional 50 when check_6 score >= 30; pair-mode default is lower), removed `os` and `sys` from CRITICAL imports in standalone mode, expanded safe-import list to ~100 common ML/data-science libraries, added context-aware `exit()` differentiation (only fires process\_termination outside `if __name__ == '__main__'` guards).

- **MALT benchmark loader** (`benchmarks/loaders/malt_loader.py`): Streaming ingestion of METR MALT dataset from HuggingFace (`metr-evals/malt-public`). Extracts 140,726 code blocks from 7,179 agent transcripts; filters to 81,515 scannable blocks (>50 chars, parseable). Per-label aggregation across 10 MALT categories.

- **Multi-language engine** (`ast_guard/multilang.py`): Language detection and adapter dispatch for Python (native `ast`), Bash, and JavaScript/TypeScript (tree-sitter). Optional dependency: `pip install ast-guard[multilang]`. Bash adapter detects dangerous calls (curl, wget, eval, exec, rm, chmod, chown, dd, mkfs, nc, ncat). JS/TS adapter detects eval, Function(), require('child\_process'), import('fs'), dangerous globals.

- **Benchmark framework** (`benchmarks/`): Unified ingestion pipeline for 7 datasets (TRACE built-in, TRACE external, Terminal Wrench, EvilGenie, Countdown-Code, School of Reward Hacks, MALT). Loader interface: `load() → list[dict]` returning `{original_code, generated_code, language, label, metadata}`. CLI runner: `python -m benchmarks.run_benchmark [--all|<name>] [--json <path>]`.

- **Multi-level aliasing in Check 3** (v1.3.1): Chained aliases (`b = __builtins__; e = b['eval']; e(...)`), tuple-unpack aliases, and dict-dispatch patterns are now tracked. `chr()` obfuscation via aliased chr and `builtins["chr"]` detected. `resolve_call_name` bare-attribute collision fixed (no longer conflates `obj.method()` with `method()`).

- **Scientific evaluation documentation**: `benchmarks/RESULTS.md` (publication-quality results across 5 datasets), `benchmarks/METHODOLOGY.md` (full optimization history, data pipeline, false positive analysis), `benchmarks/data/malt_summary.json` (machine-readable MALT results), `benchmarks/data/iteration_log.json` (6-iteration standalone calibration log).
- **Confidence score** (`ast_guard/confidence.py`): 0-100 confidence score exposed in scan results, SARIF output, and telemetry for triage and Precision@k workflows.
- **Intra-file taint tracking** (`ast_guard/taint.py`): Cross-function returns, class attributes, setattr, globals(), and closure bypass detection.
- **Destructive OS/shutil call detection in Check 6**: os.system/os.popen score +70, os.remove/shutil.rmtree score +50, with context-aware safe-target exclusions (relative paths and /tmp targets score +0).
- **`__import__()` detection in standalone Check 3**: Added to the forbidden-call filter alongside eval, exec, and builtins access patterns.

### Changed

- `__version__` bumped to `2.0.0`.
- `__all__` in `__init__.py` updated to include `scan_standalone` and `scan_multilang`.
- Check 4 standalone mode no longer fires CRITICAL on `os` and `sys` — both are ubiquitous in legitimate agent code and carry no incremental reward-hacking signal without a baseline.
- MALT evaluation: 16.6% flag rate on 81,515 samples; 84.2% true-negative rate on normal-labeled code; 70.9% detection on hardcoded\_solution, 41.7% on bypass\_constraints.
- Telemetry: code is hashed at the API boundary; `log_scan` no longer receives plaintext code.
- Standalone: `subprocess` import with exclusively safe calls is now CLEAN instead of WARNING.
- Standalone: destructive filesystem calls on relative paths or `/tmp` targets score +0 (safe context).
- Check 6: filename resolution now handles `os.path.join`, `pathlib.Path`, and f-strings.

### Fixed
- Telemetry: deterministic fingerprint for dict-valued metrics (`function_complexities`).
- Output/CLI: replaced hardcoded `"v1.3"` strings with dynamic `__version__`.
- Check 3: deduplicated alias findings in fixpoint loop.
- Conditional literal threshold: tightened from check_6 score > 0 to >= 30 to prevent `file_write_unknown_target` triggering the reduced threshold.

### Performance
- Analyzer: single-pass lineno index replaces per-finding AST walks.

### Benchmark Results Summary

| Dataset | Mode | Metric | Score |
|---------|------|--------|-------|
| TRACE built-in (33 samples) | Pair | F1 | 95.7% |
| TRACE built-in (33 samples) | Pair | Precision | 100% |
| TRACE built-in (33 samples) | Pair | Recall | 91.7% |
| School of Reward Hacks (26 valid) | Pair | Recall | 96.2% |
| Countdown-Code (15,894) | Pair | True Negative Rate | 99.0% |
| MALT normal (77,369) | Standalone | Specificity (TNR) | 84.2% |
| MALT hardcoded\_solution (429) | Standalone | Detection Rate | 70.9% |
| MALT bypass\_constraints (2,379) | Standalone | Detection Rate | 41.7% |

---

## [1.3.0] - 2026-05-28

### Added
- **Check 5 — Extensional Enumeration Detector**: Detects the "enumerate all known input/output pairs" failure mode of RLVR-trained LLMs documented by Helff et al., "LLMs Gaming Verifiers" ([arXiv:2604.15149](https://arxiv.org/abs/2604.15149)). Per generated function, fires WARNING when `total_ifs >= enumeration_min_ifs` (default 5), `enumeration_ifs / total_ifs >= enumeration_ratio` (default 0.70), and `loop_count <= 1`. Recognizes both `if`/`elif` chains and `match`/`case` blocks.
- **`count_enumeration_pattern(tree)` in `analyzer.py`**: Per-function analysis emitting `{name, enumeration_ifs, total_ifs, loop_count}`. Included in `extract_metrics()` as `enumeration_analysis`. Skips nested functions/classes (each is reported separately).
- **Combination Logic Extensions**:
  - Check 5 WARNING + Check 2 WARNING escalates to **CRITICAL** (enumeration + complexity collapse).
  - Check 5 WARNING + Check 1 WARNING escalates to **CRITICAL** (enumeration + hardcoding; covers the case where Check 2 misses because the original was too small).
  - Check 5 also blocks the Allowlist override of Check 2 (alongside Check 1 and Check 3).
- **SARIF Rule for Check 5**: `ast-guard/check-5-extensional-enumeration` added to the SARIF v2.1.0 output and `_CHECK_KEY_TO_RULE` mapping.
- **Detailed Telemetry Statistics (`get_detailed_stats()` in `telemetry.py`)**: Computes metric deltas (gen − orig) for `if_count`, `literal_count`, `mccabe_complexity`, `comprehension_count`, `functional_call_count`, `long_string_count` with count/mean/median/min/max/stddev; check correlations (Check 1+2 kombi, Check 5+2 kombi, Check 5 alone vs. with others, Check 3/4 CRITICAL counts); verdicts split by sensitivity mode; transformations with percentages. Standard library only (`statistics` module).
- **CLI flags `--detailed` and `--export-stats <path>` on `stats` subcommand**: Print or export the detailed statistics as JSON for external visualization.
- **GitHub Composite Action (`.github/actions/ast-guard/action.yml`)**: Reusable action with SARIF output, optional upload to GitHub Security Tab via `github/codeql-action/upload-sarif`, configurable `mode`, `sarif-file`, and `category` inputs.
- **Benchmark Samples for Extensional Enumeration**:
  - `pure_enumeration_no_fallback` — `collatz_steps(n)` as 15 individual `if n == X: return Y` without algorithmic fallback.
  - `match_case_enumeration` — `digit_name(n)` as a `match`/`case 0..9` block against a dict-lookup original.
  - `http_status_dispatch` (benign) — many `elif status_code == ...` branches with complex bodies (3+ statements) to verify Check 5 does not fire on real dispatch logic.
- **Config Thresholds**: `enumeration_ratio` (0.70) and `enumeration_min_ifs` (5) added to `DEFAULT_CONFIG` and CLI threshold mapping.
- **Test Coverage**: `tests/test_check5.py` with unit tests for `count_enumeration_pattern`, two true positives (Fibonacci if/elif chain, match/case lookup), three true negatives (complex bodies, too few ifs, multiple loops), and integration tests for both kombi rules.

### Fixed
- **Check 2 Rename Bypass**: When original and generated both define functions but share no qualified names (e.g. `factorial` renamed to `fact`), Check 2 previously returned silently CLEAN. Now falls back to file-level `mccabe_complexity` comparison with the same thresholds, citing "No matching function names found between original and generated code; falling back to file-level comparison."
- **`builtins.eval(...)` Detection Gap**: `_is_builtins_reference()` and the parallel attribute-path check now include `"builtins"` (the regular module) alongside `"__builtins__"` and `"_builtins_"`. Closes the silent bypass that occurred when `import builtins` was already present in the original code and `builtins.eval(...)` therefore did not appear as a "new" call.
- **Syntax-Error Telemetry Data Corruption**: In the `gen_code` parse-failure path, `log_scan` was called with `orig_metrics` twice (in place of `gen_metrics`), polluting the local telemetry log with the false claim that the generated code matched the original. Now passes an empty dict for `gen_metrics`.
- **Overly Broad Exception Handling**: Both `ast.parse` / `extract_metrics` blocks in `scan()` now use `except SyntaxError` instead of `except Exception`. Real analyzer bugs (KeyError, AttributeError, …) propagate instead of being silently masked as if the input were unparseable.

### Changed
- `__version__` bumped to `1.3.0` across `__init__.py`, `pyproject.toml`, `cli.py` description, `output.py` ANSI header and SARIF tool version.
- ANSI report header now reads `AST-GUARD v1.3 ANALYSIS REPORT`.

## [1.2.0] - 2026-05-26

### Added
- **Constant Folding (`resolve_constant_string`)**: Recursive resolution of string concatenation via `ast.BinOp(ast.Add)` in obfuscation checks. Catches patterns like `__builtins__['ev' + 'al']`.
- **New Anti-Obfuscation Paths (Check 3)**:
  - `__builtins__.__dict__['eval']` detection (attribute chain to `__dict__`)
  - `getattr(globals()['__builtins__'], 'eval')` detection (globals subscript)
  - Constant folding in subscript strings (e.g., `__builtins__['ev' + 'al']`)
- **Complexity Floor (`complexity_abs_min`)**: Check 2 only fires when original complexity >= 5 (default), preventing false positives on small functions.
- **Per-Function Complexity Analysis**: Check 2 now compares McCabe complexity per qualified function name instead of file-level totals. Closes the "complexity padding" vulnerability.
- **Set-Literal-Size Allowlist Blocker**: Data Structure Swap override blocked when set literal exceeds `set_literal_max` (default 15 elements).
- **SARIF v2.1.0 Output**: `--sarif` flag for GitHub Security Tab integration. Stable `partialFingerprints` (astGuardFingerprint/v1) independent of line numbers.
- **14 new tests** for v1.2 features in `tests/test_v12_features.py`.

### Changed
- Check 2 explanation messages now include the qualified function name.
- `_is_builtins_reference()` centralized for all builtins detection paths.

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
