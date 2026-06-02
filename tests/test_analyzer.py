import pytest
from ast_guard.analyzer import extract_metrics

def test_guard_clause_detection():
    # 1. Standard Guard Clauses
    code_with_guards = """
def calc(x):
    '''Some docstring'''
    if x < 0:
        raise ValueError("negative")
    if x == 0:
        return 0
    if x > 10:
        # A normal If inside a non-guard clause (this does not qualify as guard because it is at index 2,
        # but wait, let's see: if_node.body[-1] is not a return/raise, it's print)
        print("large")
    return x + 1
"""
    metrics = extract_metrics(code_with_guards)
    assert metrics["guard_clause_count"] == 2
    assert metrics["if_count"] == 1  # only the if x > 10 counts as normal If

def test_guard_clause_no_docstring():
    # 2. Guard clause without docstring at start of function
    code_no_docstring = """
def calc(x):
    if x < 0:
        return -1
    return x
"""
    metrics = extract_metrics(code_no_docstring)
    assert metrics["guard_clause_count"] == 1
    assert metrics["if_count"] == 0

def test_guard_clause_invalid_position():
    # 3. If at index 3 of adjusted body (not index 0, 1, or 2)
    code_invalid_pos = """
def calc(x):
    '''Docstring'''
    a = 1
    b = 2
    c = 3
    if x < 0:
        return -1
    return x
"""
    metrics = extract_metrics(code_invalid_pos)
    assert metrics["guard_clause_count"] == 0
    assert metrics["if_count"] == 1

def test_guard_clause_with_else():
    # 4. Guard clause with an else branch
    code_with_else = """
def calc(x):
    if x < 0:
        return -1
    else:
        pass
    return x
"""
    metrics = extract_metrics(code_with_else)
    assert metrics["guard_clause_count"] == 0
    assert metrics["if_count"] == 1

def test_guard_clause_not_returning():
    # 5. Guard clause without return/raise as last statement
    code_no_return = """
def calc(x):
    if x < 0:
        print("negative")
    return x
"""
    metrics = extract_metrics(code_no_return)
    assert metrics["guard_clause_count"] == 0
    assert metrics["if_count"] == 1

def test_loop_depth():
    code_loops = """
def process(data):
    for item in data:
        while item > 0:
            item -= 1
"""
    metrics = extract_metrics(code_loops)
    assert metrics["loop_depth"] == 2

    # Excludes comprehensions from loop depth
    code_comp = """
def process(data):
    [x * 2 for x in data]
"""
    metrics = extract_metrics(code_comp)
    assert metrics["loop_depth"] == 0
    assert metrics["comprehension_count"] == 1

def test_mccabe_complexity():
    # McCabe complexity:
    # 1 for function base
    # 1 for 'if'
    # 1 for 'for'
    # 1 for 'and' in BoolOp -> adding 1
    code_mccabe = """
def check_all(items):
    if items and len(items) > 0:
        for x in items:
            pass
"""
    metrics = extract_metrics(code_mccabe)
    # Base = 1
    # 'if' = 1
    # 'and' = 1 (BoolOp with 2 values)
    # 'for' = 1
    # Total = 4
    assert metrics["mccabe_complexity"] == 4

def test_mccabe_match_case():
    # Test ast.Match/case complexity calculation
    code_match = """
def handle_value(v):
    match v:
        case 1:
            return "one"
        case 2:
            return "two"
        case _:
            return "other"
"""
    metrics = extract_metrics(code_match)
    # Base = 1
    # match node itself is 0
    # case 1 = 1
    # case 2 = 1
    # case _ = 1
    # Total = 4
    assert metrics["mccabe_complexity"] == 4

def test_literal_count():
    # Ensure no double counting for Constant dict keys
    code_dict = """
x = {"key1": 123, "key2": 456}
"""
    metrics = extract_metrics(code_dict)
    # Literals should be:
    # "key1", 123, "key2", 456
    # Total = 4 ast.Constants.
    # The dict keys are ast.Constants, so they are not counted twice.
    assert metrics["literal_count"] == 4

    # Dict with dynamic keys
    code_dyn_dict = """
x = {get_key(): 123}
"""
    metrics = extract_metrics(code_dyn_dict)
    # "get_key()" is not ast.Constant.
    # The key is ast.Call, which is not ast.Constant.
    # Thus, "get_key()" counts as 1 non-constant key.
    # 123 is 1 ast.Constant.
    # Total literal_count should be 2.
    assert metrics["literal_count"] == 2

def test_long_string_and_docstrings():
    # Docstrings should be excluded from long string count
    code_with_long_docstring = f'''
def some_func():
    """{"A" * 300}"""
    # Free string
    x = "{"B" * 250}"
    y = "short string"
'''
    metrics = extract_metrics(code_with_long_docstring)
    # The docstring is excluded.
    # Only "B" * 250 is a free long string (> 200 chars).
    # Thus, long_string_count should be 1.
    assert metrics["long_string_count"] == 1

def test_imports_and_calls():
    code_imports_calls = """
import os
import sys as s
from os import path
from collections import Counter

def do_work():
    os.path.join("a", "b")
    get_data().action()
    map(lambda x: x + 1, [1, 2, 3])
"""
    metrics = extract_metrics(code_imports_calls)
    
    # Imports:
    # import os -> 'os'
    # import sys as s -> 'sys' (wait, the alias is s, but alias.name is 'sys')
    # from os import path -> 'os', 'os.path'
    # from collections import Counter -> 'collections', 'collections.Counter'
    expected_imports = {"os", "sys", "os.path", "collections", "collections.Counter"}
    assert set(metrics["import_list"]) == expected_imports
    
    # Calls:
    # os.path.join -> resolved to 'os.path.join'
    # get_data().action() -> base is a Call node (unresolvable) → returns None, excluded
    #   The inner get_data() -> Name('get_data') -> 'get_data'
    # map(...) -> Name('map') -> 'map'
    assert "os.path.join" in metrics["call_list"]
    assert "get_data" in metrics["call_list"]
    assert "action" not in metrics["call_list"]  # dynamic base → excluded (avoids .eval() false positives)
    assert "map" in metrics["call_list"]

    # Functional calls:
    # 'map' is a functional call
    assert metrics["functional_call_count"] == 1


def test_build_lineno_index_perf():
    """build_lineno_index must be at least 2x faster than a per-call inline ast.walk for 200 calls."""
    import ast
    import time
    from ast_guard.analyzer import build_lineno_index, resolve_call_name

    # Synthetic 500-LOC file with 200 distinct function calls
    lines = ["def dummy(): pass"]
    for i in range(200):
        lines.append(f"func_{i}(arg_{i})")
    # Pad to 500 lines
    for i in range(500 - len(lines)):
        lines.append(f"x_{i} = {i}")
    code = "\n".join(lines)
    tree = ast.parse(code)
    call_names = [f"func_{i}" for i in range(200)]

    def old_lookup(tree, call_name):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and resolve_call_name(node.func) == call_name:
                return getattr(node, "lineno", None)
        return None

    # Baseline: inline walk per call (old approach)
    t0 = time.perf_counter()
    for name in call_names:
        old_lookup(tree, name)
    old_time = time.perf_counter() - t0

    # New approach: build index once, then O(1) lookups
    t0 = time.perf_counter()
    idx = build_lineno_index(tree)
    for name in call_names:
        idx["calls"].get(name)
    new_time = time.perf_counter() - t0

    assert new_time < old_time / 2, (
        f"build_lineno_index not 2x faster: new={new_time:.4f}s old={old_time:.4f}s"
    )
