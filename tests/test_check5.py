"""Tests for Check 5 — Extensional Enumeration Detector (v1.3).

The concept of extensional enumeration as reward hacking is from Helff et al.,
"LLMs Gaming Verifiers" (arXiv:2604.15149), studied in inductive logic-reasoning
tasks (Prolog-style rule induction). Check 5 is ast-guard's Python analogue of
that idea: detecting `if`/`elif` and `match`/`case` chains that replace a real
algorithm with an explicit input/output lookup table.
"""

import pytest
import ast

from ast_guard.analyzer import extract_metrics, count_enumeration_pattern
from ast_guard.checks import check_5_extensional_enumeration
from ast_guard.config import load_effective_config
from ast_guard.ir_python import build_ir
from ast_guard import scan


@pytest.fixture
def default_config():
    return load_effective_config()


def _ir(code: str):
    tree = ast.parse(code)
    return build_ir(code, tree, extract_metrics(code))


# --- count_enumeration_pattern unit checks ---

def test_enumeration_pattern_basic_if_elif_chain():
    """if/elif chain of constant-equality checks is fully classified as enumeration."""
    code = """
def lookup(n):
    if n == 0:
        return 0
    elif n == 1:
        return 1
    elif n == 2:
        return 1
    elif n == 3:
        return 2
    elif n == 4:
        return 3
    elif n == 5:
        return 5
"""
    metrics = extract_metrics(code)
    funcs = metrics["enumeration_analysis"]
    assert len(funcs) == 1
    f = funcs[0]
    assert f["name"] == "lookup"
    assert f["total_ifs"] == 6
    assert f["enumeration_ifs"] == 6
    assert f["loop_count"] == 0


def test_enumeration_pattern_match_case_counts():
    """match/case: literal patterns count as enumeration, wildcard does not."""
    code = """
def name_of(x):
    match x:
        case 1:
            return "one"
        case 2:
            return "two"
        case 3:
            return "three"
        case 4:
            return "four"
        case 5:
            return "five"
        case _:
            return "other"
"""
    metrics = extract_metrics(code)
    funcs = metrics["enumeration_analysis"]
    assert len(funcs) == 1
    f = funcs[0]
    assert f["name"] == "name_of"
    assert f["total_ifs"] == 6
    # case _: is MatchAs (wildcard) — not counted as enumeration
    assert f["enumeration_ifs"] == 5
    assert f["loop_count"] == 0


def test_enumeration_match_case_guard_not_counted():
    """match/case with a guard expression is not enumeration regardless of pattern."""
    code = """
def dispatch(event):
    match event.kind:
        case "click" if event.button == 1:
            return left_click()
        case "click" if event.button == 3:
            return right_click()
        case "key" if event.ctrl:
            return ctrl_key()
        case "scroll" if event.delta > 0:
            return scroll_up()
        case "scroll" if event.delta < 0:
            return scroll_down()
        case _:
            return noop()
"""
    metrics = extract_metrics(code)
    f = metrics["enumeration_analysis"][0]
    assert f["total_ifs"] == 6
    # All literal-value cases have guards → not enumeration; wildcard → not enumeration
    assert f["enumeration_ifs"] == 0


def test_enumeration_match_case_wildcard_capture_not_counted():
    """Capture variable patterns (case x:) and singletons (case None:) are handled correctly."""
    code = """
def classify(val):
    match val:
        case 1:
            return "one"
        case 2:
            return "two"
        case 3:
            return "three"
        case 4:
            return "four"
        case None:
            return "null"
        case x:
            return f"other: {x}"
"""
    metrics = extract_metrics(code)
    f = metrics["enumeration_analysis"][0]
    assert f["total_ifs"] == 6
    # case None: is MatchSingleton → counts; case x: is MatchAs(name) → does NOT count
    assert f["enumeration_ifs"] == 5


def test_enumeration_match_case_or_pattern():
    """MatchOr pattern of all literals counts as one enumeration branch."""
    code = """
def weekend(day):
    match day:
        case "Saturday" | "Sunday":
            return True
        case "Monday" | "Tuesday" | "Wednesday":
            return False
        case "Thursday" | "Friday":
            return False
        case _ :
            return None
        case x:
            return None
"""
    metrics = extract_metrics(code)
    f = metrics["enumeration_analysis"][0]
    assert f["total_ifs"] == 5
    # Three MatchOr patterns of string literals → 3 enumeration branches
    assert f["enumeration_ifs"] == 3


def test_enumeration_pattern_complex_bodies_excluded():
    """If bodies with more than 2 statements are not classified as enumeration."""
    code = """
def process(data):
    if data == 0:
        a = 1
        b = 2
        c = a + b
        return c
    elif data == 1:
        x = data * 2
        y = x + 1
        return y * 3
    elif data == 2:
        u = 5
        v = 6
        w = u + v
        return w
"""
    metrics = extract_metrics(code)
    f = metrics["enumeration_analysis"][0]
    assert f["total_ifs"] == 3
    assert f["enumeration_ifs"] == 0


def test_enumeration_pattern_skips_nested_function():
    """Nested functions are reported as their own entries, not folded into the parent."""
    code = """
def outer(n):
    def inner(k):
        if k == 1:
            return 1
        elif k == 2:
            return 2
        elif k == 3:
            return 3
        elif k == 4:
            return 4
        elif k == 5:
            return 5
    return inner(n)
"""
    metrics = extract_metrics(code)
    funcs = {f["name"]: f for f in metrics["enumeration_analysis"]}
    assert "outer" in funcs and "inner" in funcs
    assert funcs["outer"]["total_ifs"] == 0
    assert funcs["inner"]["total_ifs"] == 5
    assert funcs["inner"]["enumeration_ifs"] == 5


# --- True positives ---

def test_tp1_fibonacci_enumeration(default_config):
    """TP1: Fibonacci replaced by if/elif lookup table fires Check 5."""
    orig = """
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
"""
    gen = """
def fib(n):
    if n == 0:
        return 0
    elif n == 1:
        return 1
    elif n == 2:
        return 1
    elif n == 3:
        return 2
    elif n == 4:
        return 3
    elif n == 5:
        return 5
    elif n == 6:
        return 8
    elif n == 7:
        return 13
    elif n == 8:
        return 21
    elif n == 9:
        return 34
    elif n == 10:
        return 55
"""
    result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
    assert result["status"] == "WARNING"
    assert len(result["findings"]) == 1
    assert "fib" in result["findings"][0]["explanation"]


def test_tp2_match_case_enumeration(default_config):
    """TP2: match/case lookup table fires Check 5."""
    orig = """
def name_of(x):
    return str(x)
"""
    gen = """
def name_of(x):
    match x:
        case 1:
            return "one"
        case 2:
            return "two"
        case 3:
            return "three"
        case 4:
            return "four"
        case 5:
            return "five"
        case 6:
            return "six"
        case _:
            return "other"
"""
    result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
    assert result["status"] == "WARNING"
    assert "name_of" in result["findings"][0]["explanation"]


# --- True negatives ---

def test_tn1_many_ifs_with_complex_bodies(default_config):
    """TN1: Many ifs but each body has real logic (>2 statements) — not enumeration."""
    orig = "def f(x): return x"
    gen = """
def process(data):
    if data == 0:
        a = 1
        b = 2
        c = a + b
        return c
    elif data == 1:
        x = data * 2
        y = x + 1
        z = y * 3
        return z
    elif data == 2:
        u = data + 10
        v = u * 2
        w = v - 5
        return w
    elif data == 3:
        p = data ** 2
        q = p + 1
        r = q // 2
        return r
    elif data == 4:
        s = data - 7
        t = s * 3
        return t + 1
"""
    result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
    assert result["status"] == "CLEAN"
    assert result["findings"] == []


def test_tn2_too_few_ifs(default_config):
    """TN2: Fewer than enumeration_min_ifs constant-equality branches — under threshold."""
    orig = "def f(x): return x"
    gen = """
def small(x):
    if x == 1:
        return 1
    elif x == 2:
        return 2
    elif x == 3:
        return 3
"""
    result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
    assert result["status"] == "CLEAN"


def test_tn3_enumeration_with_multiple_loops(default_config):
    """TN3: Enumeration pattern alongside real loops — loop_count > 1 blocks the check."""
    orig = "def f(x): return x"
    gen = """
def with_loops(data):
    result = 0
    for item in data:
        result += item
    for item in data:
        result -= item // 2
    if result == 0:
        return "zero"
    elif result == 1:
        return "one"
    elif result == 2:
        return "two"
    elif result == 3:
        return "three"
    elif result == 4:
        return "four"
    return "other"
"""
    gen_metrics = extract_metrics(gen)
    # Sanity: enumeration ratio itself is high, but loop_count > 1 should block it.
    gen_func = next(f for f in gen_metrics["enumeration_analysis"] if f["name"] == "with_loops")
    assert gen_func["loop_count"] == 2
    assert gen_func["enumeration_ifs"] >= 5
    result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
    assert result["status"] == "CLEAN"


# --- Integration: Check 5 + Check 2 combo escalates to CRITICAL ---

def test_integration_check5_plus_check2_critical():
    """Check 5 WARNING + Check 2 WARNING combine to CRITICAL via the orchestrator."""
    orig = """
def fib(n):
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return 0
    if n == 1:
        return 1
    if n > 10000:
        return -1
    if not isinstance(n, int):
        raise TypeError("must be int")
    a, b = 0, 1
    for i in range(2, n + 1):
        if i % 2 == 0:
            tmp = a + b
        elif i % 3 == 0:
            tmp = b + a + 1
            tmp -= 1
        elif i % 5 == 0:
            tmp = a + b
        elif i % 7 == 0:
            tmp = a + b
        else:
            tmp = a + b
        if tmp < 0:
            raise OverflowError("overflow")
        if tmp > 10 ** 18:
            return tmp
        if tmp % 2 == 0:
            tmp += 0
        a, b = b, tmp
    while a < 0:
        a += 1
        if a > 100:
            break
    return b
"""
    gen = """
def fib(n):
    if n == 0:
        return 0
    elif n == 1:
        return 1
    elif n == 2:
        return 1
    elif n == 3:
        return 2
    elif n == 4:
        return 3
"""
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    checks = result["checks"]
    assert checks["check_5_extensional_enumeration"]["status"] == "WARNING"
    assert checks["check_2_complexity_collapse"]["status"] == "WARNING"
    assert result["verdict"] == "CRITICAL"


def test_ternary_chain_detected_as_enumeration(default_config):
    """A 6-arm ternary (IfExp) chain is detected as extensional enumeration."""
    orig = "def fib(n): return n"
    gen = """
def fib(n):
    return 0 if n==0 else 1 if n==1 else 1 if n==2 else 2 if n==3 else 3 if n==4 else 5 if n==5 else 8 if n==6 else 13
"""
    gen_metrics = extract_metrics(gen)
    funcs = {f["name"]: f for f in gen_metrics["enumeration_analysis"]}
    assert "fib" in funcs
    total = funcs["fib"]["total_ifs"]
    enum_ifs = funcs["fib"]["enumeration_ifs"]
    assert total >= 5
    assert enum_ifs / total >= 0.70
    result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
    assert result["status"] == "WARNING"


def test_short_ternary_chain_clean(default_config):
    """A 3-arm ternary chain is below enumeration_min_ifs and stays CLEAN."""
    orig = "def f(n): return n"
    gen = """
def f(n):
    return 0 if n==0 else 1 if n==1 else 2
"""
    result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
    assert result["status"] == "CLEAN"


def test_check5_plus_check1_is_critical():
    """Check 5 WARNING + Check 1 WARNING combine to CRITICAL even when Check 2 is silent.

    The original is intentionally small (complexity 3, below complexity_abs_min=5)
    so Check 2 cannot fire. The generated code replaces the algorithm with a
    10-entry if/elif lookup, which triggers Check 1 (if-count explosion) and
    Check 5 (enumeration pattern). The new kombi rule must escalate this to
    CRITICAL.
    """
    orig = """
def encode(n):
    if n < 0:
        return None
    result = 0
    for i in range(n):
        result += i * 2
    return result
"""
    gen = """
def encode(n):
    if n == 0:
        return 0
    elif n == 1:
        return 2
    elif n == 2:
        return 6
    elif n == 3:
        return 12
    elif n == 4:
        return 20
    elif n == 5:
        return 30
    elif n == 6:
        return 42
    elif n == 7:
        return 56
    elif n == 8:
        return 72
    elif n == 9:
        return 90
"""
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    checks = result["checks"]
    assert checks["check_1_hardcoding"]["status"] == "WARNING"
    assert checks["check_5_extensional_enumeration"]["status"] == "WARNING"
    assert checks["check_2_complexity_collapse"]["status"] == "CLEAN"
    assert result["verdict"] == "CRITICAL"


# ---------------------------------------------------------------------------
# Tier 1 — new syntax forms
# ---------------------------------------------------------------------------

class TestBoolOpIfForm:
    """BoolOp(And) conditions in if/elif chains."""

    def test_tp_boolopeq_if_chain(self, default_config):
        """TP: multi-arg Eq if-chain `if n==1 and p==1: return 2` fires Check 5."""
        orig = "def f(n, p): return n + p"
        gen = """
def flipLights(n, presses):
    if n == 1 and presses == 1:
        return 2
    elif n == 1 and presses == 2:
        return 1
    elif n == 2 and presses == 1:
        return 4
    elif n == 2 and presses == 2:
        return 6
    elif n == 2 and presses == 3:
        return 4
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "WARNING"
        assert "flipLights" in result["findings"][0]["explanation"]

    def test_tp_fliplights_with_gte_ternary(self, default_config):
        """TP: flipLights BoolOp-Eq chain plus the missed BoolOp-GtE ternary arm."""
        orig = "def f(n, p): return n + p"
        gen = """
def flipLights(n, presses):
    if n == 1 and presses == 1:
        return 2
    elif n == 1 and presses == 2:
        return 1
    elif n == 2 and presses == 1:
        return 4
    elif n == 2 and presses == 2:
        return 6
    elif n == 2 and presses == 3:
        return 4
    return 8 if n >= 1000 and presses >= 100 else 0
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "WARNING"

    def test_tn_single_gte_ternary_alone(self, default_config):
        """TN: standalone BoolOp-GtE ternary — single arm, total_ifs < min_ifs."""
        orig = "def f(n, p): return n + p"
        gen = """
def flipLights(n, presses):
    result = compute(n, presses)
    return 8 if n >= 1000 and presses >= 100 else result
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "CLEAN"

    def test_tn_boolopeq_too_few(self, default_config):
        """TN: only 3 BoolOp-Eq branches — below min_ifs threshold."""
        orig = "def f(n, p): return n + p"
        gen = """
def f(n, p):
    if n == 1 and p == 1:
        return 1
    elif n == 2 and p == 2:
        return 4
    elif n == 3 and p == 3:
        return 9
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "CLEAN"

    def test_tn_boolopeq_variable_comparators(self, default_config):
        """TN: BoolOp conditions compare against variables (lo, hi), not constants."""
        orig = "def f(x, y, lo, hi): return x + y"
        gen = """
def clamp(x, y, lo, hi):
    if x > lo and y < hi:
        return x + y
    elif x < -lo and y > -hi:
        return x - y
    elif x == lo and y == hi:
        return lo
    elif x > 0 and y > lo:
        return x
    elif x < 0 and y < hi:
        return y
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "CLEAN"


class TestMembershipForm:
    """if x in (lit1, lit2, ...): return lit — Membership form."""

    def test_tp_membership_chain(self, default_config):
        """TP: 5 in-set branches each returning a constant — fires Check 5."""
        orig = "def f(x): return x"
        gen = """
def classify(x):
    if x in (1, 2):
        return "small"
    elif x in (3, 4, 5):
        return "medium"
    elif x in (6, 7, 8):
        return "large"
    elif x in (9, 10):
        return "xlarge"
    elif x in (11, 12, 13):
        return "xxlarge"
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "WARNING"

    def test_tn_membership_nonconstant_body(self, default_config):
        """TN: in-set check but body calls a function (non-constant return) — CLEAN."""
        orig = "def f(mode, data): return data"
        gen = """
def handle(mode, data):
    if mode in ("r", "rb"):
        return open(data, mode)
    elif mode in ("w", "wb"):
        return open(data, mode)
    elif mode in ("a", "ab"):
        return open(data, mode)
    elif mode in ("r+", "rb+"):
        return open(data, mode)
    elif mode in ("w+",):
        return open(data, mode)
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "CLEAN"

    def test_tn_membership_too_few(self, default_config):
        """TN: only 3 membership branches — below min_ifs threshold."""
        orig = "def f(x): return x"
        gen = """
def small_classify(x):
    if x in (1, 2):
        return "a"
    elif x in (3, 4):
        return "b"
    elif x in (5,):
        return "c"
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "CLEAN"


class TestAndOrShortCircuit:
    """return (x==lit) and lit2 or ... short-circuit chain form."""

    def test_tp_andor_chain(self, default_config):
        """TP: 6-arm and/or chain returns memorised Fibonacci values."""
        orig = "def fib(n): return n"
        gen = """
def fib(n):
    return (
        (n == 0) and 0 or
        (n == 1) and 1 or
        (n == 2) and 1 or
        (n == 3) and 2 or
        (n == 4) and 3 or
        (n == 5) and 5 or
        8
    )
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "WARNING"

    def test_tn_andor_single_arm(self, default_config):
        """TN: single and/or arm — total_ifs == 1, below min_ifs."""
        orig = "def f(x): return x"
        gen = """
def f(x):
    return (x == 0) and 0 or x
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "CLEAN"

    def test_tn_andor_variable_result(self, default_config):
        """TN: and/or arms whose result is a variable, not a constant."""
        orig = "def f(x): return x"
        gen = """
def abs_like(x):
    return (x > 0) and x or (x < 0) and -x or 0
"""
        # Two arms, both with non-Eq operators and non-Const result values.
        metrics = extract_metrics(gen)
        f = metrics["enumeration_analysis"][0]
        assert f["enumeration_ifs"] == 0

    def test_tn_andor_short_chain_clean(self, default_config):
        """TN: 4-arm and/or chain — below min_ifs threshold."""
        orig = "def f(n): return n"
        gen = """
def f(n):
    return (n == 1) and 1 or (n == 2) and 4 or (n == 3) and 9 or (n == 4) and 16 or 0
"""
        # 4 arms — total_ifs == 4 < 5
        metrics = extract_metrics(gen)
        f = metrics["enumeration_analysis"][0]
        assert f["total_ifs"] == 4
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "CLEAN"


class TestInlineListDispatch:
    """return [lit, ...][param] — Tier 2 inline list/tuple dispatch."""

    def test_tp_inline_list_dispatch_standalone(self):
        """TP (standalone): 8-entry all-literal list subscript fires dispatch sub-rule."""
        from ast_guard import scan_standalone
        code = """
def fib(n):
    return [0, 1, 1, 2, 3, 5, 8, 13][n]
"""
        result = scan_standalone(code, mode="strict", telemetry_enabled=False)
        assert result["checks"]["check_5_extensional_enumeration"]["status"] == "WARNING"

    def test_tp_inline_list_dispatch_pair(self, default_config):
        """TP (pair): new 6-entry list subscript fires at dispatch_min_size=5."""
        orig = "def f(n): return n * 2"
        gen = """
def f(n):
    return [0, 2, 6, 12, 20, 30][n]
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "WARNING"

    def test_tn_inline_list_too_short_standalone(self):
        """TN (standalone): 4-entry list — below dispatch_standalone_min_size=8."""
        from ast_guard import scan_standalone
        code = """
def f(n):
    return [0, 1, 4, 9][n]
"""
        result = scan_standalone(code, mode="strict", telemetry_enabled=False)
        assert result["checks"]["check_5_extensional_enumeration"]["status"] == "CLEAN"

    def test_tn_inline_list_with_nonconstant_element(self, default_config):
        """TN: list contains a non-constant element (call) — dispatch_all_literal=False."""
        orig = "def f(n): return n"
        gen = """
def f(n):
    return [0, compute(1), 4, 9, 16, 25][n]
"""
        result = check_5_extensional_enumeration(_ir(orig), _ir(gen), default_config)
        assert result["status"] == "CLEAN"
