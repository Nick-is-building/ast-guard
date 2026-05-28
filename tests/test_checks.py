import pytest
import ast
from ast_guard.analyzer import extract_metrics
from ast_guard.checks import check_1_hardcoding, check_2_complexity_collapse, check_3_forbidden_calls, check_4_import_drift
from ast_guard.config import load_effective_config

@pytest.fixture
def default_config():
    return load_effective_config()

def test_check1_if_count_increase(default_config):
    orig_code = """
def process(data):
    for x in data:
        if x > 0:
            print(x)
        else:
            print(0)
"""
    gen_code = """
def process(data):
    for x in data:
        if x == 1:
            print(1)
        else:
            pass
        if x == 2:
            print(2)
        else:
            pass
        if x > 0:
            print(x)
        else:
            print(0)
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    
    orig_tree = ast.parse(orig_code)
    gen_tree = ast.parse(gen_code)
    
    res = check_1_hardcoding(orig_metrics, gen_metrics, orig_tree, gen_tree, default_config)
    assert res["status"] == "WARNING"
    assert any("If-Count increased" in f["explanation"] for f in res["findings"])

def test_check1_literal_count_increase(default_config):
    orig_code = "x = 1"
    gen_code = "x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]" # 12 literals (increase of 11, >200% and >=10)
    
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    
    orig_tree = ast.parse(orig_code)
    gen_tree = ast.parse(gen_code)
    
    res = check_1_hardcoding(orig_metrics, gen_metrics, orig_tree, gen_tree, default_config)
    assert res["status"] == "WARNING"
    assert any("Literal-Count increased" in f["explanation"] for f in res["findings"])

def test_check1_long_string(default_config):
    orig_code = "x = 'short'"
    long_str = "a" * 250
    gen_code = f"x = '{long_str}'"
    
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    
    orig_tree = ast.parse(orig_code)
    gen_tree = ast.parse(gen_code)
    
    res = check_1_hardcoding(orig_metrics, gen_metrics, orig_tree, gen_tree, default_config)
    assert res["status"] == "WARNING"
    assert any("New long string constant" in f["explanation"] for f in res["findings"])

def test_check2_complexity_collapse(default_config):
    # Complexity 10
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
    # Complexity 2 (collapse of 80%)
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
    # v1.3: per-function finding mentions the function's qualified name
    assert any(
        "McCabe complexity for function 'process' collapsed" in f["explanation"]
        for f in res["findings"]
    )

def test_check3_diff_based_forbidden_calls(default_config):
    # If os was already in original, it shouldn't trigger in gen code
    orig_code = """
import os
os.system("ls")
"""
    gen_code = """
import os
os.system("ls")
# but adding a new forbidden call like eval should trigger
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    gen_tree = ast.parse(gen_code)
    
    res = check_3_forbidden_calls(orig_metrics, gen_metrics, gen_tree, default_config)
    assert res["status"] == "CLEAN"  # No new forbidden call
    
    # Now adding a new forbidden call
    gen_code_with_eval = gen_code + "\neval('1+1')"
    gen_metrics_eval = extract_metrics(gen_code_with_eval)
    gen_tree_eval = ast.parse(gen_code_with_eval)
    
    res2 = check_3_forbidden_calls(orig_metrics, gen_metrics_eval, gen_tree_eval, default_config)
    assert res2["status"] == "CRITICAL"
    assert any("forbidden call 'eval'" in f["explanation"] for f in res2["findings"])

def test_check3_obfuscation_assign(default_config):
    orig_code = "pass"
    gen_code = """
f = eval
f("1+1")
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    gen_tree = ast.parse(gen_code)
    
    res = check_3_forbidden_calls(orig_metrics, gen_metrics, gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("Obfuscation attempt: Forbidden name 'eval' is aliased" in f["explanation"] for f in res["findings"])

def test_check3_obfuscation_builtins(default_config):
    orig_code = "pass"
    # Subscript builtins
    gen_code1 = "__builtins__['eval']('1+1')"
    # Attribute builtins
    gen_code2 = "__builtins__.eval('1+1')"
    # getattr on builtins
    gen_code3 = "getattr(__builtins__, 'eval')"
    
    for gcode in (gen_code1, gen_code2, gen_code3):
        orig_metrics = extract_metrics(orig_code)
        gen_metrics = extract_metrics(gcode)
        gen_tree = ast.parse(gcode)
        
        res = check_3_forbidden_calls(orig_metrics, gen_metrics, gen_tree, default_config)
        assert res["status"] == "CRITICAL"

def test_check3_chr_heuristic(default_config):
    orig_code = "pass"
    gen_code = "eval(chr(111)+chr(115))"
    
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    gen_tree = ast.parse(gen_code)
    
    res = check_3_forbidden_calls(orig_metrics, gen_metrics, gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("chr() call used inside" in f["explanation"] for f in res["findings"])

def test_check4_import_drift(default_config):
    orig_code = "import math"
    
    # 1. Blocklisted (CRITICAL)
    gen_code_ctypes = """
import math
import ctypes
"""
    res1 = check_4_import_drift(extract_metrics(orig_code), extract_metrics(gen_code_ctypes), default_config)
    assert res1["status"] == "CRITICAL"
    
    # 2. Allowlisted (CLEAN)
    gen_code_collections = """
import math
import collections
"""
    res2 = check_4_import_drift(extract_metrics(orig_code), extract_metrics(gen_code_collections), default_config)
    assert res2["status"] == "CLEAN"
    
    # 3. Unrecognized (WARNING)
    gen_code_requests = """
import math
import requests
"""
    res3 = check_4_import_drift(extract_metrics(orig_code), extract_metrics(gen_code_requests), default_config)
    assert res3["status"] == "WARNING"


def test_check2_rename_bypass(default_config):
    """Check 2 catches complexity collapse even when the function is renamed.

    Before the fix: orig_funcs={"factorial"}, gen_funcs={"fact"}, intersection
    empty → per-function loop did nothing AND the file-level fallback was
    skipped (because both sides have functions). Check 2 silently returned
    CLEAN. Now a file-level fallback fires when both sides have functions
    but share no qualified names.
    """
    orig_code = """
def factorial(n):
    if n < 0:
        raise ValueError("negative")
    if n == 0:
        return 1
    result = 1
    for i in range(1, n + 1):
        if i % 2 == 0:
            result *= i
        elif i % 3 == 0:
            result *= i * 2
        else:
            result *= i
    return result
"""
    gen_code = """
def fact(n):
    return 1
"""
    res = check_2_complexity_collapse(
        extract_metrics(orig_code), extract_metrics(gen_code), default_config
    )
    assert res["status"] == "WARNING"
    assert any(
        "falling back to file-level comparison" in f["explanation"]
        for f in res["findings"]
    )


def test_check3_builtins_module_eval(default_config):
    """Check 3 catches `builtins.eval(...)` even when `import builtins`
    was already legitimately present in the original code.
    """
    orig_code = "import builtins\n"
    gen_code = "import builtins\nbuiltins.eval('1+1')\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(
        extract_metrics(orig_code), extract_metrics(gen_code), gen_tree, default_config
    )
    assert res["status"] == "CRITICAL"
