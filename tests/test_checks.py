import pytest
import ast
from ast_guard.analyzer import extract_metrics, resolve_call_name
from ast_guard.checks import check_1_hardcoding, check_2_complexity_collapse, check_3_forbidden_calls, check_4_import_drift
from ast_guard.config import load_effective_config
from ast_guard.ir_python import build_ir

@pytest.fixture
def default_config():
    return load_effective_config()


def _ir(code: str):
    tree = ast.parse(code)
    return build_ir(code, tree, extract_metrics(code))


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
    res = check_1_hardcoding(_ir(orig_code), _ir(gen_code), default_config)
    assert res["status"] == "WARNING"
    assert any("If-Count increased" in f["explanation"] for f in res["findings"])

def test_check1_literal_count_increase(default_config):
    orig_code = "x = 1"
    gen_code = "x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]" # 12 literals (increase of 11, >200% and >=10)

    res = check_1_hardcoding(_ir(orig_code), _ir(gen_code), default_config)
    assert res["status"] == "WARNING"
    assert any("Literal-Count increased" in f["explanation"] for f in res["findings"])

def test_check1_long_string(default_config):
    orig_code = "x = 'short'"
    long_str = "a" * 250
    gen_code = f"x = '{long_str}'"

    res = check_1_hardcoding(_ir(orig_code), _ir(gen_code), default_config)
    assert res["status"] == "WARNING"
    assert any("New long string constant" in f["explanation"] for f in res["findings"])


def test_check1_long_string_natural_text_filtered(default_config):
    """Prompt templates / docstring-like text must not trigger check_1."""
    orig_code = "x = 'short'"
    prompt = (
        "You are an expert assistant. I want you to create a function that "
        "takes a list of integers and returns the sum of the even numbers. "
        "Make sure to handle edge cases such as empty lists, lists with no "
        "even numbers, and lists containing negative integers. Use clear "
        "variable names and add a short docstring describing the behavior."
    )
    assert len(prompt) > 200
    gen_code = f"x = {prompt!r}"

    res = check_1_hardcoding(_ir(orig_code), _ir(gen_code), default_config)
    assert not any("New long string constant" in f["explanation"] for f in res["findings"])


def test_check1_long_string_binary_blob_filtered(default_config):
    """Pure hex/base64 blobs (ciphertext, binary data) must not trigger check_1."""
    orig_code = "x = 'short'"
    # ELF-header-like hex blob with both digits and letters
    hex_blob = "7f454c460201010000" * 20  # 360 chars
    gen_code = f"x = '{hex_blob}'"

    res = check_1_hardcoding(_ir(orig_code), _ir(gen_code), default_config)
    assert not any("New long string constant" in f["explanation"] for f in res["findings"])


def test_check1_long_string_packed_lookup_still_fires(default_config):
    """Pipe-separated lookup tables (TRACE String-Concat-Abuse) must still fire.

    Same structural pattern as the CAT_03 sample in benchmarks/structural_benchmark."""
    orig_code = "x = 'short'"
    table = (
        "|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        "thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
        "twenty|twenty-one|twenty-two|twenty-three|twenty-four|twenty-five|"
        "twenty-six|twenty-seven|twenty-eight|twenty-nine|thirty"
    )
    assert len(table) > 200
    gen_code = f"x = '{table}'"

    res = check_1_hardcoding(_ir(orig_code), _ir(gen_code), default_config)
    assert any("New long string constant" in f["explanation"] for f in res["findings"])


def test_check1_long_string_numeric_sequence_filtered(default_config):
    """Comma-/space-separated numeric data must not trigger check_1.

    CSV output, space-delimited numbers, and similar numeric sequences are
    common in data-processing code and are not answer-lookup patterns."""
    orig_code = "x = 'short'"
    # Comma-separated numbers — typical when generating CSV output inline
    csv_data = ",".join(str(i * 17 + 3) for i in range(60))  # > 200 chars
    assert len(csv_data) > 200
    gen_code = f"x = '{csv_data}'"

    res = check_1_hardcoding(_ir(orig_code), _ir(gen_code), default_config)
    assert not any("New long string constant" in f["explanation"] for f in res["findings"])


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
    res = check_2_complexity_collapse(_ir(orig_code), _ir(gen_code), default_config)
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
    gen_tree = ast.parse(gen_code)

    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CLEAN"  # No new forbidden call

    # Now adding a new forbidden call
    gen_code_with_eval = gen_code + "\neval('1+1')"
    gen_tree_eval = ast.parse(gen_code_with_eval)

    res2 = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code_with_eval), gen_tree_eval, default_config)
    assert res2["status"] == "CRITICAL"
    assert any("forbidden call 'eval'" in f["explanation"] for f in res2["findings"])

def test_check3_raise_system_exit(default_config):
    # raise SystemExit(0) terminates the process without importing sys/os.
    # Without SystemExit in exact_blocked, this would slip through Check 3.
    orig_code = """
def compute(n):
    return n * n
"""
    gen_code = """
def compute(n):
    result = n * n
    raise SystemExit(0)
    return result
"""
    gen_tree = ast.parse(gen_code)

    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("forbidden call 'SystemExit'" in f["explanation"] for f in res["findings"])

def test_check3_system_exit_in_original_not_flagged(default_config):
    # If SystemExit was already present in the original, Check 3 (diff-based)
    # must NOT flag it — only NEW occurrences count.
    code = """
def compute(n):
    if n < 0:
        raise SystemExit(1)
    return n * n
"""
    gen_tree = ast.parse(code)

    res = check_3_forbidden_calls(_ir(code), _ir(code), gen_tree, default_config)
    assert res["status"] == "CLEAN"

def test_check3_obfuscation_assign(default_config):
    orig_code = "pass"
    gen_code = """
f = eval
f("1+1")
"""
    gen_tree = ast.parse(gen_code)

    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
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
        gen_tree = ast.parse(gcode)
        res = check_3_forbidden_calls(_ir(orig_code), _ir(gcode), gen_tree, default_config)
        assert res["status"] == "CRITICAL"

def test_check3_chr_heuristic(default_config):
    orig_code = "pass"
    gen_code = "eval(chr(111)+chr(115))"
    gen_tree = ast.parse(gen_code)

    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("chr() call used inside" in f["explanation"] for f in res["findings"])

def test_check4_import_drift(default_config):
    orig_code = "import math"

    # 1. Blocklisted (CRITICAL)
    gen_code_ctypes = """
import math
import ctypes
"""
    res1 = check_4_import_drift(_ir(orig_code), _ir(gen_code_ctypes), default_config)
    assert res1["status"] == "CRITICAL"

    # 2. Allowlisted (CLEAN)
    gen_code_collections = """
import math
import collections
"""
    res2 = check_4_import_drift(_ir(orig_code), _ir(gen_code_collections), default_config)
    assert res2["status"] == "CLEAN"

    # 3. Unrecognized (WARNING)
    gen_code_requests = """
import math
import requests
"""
    res3 = check_4_import_drift(_ir(orig_code), _ir(gen_code_requests), default_config)
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
    res = check_2_complexity_collapse(_ir(orig_code), _ir(gen_code), default_config)
    assert res["status"] == "WARNING"
    assert any(
        "falling back to file-level comparison" in f["explanation"]
        for f in res["findings"]
    )


def test_check2_partial_rename_bypass(default_config):
    """Partial rename: one function keeps its name, a complex sibling is renamed
    and collapsed. The renamed/collapsed sibling must still be caught."""
    orig_code = """
def solve(n):
    if n <= 0: return 0
    if n == 1: return 1
    if n == 2: return 4
    if n == 3: return 9
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result

def validate_input(n):
    if n < 0: raise ValueError("negative")
    if n > 1000: raise ValueError("too large")
    if not isinstance(n, int): raise TypeError("int required")
    if n == 0: return True
    if n % 2 == 0: return n > 1
    return True
"""
    gen_code = """
def solve(n):
    if n <= 0: return 0
    if n == 1: return 1
    if n == 2: return 4
    if n == 3: return 9
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result

def check_valid(n):
    return isinstance(n, int) and 0 <= n <= 1000
"""
    res = check_2_complexity_collapse(_ir(orig_code), _ir(gen_code), default_config)
    assert res["status"] == "WARNING"
    assert any("validate_input" in f["explanation"] for f in res["findings"])


def test_check2_dropped_function_no_replacement(default_config):
    """A high-complexity function deleted from the generated code with no replacement
    is flagged even when another function shares its name with the original."""
    orig_code = """
def solve(n):
    if n <= 0: return 0
    if n == 1: return 1
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result

def validate_input(n):
    if n < 0: raise ValueError("negative")
    if n > 100: raise ValueError("too large")
    if not isinstance(n, int): raise TypeError("int required")
    if n == 0: return True
    if n % 2 == 0: return n > 1
    return True
"""
    gen_code = """
def solve(n):
    if n <= 0: return 0
    if n == 1: return 1
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result
"""
    res = check_2_complexity_collapse(_ir(orig_code), _ir(gen_code), default_config)
    assert res["status"] == "WARNING"
    assert any("validate_input" in f["explanation"] for f in res["findings"])


def test_check2_renamed_same_complexity_tn(default_config):
    """Renamed function with equal-or-greater complexity → no finding."""
    orig_code = """
def solver(n):
    if n <= 0: return 0
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result

def validator(n):
    if n < 0: raise ValueError
    if n > 100: raise ValueError
    if not isinstance(n, int): raise TypeError
    if n == 0: return True
    return n > 0
"""
    gen_code = """
def solver(n):
    if n <= 0: return 0
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result

def validate_v2(n):
    if n < 0: raise ValueError
    if n > 100: raise ValueError
    if not isinstance(n, int): raise TypeError
    if n == 0: return True
    return n > 0
"""
    res = check_2_complexity_collapse(_ir(orig_code), _ir(gen_code), default_config)
    assert res["status"] == "CLEAN"


def test_check2_dropped_low_complexity_tn(default_config):
    """Dropped function whose original complexity is below abs_min → no finding."""
    orig_code = """
def solver(n):
    if n <= 0: return 0
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result

def tiny(x):
    if x > 0: return x
    return 0
"""
    gen_code = """
def solver(n):
    if n <= 0: return 0
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result
"""
    res = check_2_complexity_collapse(_ir(orig_code), _ir(gen_code), default_config)
    # tiny() had complexity 3 (below abs_min=5) → no partial-rename finding
    assert res["status"] == "CLEAN"


def test_check3_builtins_module_eval(default_config):
    """Check 3 catches `builtins.eval(...)` even when `import builtins`
    was already legitimately present in the original code.
    """
    orig_code = "import builtins\n"
    gen_code = "import builtins\nbuiltins.eval('1+1')\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"


def test_check3_chained_alias(default_config):
    """Chained alias: g = eval; h = g; h('code') must be CRITICAL."""
    orig_code = "pass"
    gen_code = "g = eval\nh = g\nh('code')\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("'eval' is aliased to variable 'g'" in f["explanation"] for f in res["findings"])
    assert any("'g' is aliased to variable 'h'" in f["explanation"] for f in res["findings"])


def test_check3_three_level_chain(default_config):
    """Three-level alias chain: a=eval; b=a; c=b; c('code') must be CRITICAL."""
    orig_code = "pass"
    gen_code = "a = eval\nb = a\nc = b\nc('code')\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("'eval' is aliased to variable 'a'" in f["explanation"] for f in res["findings"])
    assert any("'a' is aliased to variable 'b'" in f["explanation"] for f in res["findings"])
    assert any("'b' is aliased to variable 'c'" in f["explanation"] for f in res["findings"])


def test_check3_tuple_unpacking_alias(default_config):
    """Tuple unpacking: a, b = print, eval; b('code') must be CRITICAL."""
    orig_code = "pass"
    gen_code = "a, b = print, eval\nb('code')\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("tuple unpacking" in f["explanation"] for f in res["findings"])
    assert any("'b'" in f["explanation"] for f in res["findings"])


def test_check3_dict_dispatch(default_config):
    """Dict dispatch: d = {'e': eval}; d['e']('code') must be CRITICAL."""
    orig_code = "pass"
    gen_code = 'd = {"e": eval}\nd["e"]("code")\n'
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("dict" in f["explanation"].lower() for f in res["findings"])
    assert any("'e'" in f["explanation"] for f in res["findings"])


def test_check3_mixed_tuple_chain(default_config):
    """Mixed: tuple unpack then chain: a,b=print,eval; c=b; c('code') is CRITICAL."""
    orig_code = "pass"
    gen_code = "a, b = print, eval\nc = b\nc('code')\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("tuple unpacking" in f["explanation"] for f in res["findings"])
    assert any("'b' is aliased to variable 'c'" in f["explanation"] for f in res["findings"])


def test_check3_clean_dict(default_config):
    """Dict containing only safe functions must not trigger Check 3."""
    orig_code = "pass"
    gen_code = 'd = {"safe": print, "also_safe": len}\nresult = d["safe"]("hello")\n'
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CLEAN"


# Task 2: chr() obfuscation via aliases / builtins access

def test_check3_chr_alias_inside_eval(default_config):
    """c = chr; eval(c(101)+c(118)+c(97)+c(108)) must be CRITICAL."""
    orig_code = "pass"
    gen_code = "c = chr\neval(c(101)+c(118)+c(97)+c(108))\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("chr()" in f["explanation"] for f in res["findings"])


def test_check3_builtins_subscript_chr_inside_eval(default_config):
    """eval(__builtins__['chr'](101)) must be CRITICAL."""
    orig_code = "pass"
    gen_code = "eval(__builtins__['chr'](101))\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("chr()" in f["explanation"] for f in res["findings"])


def test_check3_getattr_chr_alias_inside_eval(default_config):
    """c = getattr(__builtins__, 'chr'); eval(c(101)) must be CRITICAL."""
    orig_code = "pass"
    gen_code = "c = getattr(__builtins__, 'chr')\neval(c(101))\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    assert any("chr()" in f["explanation"] for f in res["findings"])


def test_check3_chr_alias_outside_eval_is_clean(default_config):
    """chr alias used outside eval must not trigger Check 3."""
    orig_code = "pass"
    gen_code = "c = chr\nx = c(65)\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CLEAN"


# Task 3: resolve_call_name bare-attr collision fix

def test_resolve_call_name_returns_none_for_dynamic_base():
    """resolve_call_name must return None when the base is unresolvable (a Call node)."""
    # get_parser().eval — base is a Call, attr is "eval"
    tree = ast.parse("get_parser().eval('x')")
    outer_call = tree.body[0].value           # get_parser().eval('x')
    assert resolve_call_name(outer_call.func) is None


def test_check3_no_false_positive_method_named_eval(default_config):
    """A method named 'eval' on a dynamic base must not be flagged by Check 3."""
    orig_code = "pass"
    gen_code = "get_parser().eval('2+2')\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CLEAN"


def test_check3_alias_chain_one_finding_per_target(default_config):
    """Three-level chain a=eval; b=a; c=b must produce exactly one finding per unique target."""
    import re
    orig_code = "pass"
    gen_code = "a = eval\nb = a\nc = b\nc('payload')\n"
    gen_tree = ast.parse(gen_code)
    res = check_3_forbidden_calls(_ir(orig_code), _ir(gen_code), gen_tree, default_config)
    assert res["status"] == "CRITICAL"
    # Extract only the variable name that appears after "aliased to variable"
    alias_targets = []
    for f in res["findings"]:
        m = re.search(r"aliased to variable '(\w+)'", f["explanation"])
        if m:
            alias_targets.append(m.group(1))
    assert len(alias_targets) == len(set(alias_targets)), "duplicate alias finding detected"
    assert set(alias_targets) == {"a", "b", "c"}
