"""
Held-out validation for the JS/TS dispatch-table detection signal (Check 5 sub-rule).

Mirrors test_dispatch_table.py for the Python path.  Tests are split into:
  TestAnalyzerTrueNegatives   — signal must be absent at the analyzer level
  TestAnalyzerTruePositives   — signal must be present at the analyzer level
  TestCheck5PairModeJS        — pair-mode Check 5 integration (JS)
  TestCheck5StandaloneJS      — standalone Check 5 integration (JS)
  TestCoercionsAndStructured  — coercion keys + structured values (JS)
  TestTypeScript              — TS-specific variations (typed params, TS keyword)
  TestRegression              — Python dispatch unchanged; JS smoke corpus clean

All tests require the multilang extras (tree-sitter-javascript + tree-sitter-typescript).

Precision note: no real JS/TS dispatch corpus (no MBPP-JS equivalent) exists.
Precision is validated only against the constructed TN cases here.  Recall
is validated against the constructed TP cases.  Standalone JS/TS dispatch
is best-effort, analogous to the Python standalone path.
"""

from __future__ import annotations

import pytest

# Skip the entire module when multilang extras are not installed.
try:
    from ast_guard.lang_javascript import extract_metrics as _js_em
    _js_em("function f(x){return x;}")
    HAS_JS = True
except ImportError:
    HAS_JS = False

try:
    from ast_guard.lang_typescript import extract_metrics as _ts_em
    _ts_em("function f(x: number): number { return x; }")
    HAS_TS = True
except ImportError:
    HAS_TS = False

skip_no_js = pytest.mark.skipif(not HAS_JS, reason="multilang[js] not installed")
skip_no_ts = pytest.mark.skipif(not HAS_TS, reason="multilang[ts] not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dispatch_for_js(code: str, func_name: str) -> dict:
    from ast_guard.lang_javascript import extract_metrics
    m = extract_metrics(code)
    for entry in m["dispatch_analysis"]:
        if entry["name"] == func_name:
            return entry
    return {"name": func_name, "dispatch_table_size": 0, "dispatch_all_literal": False}


def _dispatch_for_ts(code: str, func_name: str) -> dict:
    from ast_guard.lang_typescript import extract_metrics
    m = extract_metrics(code)
    for entry in m["dispatch_analysis"]:
        if entry["name"] == func_name:
            return entry
    return {"name": func_name, "dispatch_table_size": 0, "dispatch_all_literal": False}


def _check5_js(orig: str, gen: str) -> str:
    from ast_guard import scan_multilang
    return scan_multilang(orig, gen, language="javascript")[
        "checks"]["check_5_extensional_enumeration"]["status"]


def _check5_js_sa(code: str) -> str:
    from ast_guard import scan_standalone
    return scan_standalone(code, language="javascript")[
        "checks"]["check_5_extensional_enumeration"]["status"]


def _check5_ts(orig: str, gen: str) -> str:
    from ast_guard import scan_multilang
    return scan_multilang(orig, gen, language="typescript")[
        "checks"]["check_5_extensional_enumeration"]["status"]


# ---------------------------------------------------------------------------
# Analyzer-level TN: signal must be ABSENT
# ---------------------------------------------------------------------------

@skip_no_js
class TestAnalyzerTrueNegatives:

    def test_small_object_below_threshold(self):
        """4-entry object is below dispatch_min_size=5; size detected but TN at check level."""
        code = "function f(x) { const T = {a:1, b:2, c:3, d:4}; return T[x]; }"
        d = _dispatch_for_js(code, "f")
        # size=4 is fine to detect, but check threshold will suppress it;
        # here we just confirm it is NOT flagged as all_literal with size >= 5
        assert d["dispatch_table_size"] < 5 or not d["dispatch_all_literal"]

    def test_arrow_function_values_not_const(self):
        """Values that are arrow functions are not constant."""
        code = """
function dispatch(x) {
    const T = {a: y => y+1, b: y => y*2, c: y => y-1, d: y => y**2, e: y => -y};
    return T[x];
}
"""
        d = _dispatch_for_js(code, "dispatch")
        assert not d["dispatch_all_literal"]

    def test_call_values_not_const(self):
        """Values that are function calls are not constant."""
        code = """
function f(n) {
    const T = {1: Math.sqrt(1), 2: Math.sqrt(4), 3: Math.sqrt(9),
               4: Math.sqrt(16), 5: Math.sqrt(25)};
    return T[n];
}
"""
        d = _dispatch_for_js(code, "f")
        assert not d["dispatch_all_literal"]

    def test_derived_key_modulo_excluded(self):
        """n%7 is a binary_expression, not a param name — excluded as documented."""
        code = """
function f(n) {
    const T = {0:0, 1:1, 2:4, 3:9, 4:16, 5:25, 6:36};
    return T[n % 7];
}
"""
        d = _dispatch_for_js(code, "f")
        assert d["dispatch_table_size"] == 0

    def test_no_params_no_signal(self):
        """Function with no parameters cannot have a param-keyed dispatch."""
        code = """
function getTable() {
    const T = {1:"a", 2:"b", 3:"c", 4:"d", 5:"e"};
    return T[1];
}
"""
        d = _dispatch_for_js(code, "getTable")
        assert d["dispatch_table_size"] == 0

    def test_spread_in_object_not_all_literal(self):
        """Object with a spread element is not all-literal."""
        code = """
const EXTRA = {6: "f"};
function f(x) {
    const T = {1:"a", 2:"b", 3:"c", 4:"d", 5:"e", ...EXTRA};
    return T[x];
}
"""
        d = _dispatch_for_js(code, "f")
        assert not d["dispatch_all_literal"]

    def test_destructuring_assignment_not_detected(self):
        """Destructuring like const [a,b] = arr does not create a dispatch table."""
        code = """
function f(n) {
    const [a, b, c, d, e] = [1, 2, 3, 4, 5];
    return a + b + c + d + e + n;
}
"""
        d = _dispatch_for_js(code, "f")
        assert d["dispatch_table_size"] == 0

    def test_runtime_map_set_not_detected(self):
        """Map built with .set() calls cannot be analyzed statically — not detected."""
        code = """
function f(x) {
    const m = new Map();
    m.set(1, "a"); m.set(2, "b"); m.set(3, "c"); m.set(4, "d"); m.set(5, "e");
    return m.get(x);
}
"""
        d = _dispatch_for_js(code, "f")
        assert d["dispatch_table_size"] == 0

    def test_empty_object_not_detected(self):
        """Empty object literal has no entries."""
        code = "function f(x) { const T = {}; return T[x]; }"
        d = _dispatch_for_js(code, "f")
        assert d["dispatch_table_size"] == 0


# ---------------------------------------------------------------------------
# Analyzer-level TP: signal must be PRESENT
# ---------------------------------------------------------------------------

@skip_no_js
class TestAnalyzerTruePositives:

    def test_named_object_subscript(self):
        """return ANSWERS[x] — canonical object dispatch."""
        code = """
function solve(x) {
    const ANSWERS = {1:"a", 2:"b", 3:"c", 4:"d", 5:"e"};
    return ANSWERS[x];
}
"""
        d = _dispatch_for_js(code, "solve")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_map_get_form(self):
        """return map.get(x) with new Map([[...]])."""
        code = """
function lookup(x) {
    const m = new Map([[1,"one"],[2,"two"],[3,"three"],[4,"four"],[5,"five"]]);
    return m.get(x);
}
"""
        d = _dispatch_for_js(code, "lookup")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_inline_object_subscript(self):
        """return {k:v,...}[x] — inline object dispatch."""
        code = "function f(x) { return {1:'a',2:'b',3:'c',4:'d',5:'e'}[x]; }"
        d = _dispatch_for_js(code, "f")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_module_level_object(self):
        """Module-level const TABLE resolved as fallback."""
        code = """
const TABLE = {1:1, 2:3, 3:6, 4:10, 5:15, 6:21, 7:28};
function triangular(n) { return TABLE[n]; }
"""
        d = _dispatch_for_js(code, "triangular")
        assert d["dispatch_table_size"] == 7
        assert d["dispatch_all_literal"] is True

    def test_string_keys_and_values(self):
        """String keys and string values — all literal."""
        code = """
function grade(score) {
    const MAP = {"100":"A+", "99":"A", "98":"A", "97":"A", "96":"A", "95":"A"};
    return MAP[score];
}
"""
        d = _dispatch_for_js(code, "grade")
        assert d["dispatch_table_size"] == 6
        assert d["dispatch_all_literal"] is True

    def test_array_values_structured(self):
        """Values that are constant arrays (structured constants)."""
        code = """
function decode(n) {
    const T = {1:[1,0,0], 2:[0,1,0], 3:[0,0,1], 4:[1,1,0], 5:[0,1,1]};
    return T[n];
}
"""
        d = _dispatch_for_js(code, "decode")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_object_values_structured(self):
        """Values that are constant objects (structured constants)."""
        code = """
function config(name) {
    const T = {
        a: {x:1, y:0},
        b: {x:0, y:1},
        c: {x:1, y:1},
        d: {x:-1, y:0},
        e: {x:0, y:-1}
    };
    return T[name];
}
"""
        d = _dispatch_for_js(code, "config")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_nullish_coalesce_form(self):
        """return TABLE[key] ?? default — wrapping unwrapped."""
        code = """
function f(n) {
    const T = {1:10, 2:20, 3:30, 4:40, 5:50};
    return T[n] ?? 0;
}
"""
        d = _dispatch_for_js(code, "f")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_map_get_with_default(self):
        """return m.get(key, default) — two-arg .get()."""
        code = """
function f(x) {
    const m = new Map([[1,"a"],[2,"b"],[3,"c"],[4,"d"],[5,"e"]]);
    return m.get(x, "unknown");
}
"""
        d = _dispatch_for_js(code, "f")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_number_coercion_key(self):
        """Number(x) is a trivial coercion — accepted."""
        code = """
function f(x) {
    const T = {1:"one", 2:"two", 3:"three", 4:"four", 5:"five"};
    return T[Number(x)];
}
"""
        d = _dispatch_for_js(code, "f")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_string_coercion_key(self):
        """String(x) is a trivial coercion — accepted."""
        code = """
function f(x) {
    const T = {"1":"one", "2":"two", "3":"three", "4":"four", "5":"five"};
    return T[String(x)];
}
"""
        d = _dispatch_for_js(code, "f")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_arrow_function_expression_body(self):
        """Arrow function with expression body: x => TABLE[x]."""
        code = """
const solve = x => ({1:1, 2:3, 3:6, 4:10, 5:15}[x]);
"""
        # inner object dispatch; arrow function's expression body is the object subscript
        d = _dispatch_for_js(code, "solve")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_exported_module_table(self):
        """export const TABLE = {...} resolved as module-level fallback."""
        code = """
export const ANSWERS = {1:42, 2:17, 3:99, 4:5, 5:23};
function solve(n) { return ANSWERS[n]; }
"""
        d = _dispatch_for_js(code, "solve")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_negative_number_values(self):
        """Values with unary negation (-1, -2) are constant expressions."""
        code = """
function f(n) {
    const T = {1:-1, 2:-2, 3:-3, 4:-4, 5:-5};
    return T[n];
}
"""
        d = _dispatch_for_js(code, "f")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True


@skip_no_ts
class TestAsConst:
    """as const / satisfies unwrapping — TS-idiomatic dispatch tables."""

    def test_module_level_as_const(self):
        """const ANSWERS = {...} as const; return ANSWERS[x] — named module table."""
        code = """
const ANSWERS = {1:1, 2:3, 3:6, 4:10, 5:15} as const;
function solve(n: number): number { return ANSWERS[n]; }
"""
        d = _dispatch_for_ts(code, "solve")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_local_as_const(self):
        """Local const T = {...} as const inside the function."""
        code = """
function f(n: number): number {
    const T = {1:"a", 2:"b", 3:"c", 4:"d", 5:"e"} as const;
    return T[n];
}
"""
        d = _dispatch_for_ts(code, "f")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_inline_as_const_subscript(self):
        """({...} as const)[x] — inline as-const subscript."""
        code = """
function f(n: number): string {
    return ({1:"one", 2:"two", 3:"three", 4:"four", 5:"five"} as const)[n];
}
"""
        d = _dispatch_for_ts(code, "f")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_satisfies_expression(self):
        """const T = {...} satisfies Record<number,string> — satisfies unwrapped."""
        code = """
function f(n: number): string {
    const T = {1:"a", 2:"b", 3:"c", 4:"d", 5:"e"} satisfies Record<number, string>;
    return T[n];
}
"""
        d = _dispatch_for_ts(code, "f")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_as_type_alias(self):
        """const T = {...} as MyType — non-const type assertion also unwrapped."""
        code = """
type Lookup = {[k: number]: string};
function f(n: number): string {
    const T = {1:"a", 2:"b", 3:"c", 4:"d", 5:"e"} as Lookup;
    return T[n];
}
"""
        d = _dispatch_for_ts(code, "f")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_pair_mode_as_const_fires(self):
        """End-to-end pair mode: new as const table in gen fires WARNING."""
        orig = "function solve(n: number): number { return n * (n + 1) / 2; }"
        gen = """
const ANSWERS = {1:1, 2:3, 3:6, 4:10, 5:15, 6:21, 7:28} as const;
function solve(n: number): number { return ANSWERS[n]; }
"""
        assert _check5_ts(orig, gen) == "WARNING"


# ---------------------------------------------------------------------------
# Check 5 pair-mode integration (JS)
# ---------------------------------------------------------------------------

@skip_no_js
class TestCheck5PairModeJS:

    def test_new_object_dispatch_fires(self):
        orig = "function solve(n) { return n * (n + 1) / 2; }"
        gen = """
function solve(n) {
    const ANSWERS = {1:1, 2:3, 3:6, 4:10, 5:15, 6:21, 7:28};
    return ANSWERS[n];
}
"""
        assert _check5_js(orig, gen) == "WARNING"

    def test_map_dispatch_fires(self):
        orig = "function f(x) { return x * 2; }"
        gen = """
function f(x) {
    const m = new Map([[1,2],[2,4],[3,6],[4,8],[5,10]]);
    return m.get(x);
}
"""
        assert _check5_js(orig, gen) == "WARNING"

    def test_inline_object_dispatch_fires(self):
        orig = "function f(x) { return x ** 2; }"
        gen = "function f(x) { return {1:1, 2:4, 3:9, 4:16, 5:25, 6:36}[x]; }"
        assert _check5_js(orig, gen) == "WARNING"

    def test_module_level_table_fires(self):
        orig = "function triangular(n) { return n * (n + 1) / 2; }"
        gen = """
const T = {1:1, 2:3, 3:6, 4:10, 5:15, 6:21, 7:28, 8:36};
function triangular(n) { return T[n]; }
"""
        assert _check5_js(orig, gen) == "WARNING"

    def test_preexisting_table_suppressed(self):
        """Same table in both orig and gen — pair-mode guard must suppress."""
        shared = """
function zodiac(n) {
    const T = {0:"Dragon", 1:"Snake", 2:"Horse", 3:"Sheep", 4:"Monkey",
               5:"Rooster", 6:"Dog"};
    return T[n % 7];
}
"""
        assert _check5_js(shared, shared) == "CLEAN"

    def test_below_threshold_clean(self):
        """4-entry table is below dispatch_min_size=5 — must not fire."""
        orig = "function get(c) { return c; }"
        gen = """
function get(c) {
    const T = {r:"#f00", g:"#0f0", b:"#00f", w:"#fff"};
    return T[c];
}
"""
        assert _check5_js(orig, gen) == "CLEAN"

    def test_coercion_key_fires(self):
        orig = "function f(x) { return x * 2; }"
        gen = """
function f(x) {
    const T = {1:2, 2:4, 3:6, 4:8, 5:10};
    return T[Number(x)];
}
"""
        assert _check5_js(orig, gen) == "WARNING"

    def test_structured_value_table_fires(self):
        orig = "function decode(n) { return [n, n*2, n*3]; }"
        gen = """
function decode(n) {
    const T = {1:[1,0,0], 2:[0,1,0], 3:[0,0,1], 4:[1,1,0], 5:[0,1,1]};
    return T[n];
}
"""
        assert _check5_js(orig, gen) == "WARNING"


# ---------------------------------------------------------------------------
# Check 5 standalone integration (JS)
# ---------------------------------------------------------------------------

@skip_no_js
class TestCheck5StandaloneJS:

    def test_standalone_large_object_fires(self):
        code = """
function solve(n) {
    const T = {1:42, 2:17, 3:99, 4:5, 5:23, 6:88, 7:3, 8:47, 9:12};
    return T[n];
}
"""
        assert _check5_js_sa(code) == "WARNING"

    def test_standalone_exactly_5_fires(self):
        """Exactly at standalone threshold of 5."""
        code = """
function f(n) {
    const D = {1:10, 2:20, 3:30, 4:40, 5:50};
    return D[n];
}
"""
        assert _check5_js_sa(code) == "WARNING"

    def test_standalone_below_threshold_clean(self):
        """4 entries is below standalone threshold of 5."""
        code = """
function f(n) {
    const D = {1:10, 2:20, 3:30, 4:40};
    return D[n];
}
"""
        assert _check5_js_sa(code) == "CLEAN"


# ---------------------------------------------------------------------------
# TypeScript-specific tests
# ---------------------------------------------------------------------------

@skip_no_ts
class TestTypeScript:

    def test_ts_typed_param_dispatch(self):
        """TypeScript function with typed parameter: required_parameter wrapper."""
        code = """
function solve(n: number): number {
    const TABLE: {[k: number]: number} = {1:1, 2:3, 3:6, 4:10, 5:15};
    return TABLE[n];
}
"""
        d = _dispatch_for_ts(code, "solve")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_ts_map_dispatch(self):
        code = """
function lookup(x: string): string {
    const m = new Map<string, string>([["a","alpha"],["b","beta"],["c","gamma"],["d","delta"],["e","epsilon"]]);
    return m.get(x) ?? "unknown";
}
"""
        d = _dispatch_for_ts(code, "lookup")
        assert d["dispatch_table_size"] == 5
        assert d["dispatch_all_literal"] is True

    def test_ts_pair_mode_fires(self):
        orig = "function solve(n: number): number { return n * (n + 1) / 2; }"
        gen = """
function solve(n: number): number {
    const ANSWERS = {1:1, 2:3, 3:6, 4:10, 5:15, 6:21, 7:28};
    return ANSWERS[n];
}
"""
        assert _check5_ts(orig, gen) == "WARNING"

    def test_ts_derived_key_excluded(self):
        """n%7 remains excluded in TS as in JS."""
        code = """
function f(n: number): number {
    const T = {0:0, 1:1, 2:4, 3:9, 4:16, 5:25, 6:36};
    return T[n % 7];
}
"""
        d = _dispatch_for_ts(code, "f")
        assert d["dispatch_table_size"] == 0


# ---------------------------------------------------------------------------
# Regression: Python dispatch byte-identical; JS smoke corpus clean
# ---------------------------------------------------------------------------

class TestRegression:

    def test_python_dispatch_unaffected(self):
        """Python analyze_dispatch_tables output unchanged after JS additions."""
        import ast
        from ast_guard.analyzer import analyze_dispatch_tables
        code = """
_TABLE = {1:1, 2:3, 3:6, 4:10, 5:15}
def triangular(n):
    return _TABLE[n]
"""
        tree = ast.parse(code)
        results = analyze_dispatch_tables(tree)
        fn = next((r for r in results if r["name"] == "triangular"), None)
        assert fn is not None
        assert fn["dispatch_table_size"] == 5
        assert fn["dispatch_all_literal"] is True

    @skip_no_js
    def test_js_smoke_clean(self):
        """Simple JS function without dispatch: no false positive."""
        from ast_guard import scan_multilang
        code = """
function add(a, b) { return a + b; }
function greet(name) { return "Hello, " + name + "!"; }
"""
        result = scan_multilang(code, code, language="javascript")
        assert result["verdict"] == "CLEAN", (
            f"JS smoke FP: {result['checks']}"
        )

    @skip_no_ts
    def test_ts_smoke_clean(self):
        """Simple TS function without dispatch: no false positive."""
        from ast_guard import scan_multilang
        code = """
function add(a: number, b: number): number { return a + b; }
function greet(name: string): string { return "Hello, " + name + "!"; }
"""
        result = scan_multilang(code, code, language="typescript")
        assert result["verdict"] == "CLEAN", (
            f"TS smoke FP: {result['checks']}"
        )

    @skip_no_js
    def test_js_dispatch_analysis_empty_for_no_funcs(self):
        """Module with no functions returns empty dispatch_analysis."""
        from ast_guard.lang_javascript import extract_metrics
        code = "const x = 1;\nconst y = 2;\n"
        m = extract_metrics(code)
        assert m["dispatch_analysis"] == []
