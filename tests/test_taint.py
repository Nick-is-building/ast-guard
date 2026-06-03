"""
Tests for the intra-file taint pass that backs Check 6 (standalone).

True positives must score at least the threshold given by the spec; true
negatives must remain CLEAN. All cases exercise risk_score_standalone so
the integration in check_behavioral is covered alongside the taint module.
"""
import ast

from ast_guard.check_behavioral import risk_score_standalone
from ast_guard.taint import collect_tainted_names, find_tainted_calls


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _score(code: str) -> dict:
    tree = ast.parse(code)
    return risk_score_standalone(code, tree, {}, "python")


def _patterns(result: dict) -> list:
    # Patterns are embedded in finding explanations after the
    # risk_score_standalone wrapper rewrites them: "[pattern +score] ..."
    # We pull from the raw findings list instead, which keeps the pattern key.
    return [f["pattern"] for f in result["findings"]]


def _assert_pattern_and_score(code: str, expected_pattern: str, min_score: int):
    result = _score(code)
    patterns = _patterns(result)
    assert expected_pattern in patterns, (
        f"Expected pattern {expected_pattern!r} in {patterns}.\n"
        f"Findings: {result['findings']}"
    )
    assert result["score"] >= min_score, (
        f"Expected score >= {min_score}, got {result['score']}.\n"
        f"Findings: {result['findings']}"
    )
    return result


def _assert_no_taint(code: str):
    result = _score(code)
    taint_patterns = [p for p in _patterns(result) if p.startswith("taint")]
    assert not taint_patterns, (
        f"Expected no taint findings, got {taint_patterns}.\n"
        f"Findings: {result['findings']}"
    )


# ===========================================================================
# TRUE POSITIVES — patterns that must score at least the expected minimum
# ===========================================================================

class TestReturnTaint:
    def test_return_sys_exit_then_call(self):
        # def get_exit(): return sys.exit  →  caller invokes the result
        code = (
            "import sys\n"
            "def get_exit():\n"
            "    return sys.exit\n"
            "fn = get_exit()\n"
            "fn(0)\n"
        )
        result = _assert_pattern_and_score(code, "taint_return", min_score=70)
        # The chained alias should also surface a tainted_call.
        assert "tainted_call" in _patterns(result)

    def test_return_os_remove_recursive(self):
        # Recursive taint: a returns b(); b returns os.remove. Fixed-point loop
        # must promote `a` even though `b` is defined after `a`.
        code = (
            "import os\n"
            "def a():\n"
            "    return b()\n"
            "def b():\n"
            "    return os.remove\n"
        )
        result = _assert_pattern_and_score(code, "taint_return", min_score=70)
        names_with_taint = [
            f for f in result["findings"] if f["pattern"] == "taint_return"
        ]
        explanations = " ".join(f["explanation"] for f in names_with_taint)
        # Both function names should be reported as tainted.
        assert "'a'" in explanations and "'b'" in explanations


class TestClassAttrTaint:
    def test_self_assign_then_call(self):
        # class B holds sys.exit as a bound attribute and calls it elsewhere.
        code = (
            "import sys\n"
            "class B:\n"
            "    def __init__(self):\n"
            "        self._e = sys.exit\n"
            "    def run(self):\n"
            "        self._e(0)\n"
        )
        result = _assert_pattern_and_score(code, "taint_class_attr", min_score=50)
        # The self._e(0) call should be flagged as tainted_call too.
        assert "tainted_call" in _patterns(result)


class TestSetattrTaint:
    def test_setattr_imported_module_lambda(self):
        # setattr on time with a lambda — monkey-patching via setattr that the
        # direct-attribute detectors miss.
        code = (
            "import time\n"
            "setattr(time, 'sleep', lambda x: None)\n"
        )
        _assert_pattern_and_score(code, "taint_setattr", min_score=70)

    def test_setattr_third_party_module_with_eval_lambda(self):
        # setattr on a benign-looking module with a lambda that contains eval.
        # Taint pass alone must fire +70; eval_dynamic from existing rules adds
        # more on top.
        code = (
            "import json\n"
            "setattr(json, 'loads', lambda s: eval(s))\n"
        )
        _assert_pattern_and_score(code, "taint_setattr", min_score=70)


class TestClosureTaint:
    def test_inner_uses_outer_forbidden(self):
        # Inner function closes over outer's reference to sys.exit and calls it.
        code = (
            "import sys\n"
            "def outer():\n"
            "    _e = sys.exit\n"
            "    def inner():\n"
            "        _e(0)\n"
            "    inner()\n"
        )
        _assert_pattern_and_score(code, "taint_closure", min_score=50)


class TestGlobalsTaint:
    def test_globals_subscript_aliases_sys_exit(self):
        # g = globals(); g["ex"] = sys.exit  →  later ex(0) reaches sys.exit.
        code = (
            "import sys\n"
            "g = globals()\n"
            "g['ex'] = sys.exit\n"
            "ex(0)\n"
        )
        result = _assert_pattern_and_score(code, "taint_globals", min_score=70)
        assert "tainted_call" in _patterns(result)


# ===========================================================================
# TRUE NEGATIVES — must not trip any taint pattern
# ===========================================================================

class TestNoFalsePositives:
    def test_return_len_is_clean(self):
        # `len` is a benign builtin, not a forbidden module attribute.
        code = (
            "def get_len():\n"
            "    return len\n"
            "fn = get_len()\n"
            "fn([1, 2])\n"
        )
        _assert_no_taint(code)

    def test_self_data_list_is_clean(self):
        code = (
            "class Bag:\n"
            "    def __init__(self):\n"
            "        self.data = []\n"
        )
        _assert_no_taint(code)

    def test_setattr_on_local_object_is_clean(self):
        # `obj` is not an imported module, so setattr should not taint.
        code = (
            "class Holder:\n"
            "    pass\n"
            "obj = Holder()\n"
            "setattr(obj, 'name', 'value')\n"
        )
        _assert_no_taint(code)

    def test_dict_subscript_not_globals(self):
        # g looks like a globals alias but was assigned a plain dict literal.
        code = (
            "g = {}\n"
            "g['key'] = 'value'\n"
        )
        _assert_no_taint(code)

    def test_functools_partial_clean(self):
        # functools.partial wraps a safe builtin — must not be tainted.
        code = (
            "import functools\n"
            "p = functools.partial(print, end='')\n"
            "p('hello')\n"
        )
        _assert_no_taint(code)


# ===========================================================================
# UNIT — collect_tainted_names / find_tainted_calls direct API
# ===========================================================================

class TestTaintModuleAPI:
    def test_collect_return_taint_keys(self):
        code = (
            "import sys\n"
            "def kill():\n"
            "    return sys.exit\n"
        )
        tree = ast.parse(code)
        tainted = collect_tainted_names(tree, {"sys"})
        assert "kill" in tainted
        assert tainted["kill"].source_type == "return"
        assert tainted["kill"].score == 70

    def test_collect_propagation_keeps_source_score(self):
        code = (
            "import sys\n"
            "def kill():\n"
            "    return sys.exit\n"
            "fn = kill()\n"
        )
        tree = ast.parse(code)
        tainted = collect_tainted_names(tree, {"sys"})
        assert "fn" in tainted
        # Propagated entry inherits the source's +70 score.
        assert tainted["fn"].source_type == "propagated"
        assert tainted["fn"].score == 70

    def test_find_tainted_calls_resolves_self_attr(self):
        code = (
            "import sys\n"
            "class B:\n"
            "    def __init__(self):\n"
            "        self._e = sys.exit\n"
            "    def run(self):\n"
            "        self._e(0)\n"
        )
        tree = ast.parse(code)
        tainted = collect_tainted_names(tree, {"sys"})
        calls = find_tainted_calls(tree, tainted)
        keys_hit = {key for _, key, _ in calls}
        assert "B._e" in keys_hit

    def test_empty_tainted_dict_short_circuit(self):
        # No taint sources → find_tainted_calls returns an empty list cheaply.
        code = "print('hello')\n"
        tree = ast.parse(code)
        assert collect_tainted_names(tree, set()) == {}
        assert find_tainted_calls(tree, {}) == []
