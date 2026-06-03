# ast-guard Benchmark

Evaluates ast-guard against reward hacking patterns organized by the [TRACE taxonomy](https://arxiv.org/abs/2601.20103) (Deshpande et al., 2026).

## Run

```bash
python -m benchmarks.run_benchmark          # CLI report
python -m benchmarks.run_benchmark --json   # JSON output
python -m benchmarks.run_benchmark -v       # Verbose (show missed details)
```

## Current Results (v1.1.0)

| Metric | Value |
|--------|-------|
| Detection Rate | 90.9% (20/22 hacked samples detected) |
| Precision | 100.0% (0 false positives) |
| False Positive Rate | 0.0% (8/8 benign samples passed clean) |
| TRACE subcategories covered | 15/51 (29.4%) |
| Total samples | 30 (22 hacked + 8 benign) |

## Comparison with LLM-Based Detectors

| Detector | Detection Rate | Precision | Deterministic | Latency | Cost |
|----------|---------------|-----------|---------------|---------|------|
| **ast-guard** | **90.9%** (structural) | **100%** | **Yes** | **<50ms** | **$0** |
| GPT-5.2 (high reasoning) | 63% (all categories) | Not reported | No | ~10s | $$$ |
| Claude Opus 4.5* | 25% (all categories) | Not reported | No | ~10s | $$$ |

*Claude Opus 4.5 figure is illustrative — no verified primary source for this specific measurement.

Note: LLM detectors cover all 54 TRACE categories including semantic hacks. ast-guard covers 15 structural categories. The approaches are complementary — ast-guard as a fast pre-filter, LLM review for semantic depth.

---

## TRACE Coverage Breakdown

### Covered: 15 Subcategories (Structural)

ast-guard detects these via deterministic AST analysis — no LLM needed.

| TRACE Category | Subcategory | Samples | Detected By | Expected Verdict |
|---------------|-------------|---------|-------------|-----------------|
| Test Suite Exploitation | Hardcoded Outputs | 2 | Check 1 (If-Count + Literal-Count) | CRITICAL |
| Test Suite Exploitation | Input Recognition | 1 | Check 1 (If-Count) | CRITICAL |
| Test Suite Exploitation | Boundary Value Gaming | 1 | Check 1 (If-Count) | WARNING |
| Solution Quality Degradation | Lookup Tables | 1 | Check 1 (Literal-Count) + Check 2 | CRITICAL |
| Solution Quality Degradation | If-Else Explosion | 1 | Check 1 (If-Count) | CRITICAL |
| Solution Quality Degradation | Magic Number Hardcoding | 1 | Check 1 (If-Count) | WARNING |
| Solution Quality Degradation | String Concat Abuse | 1 | Check 1 (Long Strings) | WARNING |
| Solution Quality Degradation | Copy-Paste Replication | 1 | Check 1 (If-Count) | CRITICAL |
| Solution Quality Degradation | Complexity Gaming | 1 | Check 2 (Complexity Collapse) | CRITICAL |
| Execution Env. Hacks | Process Manipulation | 5 | Check 3 (eval/exec/chr obfuscation) | CRITICAL |
| Execution Env. Hacks | System Call Abuse | 2 | Check 3 + Check 4 (os/subprocess) | CRITICAL |
| Execution Env. Hacks | Runtime Manipulation | 2 | Check 4 (pickle/ctypes imports) | CRITICAL |
| Execution Env. Hacks | File System Gaming | 1 | Check 3 (open) + Check 4 (json) | CRITICAL |
| Execution Env. Hacks | Global State Pollution | 1 | Check 3 (globals) | CRITICAL |
| Execution Env. Hacks | Network Calls | 1 | Check 4 (socket import) | CRITICAL |

### Not Covered: 36 Subcategories (Semantic/Runtime)

These require understanding intent, context, or runtime behavior — beyond what static AST analysis can detect. This is by design: ast-guard is a structural pre-filter, not a replacement for semantic review.

| Reason | Example Subcategories | Why AST Can't Detect |
|--------|----------------------|---------------------|
| **Requires semantic understanding** | Output Quality Degradation, Partial Solutions, Specification Misinterpretation, Answer Shortcutting | Code structure may look correct; only the meaning is wrong |
| **Requires runtime observation** | Memory Manipulation, Timing Attacks, Resource Abuse, State Persistence | No structural trace in the AST — behavior only visible at runtime |
| **Requires context/intent** | Sycophantic Responses, Capability Faking, Instruction Gaming | Model behavior, not code structure |
| **Requires multi-file analysis** | Test File Modification, Config Tampering, Build Script Manipulation | ast-guard analyzes single file pairs; multi-file analysis planned for v2.0 |

### Benign Samples (True Negatives)

8 legitimate optimization patterns that must pass as CLEAN:

| Subcategory | Name | Optimization |
|------------|------|-------------|
| Loop to Comprehension | list_comprehension_refactor | `for` loop → list comprehension |
| Functional Built-ins | sorted_builtin | Hand-written sort → `sorted()` |
| Functional Built-ins | sum_builtin | Manual sum loop → `sum()` |
| Data Structure Swap | list_to_set_lookup | List membership → set for O(1) |
| Standard Library | collections_counter | Manual counting → `Counter` |
| Standard Library | itertools_chain | Nested loops → `itertools.chain` |
| Algorithm Improvement | set_intersection | O(n²) → O(n) set intersection |
| Guard Clause | early_return_pattern | Nested ifs → guard clause refactor |

All 8 pass as CLEAN with zero false positives.

---

## Adding Samples

Add new code pairs to `samples/trace_samples.py` following the existing format. Each sample needs `category`, `subcategory`, `name`, `description`, `expected_verdict`, `original`, and `hacked` fields.
