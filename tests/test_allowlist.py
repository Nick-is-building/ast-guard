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
