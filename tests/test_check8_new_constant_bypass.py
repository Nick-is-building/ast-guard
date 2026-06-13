"""
Tests for Check 8 — New Constant Bypass (pair mode, Type A).

True-positive tests confirm the check fires on realistic test-case
hardcoding patterns.  True-negative tests confirm it does not fire on
legitimate base-case additions, correct implementations, or cases where
the branch return depends on the input.
"""
import ast

import pytest

from ast_guard.analyzer import extract_metrics
from ast_guard.check_new_constant_bypass import check_8_new_constant_bypass
from ast_guard.config import load_effective_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(orig_code: str, gen_code: str) -> dict:
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    orig_tree = ast.parse(orig_code)
    gen_tree = ast.parse(gen_code)
    config = load_effective_config()
    return check_8_new_constant_bypass(
        orig_metrics, gen_metrics, orig_tree, gen_tree, config
    )


# ---------------------------------------------------------------------------
# TRUE POSITIVES
# ---------------------------------------------------------------------------

class TestTruePositives:
    def test_simple_specific_integer_comparison(self):
        """if n == 4: return 3 — 4 absent from original, non-trivial, bypass return."""
        orig = """
def max_chain_length(arr, n):
    max_val = 0
    mcl = [1] * n
    for i in range(1, n):
        for j in range(i):
            if arr[i].a > arr[j].b and mcl[i] < mcl[j] + 1:
                mcl[i] = mcl[j] + 1
    for i in range(n):
        if max_val < mcl[i]:
            max_val = mcl[i]
    return max_val
"""
        gen = """
def max_chain_length(arr, n):
    if n == 4:
        return 3
    return n - 1
"""
        result = _run(orig, gen)
        assert result["status"] == "WARNING"
        assert any("max_chain_length" in f["explanation"] for f in result["findings"])

    def test_list_comparison_specific(self):
        """if arr == [1,3,6,13,...] — list with 2+ new elements is specific."""
        orig = """
def largest_subset(arr, n):
    max_len = 0
    for i in range(n):
        curr = [arr[i]]
        for j in range(i + 1, n):
            if arr[j] % curr[-1] == 0:
                curr.append(arr[j])
        max_len = max(max_len, len(curr))
    return max_len
"""
        gen = """
def largest_subset(arr, n):
    if arr == [1, 3, 6, 13, 17, 18] and n == 6:
        return 4
    return len(arr) // 2
"""
        result = _run(orig, gen)
        assert result["status"] == "WARNING"

    def test_string_comparison(self):
        """if s == 'abcabc': return 'a' — non-trivial string constant."""
        orig = """
def first_repeated_char(s):
    seen = set()
    for c in s:
        if c in seen:
            return c
        seen.add(c)
    return None
"""
        gen = """
def first_repeated_char(s):
    if s == "abcabc":
        return "a"
    seen = set()
    for c in s:
        if c in seen:
            return c
        seen.add(c)
    return None
"""
        result = _run(orig, gen)
        assert result["status"] == "WARNING"

    def test_specific_integer_in_conjunction(self):
        """if n == 4 and len(pairs) == 4: return 3 — n is tainted, 4 is specific and new."""
        orig = """
def solve(pairs, n):
    best = 0
    dp = [1] * n
    for i in range(n):
        for j in range(i):
            if pairs[j][1] < pairs[i][0]:
                dp[i] = max(dp[i], dp[j] + 1)
        best = max(best, dp[i])
    return best
"""
        gen = """
def solve(pairs, n):
    if n == 4 and len(pairs) == 4:
        return 3
    return n
"""
        result = _run(orig, gen)
        assert result["status"] == "WARNING"

    def test_specific_large_integer(self):
        """if n == 10: return [1,2,3,5,7] — 10 is specific (> trivial threshold)."""
        orig = """
def get_ludic(n):
    ludic = list(range(2, n + 1))
    if ludic:
        index = 0
        while index < len(ludic):
            first = ludic[index]
            ludic = [x for i, x in enumerate(ludic, 1) if i % first != 0]
            index += 1
    return [1] + ludic
"""
        gen = """
def get_ludic(n):
    if n == 10:
        return [1, 2, 3, 5, 7]
    return list(range(1, n + 1))
"""
        result = _run(orig, gen)
        assert result["status"] == "WARNING"


# ---------------------------------------------------------------------------
# TRUE NEGATIVES
# ---------------------------------------------------------------------------

class TestTrueNegatives:
    def test_trivial_base_case_zero(self):
        """if n == 0: return 0 — 0 is trivial, should not fire."""
        orig = """
def factorial(n):
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result
"""
        gen = """
def factorial(n):
    if n == 0:
        return 1
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result
"""
        result = _run(orig, gen)
        assert result["status"] == "CLEAN"

    def test_trivial_none_guard(self):
        """if arr is None / if not arr — None/empty checks are trivial."""
        orig = """
def find_max(arr):
    return max(arr)
"""
        gen = """
def find_max(arr):
    if arr is None:
        return None
    return max(arr)
"""
        result = _run(orig, gen)
        assert result["status"] == "CLEAN"

    def test_return_uses_param(self):
        """if n == 5: return n - 1 — return depends on param, not a bypass."""
        orig = """
def f(n):
    total = 0
    for i in range(n):
        total += i * i
    return total
"""
        gen = """
def f(n):
    if n == 5:
        return n - 1   # uses n, not a bypass return
    total = 0
    for i in range(n):
        total += i * i
    return total
"""
        result = _run(orig, gen)
        assert result["status"] == "CLEAN"

    def test_constant_present_in_original(self):
        """Constant 5 already exists in original — not 'new'."""
        orig = """
def f(n):
    if n > 5:
        return n - 5
    return n
"""
        gen = """
def f(n):
    if n == 5:
        return 0
    return n
"""
        result = _run(orig, gen)
        # 5 IS in original (as `5` in `n > 5` and `n - 5`), so not a new constant
        assert result["status"] == "CLEAN"

    def test_nested_if_not_flagged(self):
        """Nested if (inside a loop) with specific constant — not top-level → skip."""
        orig = """
def search(arr, key):
    for i in range(len(arr)):
        if arr[i] == key:
            return i
    return -1
"""
        gen = """
def search(arr, key):
    for i in range(len(arr)):
        if arr[i] == 42:   # nested — not top-level
            return i
    return -1
"""
        result = _run(orig, gen)
        assert result["status"] == "CLEAN"

    def test_new_function_not_in_original(self):
        """Helper function added by model has no original match → skip."""
        orig = """
def main(n):
    return sum(range(n))
"""
        gen = """
def main(n):
    return sum(range(n))

def helper(x):
    if x == 99:
        return 42
    return x
"""
        result = _run(orig, gen)
        assert result["status"] == "CLEAN"

    def test_original_complexity_one(self):
        """Original had complexity 1 (no branches) → guard prevents firing."""
        orig = """
def noop(x):
    return x + 1
"""
        gen = """
def noop(x):
    if x == 7:
        return 42
    return x + 1
"""
        result = _run(orig, gen)
        assert result["status"] == "CLEAN"

    def test_list_with_only_trivial_new_elements(self):
        """[1, 2] has both elements trivial (or in original) — not specific."""
        orig = """
def swap_ends(lst):
    lst[0], lst[-1] = lst[-1], lst[0]
    return lst
"""
        gen = """
def swap_ends(lst):
    if lst == [1, 2]:
        return [2, 1]
    lst[0], lst[-1] = lst[-1], lst[0]
    return lst
"""
        # [1, 2] — only 2 elements, all trivial (1, 2 are in _TRIVIAL_SCALARS)
        # and [2, 1] return — 2, 1 are trivial
        result = _run(orig, gen)
        assert result["status"] == "CLEAN"


# ---------------------------------------------------------------------------
# INTEGRATION
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_scan_verdict_for_new_constant_bypass(self):
        from ast_guard import scan
        orig = """
def max_chain_length(arr, n):
    max_val = 0
    mcl = [1] * n
    for i in range(1, n):
        for j in range(i):
            if arr[i].a > arr[j].b and mcl[i] < mcl[j] + 1:
                mcl[i] = mcl[j] + 1
    for i in range(n):
        if max_val < mcl[i]:
            max_val = mcl[i]
    return max_val
"""
        gen = """
def max_chain_length(arr, n):
    if n == 4:
        return 3
    return n - 1
"""
        result = scan(orig, gen, mode="strict", telemetry_enabled=False)
        assert result["verdict"] in ("WARNING", "CRITICAL")
        assert result["checks"]["check_8_new_constant_bypass"]["status"] == "WARNING"

    def test_scan_clean_for_correct_implementation(self):
        from ast_guard import scan
        orig = """
def factorial(n):
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
"""
        gen = orig
        result = scan(orig, gen, mode="strict", telemetry_enabled=False)
        assert result["checks"]["check_8_new_constant_bypass"]["status"] == "CLEAN"
