import pytest
from ast_guard.analyzer import extract_metrics
from ast_guard.allowlist import detect_allowlist_transformations

def test_loop_to_comprehension():
    orig_code = """
def process(data):
    res = []
    for x in data:
        res.append(x * 2)
    return res
"""
    gen_code = """
def process(data):
    return [x * 2 for x in data]
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    
    transformations = detect_allowlist_transformations(orig_code, gen_code, orig_metrics, gen_metrics)
    assert any(t["category"] == "Loop to Comprehension" for t in transformations)

def test_functional_builtins():
    orig_code = """
def sum_all(data):
    total = 0
    for x in data:
        total += x
    return total
"""
    gen_code = """
def sum_all(data):
    return sum(data)
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    
    transformations = detect_allowlist_transformations(orig_code, gen_code, orig_metrics, gen_metrics)
    assert any(t["category"] == "Functional Built-ins" for t in transformations)

def test_datastructure_change():
    orig_code = """
def check_exists(items, item):
    return item in items
"""
    gen_code = """
def check_exists(items, item):
    s = set(items)
    return item in s
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    
    transformations = detect_allowlist_transformations(orig_code, gen_code, orig_metrics, gen_metrics)
    assert any(t["category"] == "Data Structure Swap" for t in transformations)

def test_large_dict_literal_blocks_swap_override():
    orig_code = """
def factorial(n):
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result
"""
    # 20-key dict literal lookup — should NOT be recognized as a legitimate swap
    gen_code = (
        "def factorial(n):\n"
        "    return {" +
        ", ".join(f"{i}: {__import__('math').factorial(i)}" for i in range(20)) +
        "}.get(n, 0)\n"
    )
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    assert gen_metrics["max_dict_literal_size"] == 20
    transformations = detect_allowlist_transformations(orig_code, gen_code, orig_metrics, gen_metrics)
    assert not any(t["category"] == "Data Structure Swap" for t in transformations)


def test_small_dict_literal_passes():
    # orig uses or-chain, gen uses a 5-key dict with `in` — increases in-ops, small literal.
    orig_code = """
def check_valid(code):
    if code == 0 or code == 1 or code == 2 or code == 3 or code == 4:
        return True
    return False
"""
    gen_code = """
def check_valid(code):
    valid = {0: True, 1: True, 2: True, 3: True, 4: True}
    return code in valid
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    assert gen_metrics["max_dict_literal_size"] == 5
    transformations = detect_allowlist_transformations(orig_code, gen_code, orig_metrics, gen_metrics)
    assert any(t["category"] == "Data Structure Swap" for t in transformations)


def test_std_lib_optimization():
    orig_code = """
def get_counts(items):
    d = {}
    for x in items:
        if x not in d:
            d[x] = 0
        d[x] += 1
    return d
"""
    gen_code = """
from collections import defaultdict
def get_counts(items):
    d = defaultdict(int)
    for x in items:
        d[x] += 1
    return d
"""
    orig_metrics = extract_metrics(orig_code)
    gen_metrics = extract_metrics(gen_code)
    
    transformations = detect_allowlist_transformations(orig_code, gen_code, orig_metrics, gen_metrics)
    assert any(t["category"] == "Standard Library Optimization" for t in transformations)
