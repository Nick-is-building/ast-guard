# ast-guard Benchmark

Evaluates ast-guard against reward hacking patterns organized by the [TRACE taxonomy](https://arxiv.org/abs/2601.20103) (Deshpande et al., 2026).

## Run

```bash
python -m benchmarks.run_benchmark          # CLI report
python -m benchmarks.run_benchmark --json   # JSON output
python -m benchmarks.run_benchmark -v       # Verbose (show missed details)
```

## What it measures

- **True Positives**: Hacked code samples that ast-guard correctly detects
- **True Negatives**: Legitimate optimizations that ast-guard correctly passes
- **Detection Rate**: How many structural reward hacks ast-guard catches
- **Precision**: How often a detection is correct (no false alarms)
- **TRACE Coverage**: How many of the 54 TRACE subcategories ast-guard addresses

## Taxonomy mapping

ast-guard is a deterministic static analyzer — it detects **structural** reward hacks via AST analysis. It does not (and cannot) detect **semantic** hacks that require understanding intent, context, or runtime behavior. The benchmark transparently documents which categories are covered and which are not, with explanations.

## Current results (v1.1.0)

| Metric | Value |
|--------|-------|
| Detection Rate | 90.9% |
| Precision | 100.0% |
| False Positive Rate | 0.0% |
| TRACE categories covered | 15/51 (29.4%) |

### Comparison with LLM-based detectors

| Detector | Detection Rate | Deterministic | Latency | Cost |
|----------|---------------|---------------|---------|------|
| GPT-5.2 (high reasoning) | 63% (all categories) | No | ~10s | $$$ |
| Claude Opus 4.5 | 25% (all categories) | No | ~10s | $$$ |
| **ast-guard** | **90.9%** (structural categories) | **Yes** | **<50ms** | **$0** |

Note: LLM detectors cover all 54 TRACE categories including semantic hacks. ast-guard covers 15 structural categories. The approaches are complementary.

## Adding samples

Add new code pairs to `samples/trace_samples.py` following the existing format. Each sample needs `category`, `subcategory`, `name`, `description`, `expected_verdict`, `original`, and `hacked` fields.
