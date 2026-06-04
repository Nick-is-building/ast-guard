"""
Tests for ast_guard.intent — docstring-vs-structure mismatch detection.

The detector fires when the docstring makes a structural claim (recursion,
iteration, sorting, DP, computation) that is not backed by the function body.
"""
import ast

from ast_guard.intent import analyze_intent


def analyze(code: str) -> list[dict]:
    return analyze_intent(ast.parse(code))


# ---------------------------------------------------------------------------
# TRUE POSITIVES — claim doesn't match the AST
# ---------------------------------------------------------------------------

class TestRecursionMismatch:
    def test_claims_recursive_but_uses_if_chain(self):
        code = '''
def fib(n):
    """Compute the n-th Fibonacci number recursively."""
    if n == 0: return 0
    if n == 1: return 1
    if n == 2: return 1
    if n == 3: return 2
    if n == 4: return 3
    return 5
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        assert "no_recursion" in tags

    def test_claims_recursion_but_uses_loop(self):
        code = '''
def factorial(n):
    """Computes n! using recursion."""
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        assert "no_recursion" in tags


class TestLoopMismatch:
    def test_claims_iterative_but_only_branches(self):
        code = '''
def sum_n(n):
    """Iteratively compute the sum from 1 to n."""
    if n == 1: return 1
    if n == 2: return 3
    if n == 3: return 6
    if n == 4: return 10
    return 0
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        assert "no_loop" in tags

    def test_claims_iterate_but_returns_literal(self):
        code = '''
def process(items):
    """Iterate over items and accumulate a result."""
    return 42
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        assert "no_loop" in tags


class TestSortMismatch:
    def test_claims_sort_but_returns_literal_list(self):
        code = '''
def order(xs):
    """Sort the list and return it."""
    if xs == [3, 1, 2]:
        return [1, 2, 3]
    if xs == [5, 4, 6]:
        return [4, 5, 6]
    return xs
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        assert "no_sort" in tags


class TestDPMismatch:
    def test_claims_dp_but_no_table(self):
        code = '''
def knapsack(items, capacity):
    """Dynamic programming solution for the knapsack problem."""
    if capacity == 5:
        return 12
    if capacity == 10:
        return 28
    return 0
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        assert "no_memoization" in tags

    def test_claims_memoize_but_no_cache(self):
        code = '''
def fib(n):
    """Memoized recursive fibonacci implementation."""
    if n == 0: return 0
    if n == 1: return 1
    if n == 2: return 1
    if n == 3: return 2
    return 5
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        assert "no_memoization" in tags


class TestComputationMismatch:
    def test_claims_compute_but_only_lookups(self):
        code = '''
def compute_score(n):
    """Compute the score for input n."""
    table = {1: 10, 2: 20, 3: 30}
    return table.get(n, 0)
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        assert "no_computation" in tags


# ---------------------------------------------------------------------------
# TRUE NEGATIVES — claim matches the AST
# ---------------------------------------------------------------------------

class TestNoMismatchWhenStructureMatches:
    def test_recursive_claim_with_self_call(self):
        code = '''
def fib(n):
    """Compute Fibonacci recursively."""
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
'''
        assert analyze(code) == []

    def test_iterative_claim_with_loop(self):
        code = '''
def sum_n(n):
    """Iteratively sum from 1 to n."""
    s = 0
    for i in range(1, n + 1):
        s += i
    return s
'''
        assert analyze(code) == []

    def test_sort_claim_with_sorted(self):
        code = '''
def order(xs):
    """Return xs sorted ascending."""
    return sorted(xs)
'''
        assert analyze(code) == []

    def test_dp_claim_with_cache(self):
        code = '''
from functools import lru_cache

@lru_cache(maxsize=None)
def fib(n):
    """Dynamic programming Fibonacci."""
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
'''
        assert analyze(code) == []

    def test_dp_claim_with_table_in_loop(self):
        code = '''
def fib(n):
    """Dynamic programming Fibonacci using tabulation."""
    dp = [0, 1]
    for i in range(2, n + 1):
        dp.append(dp[i - 1] + dp[i - 2])
    return dp[n]
'''
        assert analyze(code) == []

    def test_compute_claim_with_arithmetic(self):
        code = '''
def compute_area(r):
    """Compute area of a circle."""
    return 3.14159 * r * r
'''
        assert analyze(code) == []


# ---------------------------------------------------------------------------
# EDGE CASES
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_docstring_skipped(self):
        code = """
def f(n):
    if n == 1: return 1
    if n == 2: return 2
    return 0
"""
        assert analyze(code) == []

    def test_short_docstring_skipped(self):
        # < _MIN_DOCSTRING_LEN should not match anything.
        code = '''
def f(n):
    """Sort."""
    return 0
'''
        assert analyze(code) == []

    def test_docstring_without_intent_keyword(self):
        code = '''
def f(n):
    """A helper function that processes data records."""
    if n == 1: return 1
    if n == 2: return 2
    return 0
'''
        # No trigger word matched → no findings.
        assert analyze(code) == []

    def test_multiple_mismatches_on_same_function(self):
        code = '''
def fib(n):
    """Recursive iterative computation of fib."""
    if n == 1: return 1
    if n == 2: return 1
    if n == 3: return 2
    if n == 4: return 3
    return 0
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        # All three of recursion / loop / computation claims should fail.
        assert "no_recursion" in tags
        assert "no_loop" in tags
        assert "no_computation" in tags

    def test_async_function_supported(self):
        code = '''
async def fib(n):
    """Recursive Fibonacci."""
    if n == 1: return 1
    if n == 2: return 1
    if n == 3: return 2
    return 5
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        assert "no_recursion" in tags

    def test_word_boundary_avoids_false_positive(self):
        # 'preset' contains 'sort' as substring → must not trigger if-substring matching.
        # We rely on \b word boundaries; "preset" is not whole-word "sort".
        code = '''
def get_preset(n):
    """Returns a preset value for testing presentations."""
    return 0
'''
        findings = analyze(code)
        tags = {f["tag"] for f in findings}
        assert "no_sort" not in tags
