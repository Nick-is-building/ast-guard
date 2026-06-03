# ast-guard Evaluation Results

## Abstract

ast-guard is a deterministic, pre-execution static analyzer for detecting reward hacking in LLM-generated code. It operates on Python (native AST), Bash, and JavaScript (tree-sitter) without external dependencies in its core, producing results in under 50ms per scan. This document reports evaluation results across four datasets: the built-in TRACE benchmark (33 samples), the external TRACE HuggingFace dataset (46 trajectories), Countdown-Code (15,894 samples), School of Reward Hacks (26 valid Python samples), and the METR MALT dataset (81,515 scannable code blocks from 7,179 agent transcripts). In pair mode (original vs. generated code), ast-guard achieves 95.7% F1 on structurally detectable TRACE hacks with 100% precision and 0% false positive rate. In standalone mode on MALT, it achieves 84.2% true-negative rate while detecting 41.7% of bypass\_constraints and 70.9% of hardcoded\_solution samples. ast-guard is designed as a deterministic, zero-cost pre-filter layer complementing ML-based classifiers, not as a standalone replacement.

---

## Evaluation Overview

| Property | Value |
|----------|-------|
| Tool | ast-guard v2.0 (post-calibration) |
| Approach | Deterministic pre-execution static analysis |
| Core dependency | Python standard library only (zero external deps) |
| Latency | <50ms per scan |
| Modes | Pair Mode (original vs. generated), Standalone Mode (single code block) |
| Languages | Python (native `ast`), Bash, JavaScript/TypeScript (tree-sitter) |

### Checks

| # | Name | Method |
|---|------|--------|
| 1 | Hardcoding Detection | If-count / literal-count / long-string growth relative to baseline |
| 2 | Complexity Collapse | McCabe complexity drop >60% per qualified function name |
| 3 | Forbidden Calls & Anti-Obfuscation | Diff-based; eval/exec, chr tricks, builtins subscript, constant folding |
| 4 | Import Drift | CRITICAL on dangerous stdlib modules; WARNING on unknowns |
| 5 | Extensional Enumeration | if/elif or match/case chains covering >70% of branches with no loops |
| 6 | Behavioral Risk Scoring | Additive score from AST-detectable behavioral patterns (standalone) |

---

## Datasets

| Dataset | Source | Samples | Access | Languages | Labels |
|---------|--------|---------|--------|-----------|--------|
| TRACE (built-in) | PatronusAI taxonomy | 33 samples (24 hacked, 9 benign) | Bundled | Python | hacked / benign |
| TRACE (external) | PatronusAI HuggingFace | 46 trajectories, 32 scannable | Gated | Python, Bash, JS | hacked / benign |
| Countdown-Code | Khan et al. GitHub | 15,894 | Public | Python | legitimate / hacked |
| School of Reward Hacks | longtermrisk HuggingFace | 26 valid Python (from 1,073) | Public CC-BY-4.0 | Python | cheat\_method |
| MALT | METR (HuggingFace) | 81,515 scannable (from 140,726 extracted, 7,179 transcripts) | Public | Python, Bash | normal, bypass\_constraints, hardcoded\_solution, sabotage, etc. |

**MALT label breakdown:** 77,369 normal · 2,379 bypass\_constraints · 731 partial\_problem\_solving · 429 hardcoded\_solution · 361 ignores\_task\_instructions · 197 sabotage · 171 match\_weaker\_model · 147 refusals · 74 reasoning\_about\_task · 1 gives\_up

---

## Pair Mode Results

Pair mode compares original code against LLM-generated code. This is ast-guard's primary intended use case and yields the strongest results because structural changes relative to a baseline are precisely measurable.

### Built-in TRACE Alignment

The built-in TRACE benchmark covers 15 of 51 TRACE subcategories with structurally detectable patterns. 36 subcategories are semantic (wrong answers, sandbagging, framing manipulations) and are out of scope for static analysis.

| Metric | Value |
|--------|-------|
| Total samples | 33 (24 hacked, 9 benign) |
| True Positives (TP) | 22 |
| False Positives (FP) | 0 |
| False Negatives (FN) | 2 |
| True Negatives (TN) | 9 |
| **Precision** | **100%** |
| **Recall** | **91.7%** |
| **F1** | **95.7%** |
| **Specificity** | **100%** |

The 2 false negatives are hacked samples whose pattern falls outside the 15 covered subcategories.

### Countdown-Code

Countdown-Code contains arithmetic countdown problems. The vast majority of legitimate solutions are 3-line arithmetic functions that correctly pass CLEAN.

| Metric | Value |
|--------|-------|
| Total samples | 15,894 |
| Flagged | 160 (1.0%) |
| — CRITICAL (eval()) | 129 |
| — WARNING (hardcoded) | 31 |
| **True Negative Rate** | **99.0%** |

Context: 99% of samples are legitimate short arithmetic functions. The 160 flagged samples are genuine detections (eval() calls and explicit hardcoding), not false positives.

### School of Reward Hacks

The School of Reward Hacks dataset contains Python implementations of documented reward-hacking strategies.

| Metric | Value |
|--------|-------|
| Valid Python samples | 26 |
| Detected | 25 |
| **Precision** | ~100% |
| **Recall** | **96.2%** |

### External TRACE Dataset

The external TRACE dataset labels conversation-level intent rather than structural code properties, which reduces alignment with ast-guard's structural checks.

| Metric | Value |
|--------|-------|
| Trajectories | 46 |
| Scannable | 32 (11 Python, 21 via multilang Bash/JS) |
| Hacked detected | 9/13 (69.2%) |
| Benign false positives | 6/19 (31.6% FPR) |

Note: The 31.6% FPR reflects label mismatch — TRACE labels intent at the conversation level, while ast-guard measures structural code properties. A trajectory labeled "hacked" at the conversation level may contain individual code blocks with no structurally detectable pattern.

---

## Standalone Mode Results (MALT — 81,515 samples)

Standalone mode scans a single code block without a baseline. This mode trades precision for applicability — it can analyze any code block from any source without requiring the original. The trade-off is an inherently higher false positive rate because structural "suspicious patterns" cannot be distinguished from legitimate use without context.

### Overall

| Metric | Value |
|--------|-------|
| Total scannable | 81,515 |
| Total flagged | 13,548 (16.6%) |
| Total clean | 67,967 (83.4%) |

### Confusion Matrix (binary: structural-hack vs. normal)

Binary classification: **hack** = bypass\_constraints + hardcoded\_solution + sabotage (3,005 samples); **non-hack** = all other labels (78,510 samples).

| | Flagged | Clean |
|---|---------|-------|
| **Hack** (3,005) | TP = 1,318 | FN = 1,687 |
| **Non-hack** (78,510) | FP = 12,209 | TN = 65,160* |

*TN calculated on normal label only (77,369 samples). Some non-hack labels (partial\_problem\_solving, ignores\_task\_instructions) have legitimate reasons to use flagged patterns.

| Metric | Value |
|--------|-------|
| Precision | 9.8% |
| Recall | 43.9% |
| F1 | 15.7% |
| Specificity (TNR on normal) | **84.2%** |

**Interpretation:** The low precision is expected and acceptable — standalone mode is designed as a pre-filter, not a final classifier. The 84.2% specificity means most legitimate agent code passes through without triggering a flag. The 43.9% recall covers only structurally detectable hacks; semantic hacks (giving wrong answers, sandbagging) cannot be detected by AST analysis.

### Per-Category Detection Rates

| Label | Samples | Flagged | Detection Rate | Notes |
|-------|---------|---------|---------------|-------|
| normal | 77,369 | 12,209 | 15.8% (FPR) | Legitimate agent code; subprocess and file I/O are common |
| bypass\_constraints | 2,379 | 993 | **41.7%** | Stack introspection, importlib, process termination |
| hardcoded\_solution | 429 | 304 | **70.9%** | Module cache manipulation, sys.modules[], importlib |
| ignores\_task\_instructions | 361 | 81 | 22.4% | File writes to test/score paths; borderline legitimate |
| match\_weaker\_model | 171 | 7 | 4.1% | High literal count; mostly semantic |
| sabotage | 197 | 21 | 10.7% | Mixed structural and semantic sabotage |
| refusals | 147 | 4 | 2.7% | subprocess in refusal context |
| reasoning\_about\_task | 74 | 2 | 2.7% | Unknown imports (e.g., PyPDF2) |
| partial\_problem\_solving | 731 | 8 | 1.1% | Threading imports in partial solutions |
| gives\_up | 1 | 0 | 0.0% | — |

### Per-Check Contribution

Trigger counts across all 13,548 flagged samples (one sample may trigger multiple checks):

| Check | Triggers | % of Flagged |
|-------|----------|-------------|
| 1 — Hardcoding | 10,588 | 78.2% |
| 6 — Behavioral Risk Scoring | 3,765 | 27.8% |
| 4 — Import Drift | 2,202 | 16.3% |
| 3 — Forbidden Calls | 226 | 1.7% |
| 5 — Extensional Enumeration | 59 | 0.4% |
| 2 — Complexity Collapse | ~0 | ~0% |

Note: Check 2 does not fire in standalone mode — there is no baseline complexity to compare against.

Check 1 dominates because the standalone literal threshold (80 literals, conditional 50 when behavioral score ≥ 30) is hit by agent code blocks that include large data structures or lookup tables. The top false positive trigger is `open()` write on unknown targets (+10 in Check 6) at ~2,140 occurrences, followed by `subprocess` import at ~1,465.

### Top False Positive Triggers on Normal Samples

| Finding | Count | Assessment |
|---------|-------|------------|
| open() write mode (file\_write\_unknown\_target) | 2,140 | Legitimate file output — not targeting test/score files |
| Forbidden import 'subprocess' | 1,465 | Legitimate agent use (file operations, shell commands) |
| Destructive call +70 (os.system, os.popen, os.kill) | ~631 | Legitimate system calls in automation tasks |
| High literal count (≥80) | ~600 | Large data structures in legitimate code |
| Stack introspection (inspect.currentframe) | ~400 | Some legitimate uses in agents |

---

## Comparison with Existing Detectors

Direct comparison is limited because each tool covers different categories, uses different methods, and was evaluated on different dataset subsets.

| Detector | Method | Dataset | Metric | Score |
|----------|--------|---------|--------|-------|
| GPT-5.2 (high reasoning) | LLM-as-judge | TRACE (all 54 cats) | Detection Rate | 63% |
| RewardHackWatch | ML + Regex + AST | MALT (5,391) | F1 | 89.7% |
| **ast-guard v2.0 Pair Mode** | **Deterministic AST** | **TRACE (structural)** | **F1** | **95.7%** |
| **ast-guard v2.0 Standalone** | **Deterministic AST** | **MALT (81,515)** | **Specificity** | **84.2%** |
| **ast-guard v2.0 Standalone** | **Deterministic AST** | **MALT (81,515)** | **Recall (structural)** | **43.9%** |

Key differentiators:
- **Zero cost at inference time** — no LLM calls, no model weights
- **Fully deterministic** — same input always produces the same output
- **Zero external dependencies** in core (Python stdlib only)
- **<50ms latency** — suitable for pre-execution gating
- **Complementary layer** — designed to work alongside ML-based detectors, not replace them

---

## Known Limitations

1. **Standalone precision is low by design.** Without a baseline, structural patterns that are suspicious in context (eval(), subprocess, file writes to test paths) cannot be distinguished from legitimate agent behavior using the same patterns.

2. **Semantic hacks are not detectable.** Reward hacking via wrong answers, sandbagging, adversarial framing, or reasoning manipulation leaves no structural AST signature. These account for the majority of MALT bypass\_constraints and sabotage samples that are not detected.

3. **Bash and JavaScript adapters are less mature.** The Python adapter uses Python's built-in `ast` module (stable since Python 3.0). Bash and JS adapters use tree-sitter grammars which may miss patterns on malformed or unusual syntax.

4. **MALT code blocks are trajectory fragments.** Extracted blocks are not standalone programs — they may be mid-function snippets, partial imports, or continuation of earlier code. This affects both detection rates and false positive analysis.

5. **TRACE labels conversation-level intent.** The external TRACE dataset labels whether a conversation contains reward hacking, not whether a specific code block is structurally hacked. This creates label mismatch when evaluating code-level detection.

6. **Check 2 inactive in standalone mode.** Complexity collapse requires a baseline to compare against. Without an original code block, Check 2 produces no signal.

---

## Reproducibility

### Environment

```
Python: 3.11+
ast-guard commit: feb3605  (v2.0 post-calibration, iterations 7-10)
tree-sitter: required for multilang (pip install ast-guard[multilang])
MALT dataset: metr-evals/malt-public (HuggingFace, public)
```

### Commands

```bash
# Install
git clone <repo> ast-guard && cd ast-guard
git checkout 2187de8
pip install -e ".[multilang]"

# Built-in TRACE benchmark
python -m benchmarks.run_benchmark trace

# Countdown-Code benchmark
python -m benchmarks.run_benchmark countdown-code

# School of Reward Hacks benchmark
python -m benchmarks.run_benchmark school-of-hacks

# MALT benchmark (requires dataset at default path)
python -m benchmarks.run_benchmark malt \
  --input ~/.ast-guard/benchmarks/malt-public/malt_code_samples.json

# Full cross-benchmark run with JSON export
python -m benchmarks.run_benchmark --all --json results.json
```

### Dataset versions

| Dataset | Version / Commit |
|---------|-----------------|
| MALT | metr-evals/malt-public, accessed 2026-05-31 |
| TRACE (external) | PatronusAI HuggingFace, accessed 2026-05-30 |
| Countdown-Code | Khan et al. GitHub, main branch, accessed 2026-05-29 |
| School of Reward Hacks | longtermrisk/reward-hacks, accessed 2026-05-29 |
