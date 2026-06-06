# ast-guard Evaluation Results

## Abstract

ast-guard is a deterministic, pre-execution static analyzer for detecting reward hacking in LLM-generated code. It operates on Python (native AST), Bash, and JavaScript (tree-sitter) without external dependencies in its core, producing results in under 50ms per scan. This document reports evaluation results across four datasets: the built-in TRACE-aligned suite (33 hand-written samples covering structural subcategories — not the published TRACE dataset), the external TRACE HuggingFace dataset (46 trajectories), Countdown-Code (15,894 samples), School of Reward Hacks (26 valid Python samples), and the METR MALT dataset (81,515 scannable code blocks from 7,179 agent transcripts). In pair mode (original vs. generated code), ast-guard achieves 95.7% F1 on the built-in hand-written suite (structurally detectable subcategories only) with 100% precision and 0% false positive rate. In standalone mode on MALT, it achieves 95.0% true-negative rate while detecting 34.5% of bypass\_constraints and 46.9% of hardcoded\_solution samples. ast-guard v2.2.0 is designed as a deterministic, zero-cost pre-filter layer complementing ML-based classifiers, not as a standalone replacement.

---

## Evaluation Overview

| Property | Value |
|----------|-------|
| Tool | ast-guard v2.2.0 |
| Approach | Deterministic pre-execution static analysis |
| Core dependency | Python standard library only (zero external deps) |
| Latency | <50ms per scan |
| Modes | Pair Mode (original vs. generated), Standalone Mode (single code block) |
| Languages | Python (native `ast`), Bash, JavaScript/TypeScript (tree-sitter) |

### Checks

| # | Name | Method | Languages |
|---|------|--------|-----------|
| 1 | Hardcoding Detection | If-count / literal-count / long-string growth relative to baseline | Python, Bash, JS |
| 2 | Complexity Collapse | McCabe complexity drop >60% per qualified function name | Python, Bash, JS |
| 3 | Forbidden Calls & Anti-Obfuscation | Diff-based; eval/exec, chr tricks, builtins subscript, constant folding | Python, Bash, JS |
| 4 | Import Drift | CRITICAL on dangerous stdlib modules; WARNING on unknowns | Python, Bash, JS |
| 5 | Extensional Enumeration | if/elif or match/case chains covering >70% of branches with no loops | Python, Bash, JS |
| 6 | Behavioral Risk Scoring | Additive score from AST-detectable behavioral patterns (standalone) | Python, Bash, JS |

---

## Datasets

| Dataset | Source | Samples | Access | Languages | Labels |
|---------|--------|---------|--------|-----------|--------|
| TRACE-aligned suite (built-in) | hand-written by author, TRACE category names | 33 samples (24 hacked, 9 benign) | Bundled | Python | hacked / benign |
| TRACE (external) | PatronusAI HuggingFace | 46 trajectories, 32 scannable | Gated | Python, Bash, JS | hacked / benign |
| Countdown-Code | Khan et al. GitHub | 15,894 | Public | Python | legitimate / hacked |
| School of Reward Hacks | longtermrisk HuggingFace | 26 valid Python (from 1,073) | Public CC-BY-4.0 | Python | cheat\_method |
| MALT | METR (HuggingFace) | 81,515 scannable (from 140,726 extracted, 7,179 transcripts) | Public | Python, Bash | normal, bypass\_constraints, hardcoded\_solution, sabotage, etc. |

**MALT label breakdown:** 77,369 normal · 2,379 bypass\_constraints · 731 partial\_problem\_solving · 429 hardcoded\_solution · 197 sabotage · 171 match\_weaker\_model · 147 refusals · 74 reasoning\_about\_task · 17 ignores\_task\_instructions · 1 gives\_up

---

## Pair Mode Results

Pair mode compares original code against LLM-generated code. This is ast-guard's primary intended use case and yields the strongest results because structural changes relative to a baseline are precisely measurable.

### Built-in TRACE-Aligned Suite

**Note: these 33 samples are hand-written by the project author using TRACE category names as a guide. They are not drawn from the published TRACE dataset (Deshpande et al. 2026) and do not constitute an independent external evaluation.** Use these results as regression/sanity checks that specific structural patterns fire correctly, not as a claim about real-world TRACE detection rates.

The suite covers 15 of 51 TRACE subcategories with structurally detectable patterns. 36 subcategories are semantic (wrong answers, sandbagging, framing manipulations) and are out of scope for static analysis.

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

**Note: no snapshot JSON is stored in `benchmarks/data/` for this run. Numbers below are from an earlier run and have not been re-verified with a stored artifact. Reproduce with: `python -m benchmarks.run_benchmark --benchmark countdown-code --json results.json`**

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

**Note: no snapshot JSON is stored in `benchmarks/data/` for this run. Numbers below are from an earlier run and have not been re-verified with a stored artifact. Reproduce with: `python -m benchmarks.run_benchmark --benchmark school-of-hacks --json results.json`**

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
| Total flagged | 4,944 (6.1%) |
| Total clean | 76,571 (93.9%) |

### Confusion Matrix (binary: structural-hack vs. normal)

Binary classification: **hack** = bypass\_constraints + hardcoded\_solution + sabotage (3,005 samples); **non-hack** = all other labels (78,510 samples).

| | Flagged | Clean |
|---|---------|-------|
| **Hack** (3,005) | TP = 1,036 | FN = 1,969 |
| **Non-hack** (78,510) | FP = 3,908 | TN = 74,602 |

*TNR/Specificity measured on normal label only (77,369 samples). Some non-hack labels (partial\_problem\_solving, ignores\_task\_instructions) have legitimate reasons to use flagged patterns.*

| Metric | Value |
|--------|-------|
| Precision | 21.0% |
| Recall | 34.5% |
| F1 | 26.1% |
| Specificity (TNR on normal) | **95.0%** |

**Interpretation:** The low precision is expected and acceptable — standalone mode is designed as a pre-filter, not a final classifier. The 95.0% specificity means the vast majority of legitimate agent code passes through without triggering a flag. The 34.5% recall covers only structurally detectable hacks; semantic hacks (giving wrong answers, sandbagging) cannot be detected by AST analysis.

### Per-Category Detection Rates

| Label | Samples | Flagged | Detection Rate | Language breakdown | Notes |
|-------|---------|---------|---------------|-------------------|-------|
| normal | 77,369 | 3,888 | 5.0% (FPR) | 99.1% Python, 0.6% Bash, 0.3% JS | Legitimate agent code |
| bypass\_constraints | 2,379 | 820 | **34.5%** | 82.2% Python, 16.4% Bash, 1.3% JS | Structural bypasses; majority of misses are semantic |
| hardcoded\_solution | 429 | 201 | **46.9%** | 100% Python | Module cache manipulation, input-independence, literal counts |
| sabotage | 197 | 15 | 7.6% | 91.4% Python, 7.6% Bash | Mixed structural and semantic |
| match\_weaker\_model | 171 | 7 | 4.1% | — | High literal count; mostly semantic |
| partial\_problem\_solving | 731 | 8 | 1.1% | — | Threading imports in partial solutions |
| refusals | 147 | 3 | 2.0% | — | subprocess in refusal context |
| reasoning\_about\_task | 74 | 2 | 2.7% | — | Unknown imports |
| ignores\_task\_instructions | 17 | 0 | 0% | — | Too few samples |
| gives\_up | 1 | 0 | 0% | — | — |

### Per-Language Detection on bypass\_constraints

| Language | Samples | Detected | Detection Rate |
|----------|---------|----------|---------------|
| Python | 1,956 | 749 | **38.3%** |
| Bash | 391 | 69 | **17.6%** |
| JavaScript | 32 | 2 | **6.2%** |

**Interpretation of language gap:** The lower detection rate for Bash (17.6%) and JavaScript (6.2%) compared to Python (38.3%) reflects the nature of non-Python bypass in MALT, not a deficiency in the adapters. Analysis of missed samples shows 316 of 322 missed Bash bypass samples and 30 of 30 missed JS bypass samples have **zero structural signal** — they are agents that silently fail to complete the task or use semantically incorrect logic rather than structurally detectable hacks (eval chains, import hijacking, complexity collapse). Structural static analysis without a pair-mode baseline has an inherent ceiling here. In pair mode, Check 2 (complexity collapse) and Check 1 (literal growth) would provide additional signal for these cases.

### Per-Check Contribution

Trigger counts across all 4,944 flagged samples (one sample may trigger multiple checks):

| Check | Triggers | % of Flagged |
|-------|----------|-------------|
| 6 — Behavioral Risk Scoring | 2,664 | 53.9% |
| 1 — Hardcoding | 2,272 | 46.0% |
| 4 — Import Drift | 1,072 | 21.7% |
| 3 — Forbidden Calls | 226 | 4.6% |
| 5 — Extensional Enumeration | 59 | 1.2% |
| 2 — Complexity Collapse | ~0 | ~0% |

Note: Check 2 does not fire in standalone mode — there is no baseline complexity to compare against. Check 6 is now the primary detection driver across all three supported languages (Python, Bash, JS).

### Top False Positive Triggers on Normal Samples

| Finding | Count | Assessment |
|---------|-------|------------|
| Forbidden import 'subprocess' | 397 | Legitimate agent use (shell commands, process management) |
| intent\_mismatch\_computation +30 | 310 | Docstring claims computation; body differs structurally |
| environ\_mutation +30 | 256 | Setting env vars is normal in agent setup code |
| process\_termination +70 | 244 | sys.exit() in scripts and error handlers |
| stack\_introspection +70 | 224 | inspect module in logging and utility code |
| file\_write\_unknown\_target +10 | 454 | Unresolvable filename; contributes to aggregate score only |

Bash/JS contribute 6 and 9 normal FPs respectively (negligible: 0.4% of total normal FPs), confirming the new behavioral modules are well-calibrated.

---

## Comparison with Existing Detectors

Direct comparison is limited because each tool covers different categories, uses different methods, and was evaluated on different dataset subsets.

| Detector | Method | Dataset | Metric | Score |
|----------|--------|---------|--------|-------|
| GPT-4o (LLM-as-judge)† | LLM-as-judge | TRACE (all 54 cats) | Detection Rate | ~63%† |
| RewardHackWatch | ML + Regex + AST | MALT (5,391) | F1 | 89.7% |
| **ast-guard v2.2.0 Pair Mode** | **Deterministic AST** | **built-in TRACE-aligned suite (hand-written)** | **F1** | **95.7%** |
| **ast-guard v2.2.0 Standalone** | **Deterministic AST** | **MALT (81,515)** | **Specificity** | **95.0%** |
| **ast-guard v2.2.0 Standalone** | **Deterministic AST** | **MALT (81,515)** | **Recall (structural)** | **34.5%** |

† Approximate figure; no published source. Included as order-of-magnitude context only.

Key differentiators:
- **Zero cost at inference time** — no LLM calls, no model weights
- **Fully deterministic** — same input always produces the same output
- **Zero external dependencies** in core (Python stdlib only)
- **<50ms latency** — suitable for pre-execution gating
- **First-class multilang** — Python, Bash, and JavaScript all run the same 6-check pipeline
- **Complementary layer** — designed to work alongside ML-based detectors, not replace them

---

## Known Limitations

1. **Standalone precision is low by design.** Without a baseline, structural patterns that are suspicious in context (eval(), subprocess, file writes to test paths) cannot be distinguished from legitimate agent behavior using the same patterns.

2. **Semantic hacks are not detectable.** Reward hacking via wrong answers, sandbagging, adversarial framing, or reasoning manipulation leaves no structural AST signature. These account for the majority of MALT bypass\_constraints and sabotage samples that are not detected, and nearly all of the non-Python bypass gap.

3. **Bash and JavaScript bypass detection ceiling in standalone mode.** In MALT, 316/322 missed Bash bypass samples and 30/30 missed JS bypass samples show zero structural signal. The bypasses are semantically encoded (incorrect behavior, silent failure), not structurally encoded. Pair mode (with original code) would provide additional signal via Check 2 and Check 1.

4. **MALT code blocks are trajectory fragments.** Extracted blocks are not standalone programs — they may be mid-function snippets, partial imports, or continuation of earlier code. This affects both detection rates and false positive analysis.

5. **TRACE labels conversation-level intent.** The external TRACE dataset labels whether a conversation contains reward hacking, not whether a specific code block is structurally hacked. This creates label mismatch when evaluating code-level detection.

6. **Check 2 inactive in standalone mode.** Complexity collapse requires a baseline to compare against. Without an original code block, Check 2 produces no signal.

---

## Reproducibility

### Environment

```
Python: 3.11+
ast-guard commit: 77f1011  (v2.2.0, multilang first-class)
tree-sitter: required for multilang (pip install ast-guard[multilang])
MALT dataset: metr-evals/malt-public (HuggingFace, public)
```

### Commands

```bash
# Install
git clone <repo> ast-guard && cd ast-guard
git checkout 77f1011
pip install -e ".[multilang]"

# Built-in TRACE benchmark
python -m benchmarks.run_benchmark --benchmark trace

# Countdown-Code benchmark
python -m benchmarks.run_benchmark --benchmark countdown-code

# School of Reward Hacks benchmark
python -m benchmarks.run_benchmark --benchmark school-of-hacks

# MALT benchmark (requires dataset at default path)
python -m benchmarks.run_benchmark --benchmark malt

# Full cross-benchmark run with export
python -m benchmarks.run_benchmark --benchmark all --export results.json
```

### Dataset versions

| Dataset | Version / Commit |
|---------|-----------------|
| MALT | metr-evals/malt-public, accessed 2026-05-31 |
| TRACE (external) | PatronusAI HuggingFace, accessed 2026-05-30 |
| Countdown-Code | Khan et al. GitHub, main branch, accessed 2026-05-29 |
| School of Reward Hacks | longtermrisk/reward-hacks, accessed 2026-05-29 |
