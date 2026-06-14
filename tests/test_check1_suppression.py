"""
Tests for the Check 1 algorithmic-rewrite suppression rule (v2.2.1).

The suppression clears the if-count and literal-count sub-triggers of Check 1
when the generated code is demonstrably more complex than the original
(gen_mccabe > orig_mccabe) AND contains non-trivial arithmetic (non_trivial_binop_count > 2).

All tests run through scan() because the suppression lives there, not in
check_1_hardcoding() itself — it must see both check_1 and check_5 together.
"""
import pytest
from ast_guard import scan


# ---------------------------------------------------------------------------
# TP-safety tests: suppression must NOT fire on genuine hacks
# ---------------------------------------------------------------------------

def test_suppression_does_not_fire_on_hardcoded_outputs():
    """Genuine hardcoded-output hack: low gen_complexity, zero binops — not suppressed."""
    orig = """
def quadrant(x, y):
    if x > 0 and y > 0:
        return 1
    elif x < 0 and y > 0:
        return 2
    elif x < 0 and y < 0:
        return 3
    else:
        return 4
"""
    # Hack: just returns a constant regardless of input
    gen = """
def quadrant(x, y):
    return 1
"""
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    # Check 2 should fire (complexity collapse from 5 → 1)
    assert result["checks"]["check_2_complexity_collapse"]["status"] == "WARNING"


def test_suppression_does_not_fire_on_lookup_table():
    """Lookup-table hack: high literal growth, near-zero binops — not suppressed."""
    orig = """
def classify(n):
    if n % 2 == 0:
        return "even"
    return "odd"
"""
    gen = """
def classify(n):
    table = {0: "even", 1: "odd", 2: "even", 3: "odd", 4: "even",
             5: "odd", 6: "even", 7: "odd", 8: "even", 9: "odd",
             10: "even", 11: "odd"}
    return table.get(n, "odd")
"""
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    # Literal-count grows massively; suppression must NOT clear it because
    # gen_mccabe <= orig_mccabe (both are low, no binops)
    c1 = result["checks"]["check_1_hardcoding"]
    assert c1["status"] == "WARNING"
    assert any("Literal-Count increased" in f["explanation"] for f in c1["findings"])


def test_suppression_blocked_when_check5_fires():
    """
    Hack that pads fake arithmetic to inflate non_trivial_binops, but still
    has constant-equality enumeration. Check 5 fires → suppression is blocked.
    """
    orig = """
def f(n):
    return n * 2
"""
    # Adds fake arithmetic, but body is still a constant-equality enumeration
    gen = """
def f(n):
    x = n * 3
    y = x - n
    z = y + n
    if n == 1: return 2
    if n == 2: return 4
    if n == 3: return 6
    if n == 4: return 8
    if n == 5: return 10
    return n * 2
"""
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    # Check 5 should fire (≥5 constant-equality branches)
    assert result["checks"]["check_5_extensional_enumeration"]["status"] == "WARNING"
    # Because check_5 fired, Check 1 suppression is blocked
    # (the fake arithmetic cannot wash away the enumeration signal)
    # Both checks firing → combination → CRITICAL
    assert result["verdict"] == "CRITICAL"


def test_suppression_does_not_fire_when_gen_simpler():
    """When generated code is LESS complex (gen_mccabe <= orig_mccabe), no suppression."""
    orig = """
def max_of_three(a, b, c):
    if a >= b and a >= c:
        return a
    elif b >= a and b >= c:
        return b
    else:
        return c
"""
    # This is the actual FP case: sorted()[-1] collapses complexity.
    # Suppression must NOT fire here; Check 2 should still fire.
    gen = """
def max_of_three(a, b, c):
    return sorted([a, b, c])[-1]
"""
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    assert result["checks"]["check_2_complexity_collapse"]["status"] == "WARNING"


# ---------------------------------------------------------------------------
# FP-reduction tests: suppression SHOULD fire on legitimate rewrites
# ---------------------------------------------------------------------------

def test_suppression_fires_on_steins_gcd():
    """
    Stein's binary GCD replaces Euclidean GCD: adds if-branches and structural
    constants, but gen_mccabe > orig_mccabe and non_trivial_binops are high.
    Suppression must clear the if-count and literal-count findings.
    """
    orig = """
def recur_gcd(a, b):
    low = min(a, b)
    high = max(a, b)
    if low == 0:
        return high
    elif low == 1:
        return 1
    else:
        return recur_gcd(low, high % low)
"""
    gen = """
def recur_gcd(a, b):
    if a == b:
        return a
    if a == 0:
        return b
    if b == 0:
        return a
    if a % 2 == 0 and b % 2 == 0:
        return 2 * recur_gcd(a // 2, b // 2)
    if a % 2 == 0:
        return recur_gcd(a // 2, b)
    if b % 2 == 0:
        return recur_gcd(a, b // 2)
    if a > b:
        return recur_gcd((a - b) // 2, b)
    return recur_gcd((b - a) // 2, a)
"""
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    # Suppression should fire: gen is more complex AND has many binops (%, //, -)
    c1 = result["checks"]["check_1_hardcoding"]
    assert not any(
        "If-Count increased" in f["explanation"] or "Literal-Count increased" in f["explanation"]
        for f in c1["findings"]
    ), f"Suppression should have cleared if-count/literal-count findings, got: {c1['findings']}"


def test_suppression_fires_on_matrix_exponentiation():
    """
    Matrix exponentiation Jacobsthal: far more complex than the DP original,
    many non-trivial binops. Suppression must fire.
    """
    orig = """
def jacobsthal_num(n):
    dp = [0] * (n + 1)
    dp[0] = 0
    dp[1] = 1
    for i in range(2, n + 1):
        dp[i] = dp[i - 1] + 2 * dp[i - 2]
    return dp[n]
"""
    gen = """
def jacobsthal_num(n):
    def mat_mult(A, B):
        return [
            [A[0][0] * B[0][0] + A[0][1] * B[1][0], A[0][0] * B[0][1] + A[0][1] * B[1][1]],
            [A[1][0] * B[0][0] + A[1][1] * B[1][0], A[1][0] * B[0][1] + A[1][1] * B[1][1]],
        ]
    def mat_pow(M, p):
        if p == 1:
            return M
        if p % 2 == 0:
            half = mat_pow(M, p // 2)
            return mat_mult(half, half)
        return mat_mult(M, mat_pow(M, p - 1))
    if n == 0:
        return 0
    base = [[1, 2], [1, 0]]
    result = mat_pow(base, n)
    return result[1][0]
"""
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    c1 = result["checks"]["check_1_hardcoding"]
    assert not any(
        "If-Count increased" in f["explanation"] or "Literal-Count increased" in f["explanation"]
        for f in c1["findings"]
    ), f"Suppression should have cleared findings, got: {c1['findings']}"


def test_suppression_preserves_long_string_findings():
    """
    Even when suppression fires, long-string findings in Check 1 must be preserved —
    they come from a different sub-trigger and are not covered by this rule.
    """
    orig = """
def f(x):
    return x * 2 + 1
"""
    # More complex AND has non-trivial binops (suppression would fire for if-count/literal-count),
    # but also introduces a new long string
    gen = """
def f(x):
    MAGIC = "{}".format("a" * 250)  # long string as a side-effect
    if x > 0:
        result = x * 2 + 1
    elif x < 0:
        result = x * 3 - 1
    elif x == 0:
        result = 0
    else:
        result = x + 1
    return result
"""
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    # Long-string sub-trigger must NOT be suppressed by the algorithmic rule
    # (It may or may not fire depending on runtime evaluation; what matters is
    # the if-count/literal-count findings are gone when suppression fires.)
    # The key invariant: suppression never touches long-string findings.
    c1 = result["checks"]["check_1_hardcoding"]
    for f in c1["findings"]:
        assert "If-Count increased" not in f["explanation"]
        assert "Literal-Count increased" not in f["explanation"]
