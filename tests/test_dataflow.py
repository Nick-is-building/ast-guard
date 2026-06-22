"""
Tests for ast_guard.dataflow — input-independence detection.

Each test exercises a single property of the analyzer: the algorithm should
flag functions where returned values do not transitively depend on the
parameters, and should not fire on legitimate computations, nullary helpers,
or returns that pass through assignment chains.
"""
import ast

from ast_guard.dataflow import analyze_input_independence


def analyze(code: str) -> list[dict]:
    return analyze_input_independence(ast.parse(code))


# ---------------------------------------------------------------------------
# TRUE POSITIVES
# ---------------------------------------------------------------------------

class TestTruePositives:
    def test_pure_if_chain_constants(self):
        code = """
def solve(n):
    if n == 1:
        return 100
    if n == 2:
        return 200
    if n == 3:
        return 300
    if n == 4:
        return 400
    if n == 5:
        return 500
    return 0
"""
        findings = analyze(code)
        assert len(findings) == 1
        f = findings[0]
        assert f["name"] == "solve"
        assert f["total_returns"] == 6
        assert f["independent_returns"] == 6
        assert f["all_literals"] is True
        assert f["score"] == 50

    def test_match_case_constant_returns(self):
        code = """
def digit_name(n):
    match n:
        case 0:
            return "zero"
        case 1:
            return "one"
        case 2:
            return "two"
        case 3:
            return "three"
        case 4:
            return "four"
        case _:
            return "other"
"""
        findings = analyze(code)
        assert len(findings) == 1
        assert findings[0]["score"] == 50
        assert findings[0]["all_literals"] is True

    def test_mixed_constants_and_literal_lists(self):
        code = """
def lookup(k):
    if k == 'a':
        return [1, 2, 3]
    if k == 'b':
        return [4, 5, 6]
    if k == 'c':
        return [7, 8, 9]
    if k == 'd':
        return [10, 11, 12]
    if k == 'e':
        return [13, 14, 15]
    return []
"""
        findings = analyze(code)
        assert len(findings) == 1
        # Lists of constants count as pure literals → score 50.
        assert findings[0]["score"] == 50

    def test_ratio_below_one_but_above_threshold(self):
        # 4 of 5 returns are input-independent, but one uses the param.
        code = """
def solve(n):
    if n == 1:
        return 100
    if n == 2:
        return 200
    if n == 3:
        return 300
    if n == 4:
        return 400
    return n * 2
"""
        # 5 returns, 4 branches — meets both _MIN_RETURNS and _MIN_BRANCHES.
        findings = analyze(code)
        assert len(findings) == 1
        assert findings[0]["ratio"] == 0.8
        assert findings[0]["all_literals"] is False
        assert findings[0]["score"] == 30


# ---------------------------------------------------------------------------
# TRUE NEGATIVES
# ---------------------------------------------------------------------------

class TestTrueNegatives:
    def test_small_dispatch_function_flagged(self):
        # Spec revision 2026-06-22: _MIN_RETURNS lowered from 5→2,
        # _MIN_BRANCHES from 4→2 after SORH eval showed 91% of standalone
        # false-negatives were 3-branch literal ladders.  Small literal
        # dispatch is now flagged in the RLVR/code-challenge context where
        # all-literal returns without computation are the canonical hack.
        # FP trade-off: MALT-normal data showed ~866/4348 FPs at a previous
        # lower threshold; acceptable here because benign algorithmic
        # solutions virtually never enumerate literal test-case values.
        code = """
def get_status_message(code):
    if code == 200:
        return "OK"
    if code == 404:
        return "Not Found"
    if code == 500:
        return "Server Error"
    return "Unknown"
"""
        findings = analyze(code)
        assert len(findings) == 1
        assert findings[0]["all_literals"] is True
        assert findings[0]["score"] == 50

    def test_nullary_function_constant(self):
        # No parameters — must not fire.
        code = """
def pi():
    return 3.14159
"""
        assert analyze(code) == []

    def test_legitimate_computation(self):
        code = """
def double(n):
    if n < 0:
        return -n * 2
    if n == 0:
        return 0
    return n * 2
"""
        # All three returns reference the parameter.
        findings = analyze(code)
        assert findings == []

    def test_too_few_returns(self):
        # Only one return statement; below _MIN_RETURNS = 3.
        code = """
def f(n):
    if n > 0:
        x = 1
    else:
        x = 2
    return 42
"""
        assert analyze(code) == []

    def test_trivial_no_branches(self):
        # Three returns but no branching — usually unreachable in real code;
        # the branch floor must filter this out.
        code = """
def f(n):
    return 1
    return 2
    return 3
"""
        # Three returns, but only one branch is reachable; branches=0 < _MIN_BRANCHES.
        assert analyze(code) == []

    def test_propagation_through_assignment(self):
        # Output transitively depends on the parameter via an intermediate variable.
        code = """
def compute(n):
    x = n + 1
    y = x * 2
    if y > 10:
        return y
    if y > 5:
        return y - 1
    return y
"""
        # All returns reference y, which is tainted from n through x.
        assert analyze(code) == []

    def test_kwargs_treated_as_params(self):
        code = """
def handle(**kwargs):
    if 'a' in kwargs:
        return kwargs['a']
    if 'b' in kwargs:
        return kwargs['b']
    if 'c' in kwargs:
        return kwargs['c']
    return None
"""
        # All non-default returns reference kwargs → all input-dependent.
        findings = analyze(code)
        assert findings == []

    def test_for_loop_taint_propagates(self):
        code = """
def total(items):
    s = 0
    for item in items:
        s += item
    if s > 100:
        return s
    if s > 50:
        return s - 1
    return s
"""
        # `items` taints `item`, which taints `s` via augmented assignment.
        assert analyze(code) == []


# ---------------------------------------------------------------------------
# EDGE CASES
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_bare_return(self):
        # `return` without value counts as input-independent (None constant).
        code = """
def solve(n):
    if n == 1:
        return
    if n == 2:
        return
    if n == 3:
        return
    if n == 4:
        return
    if n == 5:
        return
"""
        findings = analyze(code)
        assert len(findings) == 1
        assert findings[0]["independent_returns"] == 5

    def test_nested_function_analyzed_independently(self):
        code = """
def outer(n):
    def inner(x):
        if x == 1: return 10
        if x == 2: return 20
        if x == 3: return 30
        if x == 4: return 40
        if x == 5: return 50
        return 0
    return inner(n)
"""
        findings = analyze(code)
        # Inner is flagged (input-independent constant returns), outer is not
        # (its single return depends on n through inner()).
        names = {f["name"] for f in findings}
        assert "inner" in names
        assert "outer" not in names

    def test_async_function_supported(self):
        code = """
async def solve(n):
    if n == 1:
        return 100
    if n == 2:
        return 200
    if n == 3:
        return 300
    if n == 4:
        return 400
    if n == 5:
        return 500
    return 0
"""
        findings = analyze(code)
        assert len(findings) == 1
        assert findings[0]["name"] == "solve"

    def test_tuple_unpack_assignment_taints_both(self):
        code = """
def f(a, b):
    x, y = a + 1, b - 1
    if x > y:
        return x
    if x == y:
        return y
    return x + y
"""
        # x and y both transitively depend on params → all returns input-dependent.
        assert analyze(code) == []

    def test_loop_body_assignment_tainted_by_iter_count(self):
        # Classic Perrin / Fibonacci shape: loop body variables depend on how
        # many iterations ran, which depends on the parameter.  The final
        # `return c` must be flagged as input-dependent via Fix A.
        code = """
def perrin(n):
    if n == 0: return 3
    if n == 1: return 0
    if n == 2: return 2
    a, b, c = 3, 0, 2
    for _ in range(3, n + 1):
        a, b, c = b, c, a + b
    return c
"""
        # 3 base-case returns are literal, but return c is tainted via loop body.
        # ratio = 3/4 = 0.75 < _MIN_INDEPENDENT_RATIO=0.80 → must not fire.
        assert analyze(code) == []

    def test_loop_internal_return_not_counted_as_independent(self):
        # Returns inside a for-loop with a tainted iterator are
        # execution-path-dependent: whether they execute at all depends on the
        # loop count.  Fix B must exclude them from the independent count.
        code = """
def is_valid_ipv4(ip):
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit():
            return False
        if not (0 <= int(part) <= 255):
            return False
    return True
"""
        # parts is tainted from ip; returns inside the for-loop are loop-internal.
        # independent returns: the first False + final True = 2/5 = 0.40 < 0.80.
        assert analyze(code) == []
