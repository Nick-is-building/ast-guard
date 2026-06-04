"""Tests for v1.2 features: constant folding, complexity floor, new obfuscation paths, set-literal blocker, SARIF output."""

import pytest
import ast
import json
from ast_guard.analyzer import extract_metrics, resolve_constant_string, count_set_literals
from ast_guard.checks import check_2_complexity_collapse, check_3_forbidden_calls, get_subscript_string
from ast_guard.allowlist import detect_allowlist_transformations
from ast_guard.output import format_sarif_report
from ast_guard.config import load_effective_config
from ast_guard import scan, scan_standalone

@pytest.fixture
def default_config():
    return load_effective_config()


# --- Constant Folding Tests ---

def test_resolve_constant_string_simple():
    """resolve_constant_string resolves 'ev' + 'al' to 'eval'."""
    code = "'ev' + 'al'"
    tree = ast.parse(code, mode='eval')
    result = resolve_constant_string(tree.body)
    assert result == "eval"

def test_resolve_constant_string_nested():
    """resolve_constant_string handles nested concatenation."""
    code = "'e' + 'v' + 'a' + 'l'"
    tree = ast.parse(code, mode='eval')
    result = resolve_constant_string(tree.body)
    assert result == "eval"

def test_resolve_constant_string_non_string():
    """resolve_constant_string returns None for non-string expressions."""
    code = "1 + 2"
    tree = ast.parse(code, mode='eval')
    result = resolve_constant_string(tree.body)
    assert result is None

def test_check3_constant_folding_subscript(default_config):
    """Check 3 catches __builtins__['ev' + 'al'] via constant folding."""
    orig_code = "pass"
    gen_code = "__builtins__['ev' + 'al']('1+1')"
    
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    gen_tree = ast.parse(gen_code)
    
    res = check_3_forbidden_calls(orig_metrics, gen_metrics, gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("resolved to 'eval'" in f["explanation"] for f in res["findings"])


# --- New Obfuscation Path Tests ---

def test_check3_builtins_dict_access(default_config):
    """Check 3 catches __builtins__.__dict__['eval']."""
    orig_code = "pass"
    gen_code = "__builtins__.__dict__['eval']('1+1')"
    
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    gen_tree = ast.parse(gen_code)
    
    res = check_3_forbidden_calls(orig_metrics, gen_metrics, gen_tree, default_config)
    assert res["status"] == "CRITICAL"

def test_check3_getattr_globals_builtins(default_config):
    """Check 3 catches getattr(globals()['__builtins__'], 'eval')."""
    orig_code = "pass"
    gen_code = "getattr(globals()['__builtins__'], 'eval')('1+1')"
    
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    gen_tree = ast.parse(gen_code)
    
    res = check_3_forbidden_calls(orig_metrics, gen_metrics, gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("getattr() call targeting built-ins" in f["explanation"] for f in res["findings"])


# --- Complexity Floor Tests ---

def test_check2_complexity_floor_blocks_small_functions(default_config):
    """Check 2 does NOT fire when original complexity is below the floor (default: 5)."""
    # Complexity 3 -> 1 (67% drop, exceeds 60% threshold, but below floor of 5)
    orig_code = """
def small(x):
    if x > 0:
        if x > 10:
            return x
    return 0
"""
    gen_code = """
def small(x):
    return max(x, 0)
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    
    res = check_2_complexity_collapse(orig_metrics, gen_metrics, default_config)
    assert res["status"] == "CLEAN"

def test_check2_complexity_floor_allows_large_functions(default_config):
    """Check 2 DOES fire when original complexity meets the floor."""
    # Complexity ~10 -> 2 (80% drop, exceeds both threshold and floor)
    orig_code = """
def process(x):
    if x == 1: return 1
    if x == 2: return 2
    if x == 3: return 3
    if x == 4: return 4
    if x == 5: return 5
    if x == 6: return 6
    if x == 7: return 7
    if x == 8: return 8
    if x == 9: return 9
    return 0
"""
    gen_code = """
def process(x):
    if x > 0:
        return x
    return 0
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    
    res = check_2_complexity_collapse(orig_metrics, gen_metrics, default_config)
    assert res["status"] == "WARNING"


# --- Set Literal Size Blocker Tests ---

def test_set_literal_size_detection():
    """count_set_literals finds the largest set literal."""
    code = """
primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47}
small = {1, 2, 3}
"""
    tree = ast.parse(code)
    assert count_set_literals(tree) == 15

def test_set_literal_blocks_allowlist_override():
    """Large set literal blocks Data Structure Swap allowlist override."""
    orig_code = """
def is_prime(n):
    if n < 2: return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0: return False
    return True
"""
    gen_code = """
def is_prime(n):
    primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97}
    if n <= 100:
        return n in primes
    return True
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    config = load_effective_config()
    
    transformations = detect_allowlist_transformations(orig_code, gen_code, orig_metrics, gen_metrics, config)
    # Data Structure Swap should NOT be in transformations because set has 25 elements > 15 max
    categories = [t["category"] for t in transformations]
    assert "Data Structure Swap" not in categories

def test_small_set_allows_override():
    """Small set literal still allows Data Structure Swap override."""
    orig_code = """
def has_item(items, target):
    for item in items:
        if item == target:
            return True
    return False
"""
    gen_code = """
def has_item(items, target):
    return target in set(items)
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    config = load_effective_config()
    
    transformations = detect_allowlist_transformations(orig_code, gen_code, orig_metrics, gen_metrics, config)
    categories = [t["category"] for t in transformations]
    assert "Data Structure Swap" in categories


# --- SARIF Output Tests ---

def test_sarif_output_structure():
    """SARIF output follows v2.1.0 schema structure."""
    result = scan("x = 1", "eval('1+1')", mode="strict", telemetry_enabled=False)
    sarif_str = format_sarif_report(result)
    sarif = json.loads(sarif_str)

    assert sarif["version"] == "2.1.0"
    assert "$schema" in sarif
    assert len(sarif["runs"]) == 1
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "ast-guard"
    from ast_guard import __version__
    assert sarif["runs"][0]["tool"]["driver"]["version"] == __version__
    assert len(sarif["runs"][0]["tool"]["driver"]["rules"]) == 6

    # partialFingerprints must be present on every result and stable across runs
    # (independent of line numbers, which shift between commits).
    results = sarif["runs"][0]["results"]
    assert len(results) > 0
    for r in results:
        assert "partialFingerprints" in r
        fps = r["partialFingerprints"]
        assert "astGuardFingerprint/v1" in fps
        assert isinstance(fps["astGuardFingerprint/v1"], str)
        assert len(fps["astGuardFingerprint/v1"]) > 0

    # Stability: a second scan produces the same fingerprints.
    sarif2 = json.loads(format_sarif_report(
        scan("x = 1", "eval('1+1')", mode="strict", telemetry_enabled=False)
    ))
    fps1 = [r["partialFingerprints"]["astGuardFingerprint/v1"] for r in results]
    fps2 = [r["partialFingerprints"]["astGuardFingerprint/v1"] for r in sarif2["runs"][0]["results"]]
    assert fps1 == fps2

def test_sarif_output_contains_findings():
    """SARIF results include findings from the scan."""
    result = scan("x = 1", "eval('1+1')", mode="strict", telemetry_enabled=False)
    sarif_str = format_sarif_report(result)
    sarif = json.loads(sarif_str)
    
    results = sarif["runs"][0]["results"]
    assert len(results) > 0
    assert any(r["level"] == "error" for r in results)
    assert any(r["ruleId"] == "ast-guard/check-3-forbidden-calls" for r in results)

def test_sarif_clean_scan_empty_results():
    """SARIF output has empty results for a clean scan."""
    orig = "def f(x): return x + 1"
    gen = "def f(x): return x + 1"
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    sarif_str = format_sarif_report(result)
    sarif = json.loads(sarif_str)

    assert len(sarif["runs"][0]["results"]) == 0


def test_sarif_standalone_rule_ids_are_declared():
    """Every ruleId referenced in SARIF results must resolve to a declared rule.

    Regression for v2.0.x: standalone scans emit check_6_behavioral findings
    whose ruleId previously fell through the _CHECK_KEY_TO_RULE map and ended
    up as the raw check key. GitHub Code Scanning rejects unresolved rule
    references.
    """
    code = "import sys\ndef f():\n    return sys._getframe(1)\n"
    result = scan_standalone(code, mode="strict", telemetry_enabled=False)
    sarif = json.loads(format_sarif_report(result))

    declared = {r["id"] for r in sarif["runs"][0]["tool"]["driver"]["rules"]}
    referenced = {r["ruleId"] for r in sarif["runs"][0]["results"]}

    assert referenced, "Expected at least one Check 6 finding in this fixture"
    assert referenced.issubset(declared), (
        f"Undeclared ruleIds in SARIF output: {referenced - declared}"
    )
    assert "ast-guard/check-6-behavioral" in referenced
