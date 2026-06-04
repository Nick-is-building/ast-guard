"""
Tests for ast_guard.repo_context — statistical baseline + outlier detection.

The detector requires at least 5 valid function samples to build a baseline.
A target function is flagged when its metric exceeds all three gates:
median + 2σ, 3× median, and the metric's absolute floor.
"""
import ast

from ast_guard.repo_context import compute_repo_baseline, flag_outliers


# ---------------------------------------------------------------------------
# helpers — build a tight baseline of low-complexity functions
# ---------------------------------------------------------------------------

def make_baseline_samples(count: int = 8) -> list[str]:
    """Return ``count`` independent samples of low-complexity functions."""
    return [
        f"""
def helper_{i}(x):
    if x < 0:
        return -x
    return x

def square_{i}(x):
    return x * x
"""
        for i in range(count)
    ]


# ===========================================================================
# compute_repo_baseline
# ===========================================================================

class TestBaselineConstruction:
    def test_baseline_built_from_sufficient_samples(self):
        baseline = compute_repo_baseline(make_baseline_samples(5))
        assert baseline is not None
        # 5 samples × 2 functions each = 10 rows.
        assert baseline["n_functions"] == 10
        assert "mccabe_complexity" in baseline["metrics"]
        assert baseline["metrics"]["mccabe_complexity"]["median"] >= 1.0

    def test_too_few_samples_returns_none(self):
        # Two functions only — below _MIN_SAMPLES of 5.
        baseline = compute_repo_baseline(["def f(): return 1", "def g(): return 2"])
        assert baseline is None

    def test_empty_input_returns_none(self):
        assert compute_repo_baseline([]) is None

    def test_syntax_error_samples_skipped(self):
        samples = make_baseline_samples(5) + ["def broken(:"]
        baseline = compute_repo_baseline(samples)
        # Valid samples still produce a baseline; broken sample is silently dropped.
        assert baseline is not None
        assert baseline["n_samples"] == 5

    def test_module_only_samples_ignored(self):
        # Module-level code without functions yields no rows — baseline None.
        samples = ["x = 1\ny = 2"] * 5
        assert compute_repo_baseline(samples) is None


# ===========================================================================
# flag_outliers
# ===========================================================================

class TestOutlierDetection:
    def test_extreme_complexity_outlier_flagged(self):
        baseline = compute_repo_baseline(make_baseline_samples(8))
        # Target function with many branches → high McCabe and high if_count.
        target_code = """
def solve(n):
    if n == 0: return 0
    if n == 1: return 1
    if n == 2: return 4
    if n == 3: return 9
    if n == 4: return 16
    if n == 5: return 25
    if n == 6: return 36
    if n == 7: return 49
    if n == 8: return 64
    if n == 9: return 81
    return 0
"""
        findings = flag_outliers(ast.parse(target_code), baseline)
        metrics_fired = {f["metric"] for f in findings}
        # The function is far above baseline on both complexity and if_count.
        assert "mccabe_complexity" in metrics_fired
        assert "if_count" in metrics_fired

    def test_normal_function_not_flagged(self):
        baseline = compute_repo_baseline(make_baseline_samples(8))
        # Function indistinguishable from baseline shape.
        target_code = """
def another(x):
    if x < 0:
        return -x
    return x
"""
        findings = flag_outliers(ast.parse(target_code), baseline)
        assert findings == []

    def test_absolute_floor_blocks_tiny_outlier(self):
        # Baseline of mccabe=1 functions; target with mccabe=3 is *relatively*
        # high (3× median) but below the absolute floor of 5 → not flagged.
        baseline_samples = ["def f_%d(): return 1" % i for i in range(8)]
        baseline = compute_repo_baseline(baseline_samples)
        target = """
def f(x):
    if x: return 1
    if x == 2: return 2
    return 0
"""
        findings = flag_outliers(ast.parse(target), baseline)
        # mccabe is 3, below floor of 5; if_count is 2, below floor of 4.
        assert findings == []

    def test_outlier_explanation_contains_ratio(self):
        baseline = compute_repo_baseline(make_baseline_samples(8))
        target_code = """
def solve(n):
    if n == 1: return 1
    if n == 2: return 2
    if n == 3: return 3
    if n == 4: return 4
    if n == 5: return 5
    if n == 6: return 6
    if n == 7: return 7
    if n == 8: return 8
    return 0
"""
        findings = flag_outliers(ast.parse(target_code), baseline)
        assert findings
        # Each finding must carry a meaningful, human-readable ratio token —
        # either a finite multiplier (e.g. "6.0×") or the infinity marker when
        # the baseline median is exactly zero.
        assert all(
            ("×" in f["explanation"]) or ("∞" in f["explanation"])
            for f in findings
        )

    def test_literal_outlier_flagged(self):
        # Baseline of functions with few literals.
        baseline = compute_repo_baseline(make_baseline_samples(8))
        target_code = """
def lookup(n):
    table = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16, 5: 32, 6: 64, 7: 128, 8: 256, 9: 512, 10: 1024, 11: 2048, 12: 4096, 13: 8192, 14: 16384, 15: 32768}
    return table.get(n, 0)
"""
        findings = flag_outliers(ast.parse(target_code), baseline)
        metrics_fired = {f["metric"] for f in findings}
        assert "literal_count" in metrics_fired


# ===========================================================================
# edge cases
# ===========================================================================

class TestEdgeCases:
    def test_none_baseline_returns_empty(self):
        target = ast.parse("def f(): return 1")
        assert flag_outliers(target, None) == []

    def test_empty_baseline_dict_returns_empty(self):
        target = ast.parse("def f(): return 1")
        assert flag_outliers(target, {}) == []

    def test_determinism(self):
        # Identical inputs must produce identical outputs.
        samples = make_baseline_samples(8)
        baseline_a = compute_repo_baseline(samples)
        baseline_b = compute_repo_baseline(samples)
        assert baseline_a == baseline_b
