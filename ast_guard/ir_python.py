"""
Python AST -> CodeIR adapter.

Translates the output of ast_guard.analyzer.extract_metrics and direct AST
traversal into a language-agnostic CodeIR struct. Takes already-computed
tree and metrics to avoid duplicate parsing inside scan().

Also provides metrics_to_stub_ir() for scan_multilang() and
scan_standalone() paths where only a metrics dict is available.
"""
from __future__ import annotations

import ast
from typing import Optional

from ast_guard.analyzer import find_docstring_node_ids, build_lineno_index
from ast_guard.ir import CodeIR, DangerousCallEvent, EnhancementFlags, FunctionIR
# Dataflow helpers reused for Check 7/8 IR field computation.
# These are private-by-convention but stable and tested.
from ast_guard.dataflow import (  # noqa: PLC2701
    _function_params,
    _compute_tainted_names,
    _name_references,
    _is_pure_literal,
    _collect_returns,
    _iter_body_statements,
)

__all__ = ["build_ir", "metrics_to_stub_ir", "empty_ir"]

# ---------------------------------------------------------------------------
# Per-language enhancement flag sets
# ---------------------------------------------------------------------------

_PYTHON_ENHANCEMENTS = EnhancementFlags(
    guard_clause_exemption="supported",
    docstring_exclusion="supported",
    alias_resolution="supported",
    anti_obfuscation_deep="supported",
    taint_analysis="supported",
    match_case_enumeration="supported",
    dispatch_table="supported",
    dataflow_independence="supported",
    intent_mismatch="supported",
    normalized_tree="not_applicable",  # reserved for future TED work
)

# Flag C: switch/case enumeration is partial (literal-valued cases only).
# Flag dispatch_table: return TABLE[key] / TABLE.get(key) detection now supported.
# Flag dataflow_independence: Check 7/8 IR fields now computed by the JS adapter.
_JS_ENHANCEMENTS = EnhancementFlags(
    match_case_enumeration="partial",
    dispatch_table="supported",
    dataflow_independence="supported",
)

# TS: same as JS + docstring_exclusion=partial (JSDoc appears as comment nodes,
# not string literals; flag is informational rather than actively filtered).
_TS_ENHANCEMENTS = EnhancementFlags(
    match_case_enumeration="partial",
    dispatch_table="supported",
    docstring_exclusion="partial",
    dataflow_independence="supported",
)

# Bash: case-statement enumeration works via enumeration_analysis; all other
# enhancements are not_applicable (no functions-with-returns, no dispatch-table
# idiom, no taint/dataflow, no docstrings).
_BASH_ENHANCEMENTS = EnhancementFlags(
    match_case_enumeration="partial",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_non_docstring_strings(tree: ast.Module) -> set:
    """String constant values that are not docstrings."""
    doc_ids = find_docstring_node_ids(tree)
    strings: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in doc_ids:
                strings.add(node.value)
    return strings


def _collect_scalar_set(tree: ast.Module) -> frozenset:
    """All hashable scalar constant values anywhere in the tree.

    Used by Check 8 to determine which comparators are 'new' in gen relative
    to orig.  Unhashable constants (e.g. bytearray) are silently skipped.
    """
    values: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            try:
                hash(node.value)
                values.add(node.value)
            except TypeError:
                pass
    return frozenset(values)


def _walk_functions_with_qnames(tree: ast.Module):
    """Yield (qname, func_node) for every function definition in tree.

    Mirrors the convention in check_literal_hijack._walk_functions_with_qnames
    and analyzer.collect_function_complexities (without the #2 disambiguation).
    """
    def visit(node, prefix):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qname = f"{prefix}.{node.name}" if prefix else node.name
            yield qname, node
            child_prefix = qname
        elif isinstance(node, ast.ClassDef):
            child_prefix = f"{prefix}.{node.name}" if prefix else node.name
        else:
            child_prefix = prefix
        for child in ast.iter_child_nodes(node):
            yield from visit(child, child_prefix)

    yield from visit(tree, "")


def _body_stmt_count(func: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Non-docstring body statement count."""
    body = func.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return len(body)


def _is_literal_assigned_local(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    var_name: str,
) -> bool:
    """True if any statement in func's body assigns a pure literal to var_name."""
    for stmt in _iter_body_statements(func):
        if isinstance(stmt, ast.Assign) and stmt.value is not None:
            if _is_pure_literal(stmt.value):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == var_name:
                        return True
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            if _is_pure_literal(stmt.value):
                if isinstance(stmt.target, ast.Name) and stmt.target.id == var_name:
                    return True
    return False


def _is_specific_compare_literal_local(node: ast.expr) -> bool:
    """True if node is a pure literal that is 'specific' enough to be a bypass signal.

    Trivial sentinels (0, 1, -1, 2, None, True, False, '') are excluded.
    Non-trivial scalars and non-empty containers qualify.
    """
    _TRIVIAL = frozenset({0, 1, -1, 2, None, True, False, ""})
    if isinstance(node, ast.Constant):
        return node.value not in _TRIVIAL
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts) >= 1
    if isinstance(node, ast.Dict):
        return len(node.keys) >= 1
    return False


def _is_pure_compare_return_hack_local(
    returns: list[ast.Return],
    tainted: set[str],
) -> bool:
    """True if every non-bare return is param == <specific_literal> (compare-return variant).

    Mirrors check_literal_hijack._is_pure_compare_return_hack.
    """
    _TRIVIAL = frozenset({0, 1, -1, 2, None, True, False, ""})
    has_suspicious = False
    for ret in returns:
        if ret.value is None:
            continue
        if not isinstance(ret.value, ast.Compare):
            return False
        compare = ret.value
        if len(compare.comparators) != 1:
            return False
        sides = [compare.left, compare.comparators[0]]
        tainted_name = None
        literal_node = None
        for side in sides:
            if isinstance(side, ast.Name) and side.id in tainted:
                tainted_name = side
            elif _is_pure_literal(side):
                literal_node = side
        if tainted_name is None or literal_node is None:
            return False
        if not _is_specific_compare_literal_local(literal_node):
            return False
        has_suspicious = True
    return has_suspicious


def _has_tainted_control_flow_local(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    tainted: set[str],
) -> bool:
    """True if any branch/loop condition or throw-determining try position references a tainted name.

    Mirrors check_literal_hijack._has_tainted_control_flow.
    """
    def _tainted_in(expr):
        for n in ast.walk(expr):
            if isinstance(n, ast.Name) and n.id in tainted:
                return True
        return False

    def _tainted_in_throw_pos(try_body):
        for stmt in try_body:
            for n in ast.walk(stmt):
                if isinstance(n, ast.Call):
                    if _tainted_in(n.func):
                        return True
                    for arg in n.args:
                        if _tainted_in(arg):
                            return True
                    for kw in n.keywords:
                        if _tainted_in(kw.value):
                            return True
                elif isinstance(n, ast.Subscript):
                    if _tainted_in(n.value) or _tainted_in(n.slice):
                        return True
                elif isinstance(n, ast.BinOp):
                    if _tainted_in(n.left) or _tainted_in(n.right):
                        return True
                elif isinstance(n, ast.Attribute):
                    if _tainted_in(n.value):
                        return True
                elif isinstance(n, ast.For):
                    if _tainted_in(n.iter):
                        return True
                elif isinstance(n, ast.With):
                    for item in n.items:
                        if _tainted_in(item.context_expr):
                            return True
        return False

    for stmt in _iter_body_statements(func):
        if isinstance(stmt, ast.If):
            cond = stmt.test
        elif isinstance(stmt, ast.While):
            cond = stmt.test
        elif isinstance(stmt, ast.For):
            cond = stmt.iter
        elif isinstance(stmt, ast.IfExp):
            cond = stmt.test
        elif isinstance(stmt, ast.Try):
            if _tainted_in_throw_pos(stmt.body):
                return True
            continue
        else:
            continue
        for n in ast.walk(cond):
            if isinstance(n, ast.Name) and n.id in tainted:
                return True
    return False


_TRIVIAL_GATE_LITERALS: frozenset = frozenset({0, 1, -1, 2, None, True, False, ""})


def _is_non_trivial_condition_literal(node: ast.AST) -> bool:
    """True if node is a Constant whose value is not a trivial base-case sentinel.

    Trivial sentinels (0, 1, -1, 2, None, True, False, '') are common in
    legitimate base-case guards (e.g. `if n == 0: return 0`).  Any other
    scalar is 'specific' enough to be a suspicious hardcoded test input.
    """
    if not isinstance(node, ast.Constant):
        return False
    return node.value not in _TRIVIAL_GATE_LITERALS


def _is_literal_gate_condition(test: ast.AST, tainted: set) -> bool:
    """True if test is a literal-gate condition: a param equality-check against a
    specific constant (scalar) or a tuple of params against a tuple of constants.

    Recognized forms:
      param == non_trivial_lit           — scalar comparison (reversed form too)
      (p1, p2, ...) == (l1, l2, ...)    — tuple comparison, len >= 2, params on LHS
      BoolOp(And, [above, above, ...])   — conjunction of the above

    Requires that the condition literal is non-trivial (for scalars) or that
    the LHS tuple has >= 2 elements (for tuples).  This prevents base-case guards
    like `if n == 0: return 0` from being flagged.
    """
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        return all(_is_literal_gate_condition(v, tainted) for v in test.values)

    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False

    lhs, rhs = test.left, test.comparators[0]

    # Scalar form: bare param == non-trivial literal (or reversed)
    if isinstance(lhs, ast.Name) and lhs.id in tainted:
        return _is_non_trivial_condition_literal(rhs)
    if isinstance(rhs, ast.Name) and rhs.id in tainted:
        return _is_non_trivial_condition_literal(lhs)

    # Tuple form: (p1, p2, ...) == (l1, l2, ...) with len >= 2 params on LHS
    if (isinstance(lhs, ast.Tuple) and isinstance(rhs, ast.Tuple)
            and len(lhs.elts) >= 2 and len(lhs.elts) == len(rhs.elts)):
        lhs_ok = all(isinstance(e, ast.Name) and e.id in tainted for e in lhs.elts)
        rhs_ok = all(isinstance(e, ast.Constant) for e in rhs.elts)
        return lhs_ok and rhs_ok

    return False


def _is_single_branch_literal_gate_local(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    tainted: set,
    all_returns_independent: bool = False,
) -> bool:
    """True if the function contains a single literal-gate hack pattern.

    Detects two forms:
      (a) Ternary:      return <lit> if <gate_cond> else <lit>
      (b) If-statement: if <gate_cond>: return <lit>   [only when all_returns_independent]

    <gate_cond> is a param equality-check against a non-trivial constant (see
    _is_literal_gate_condition); return values must be pure literals.

    Ternary form (a) is self-contained: both branches are explicit literals so
    there is no "other code" that could make the pattern legitimate.

    If-statement form (b) requires all_returns_independent=True (all explicit
    returns in the function are input-independent and at least one is a literal).
    This prevents FPs on functions like `if n == 4: return 3; return n - 1`
    where the fallback uses the parameter in real computation.

    The original-complexity pair-mode guard is applied by the caller (check_7).
    """
    for stmt in _iter_body_statements(func):
        # Ternary form: return <lit> if <gate_cond> else <lit>
        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.IfExp):
            ifexp = stmt.value
            if (_is_literal_gate_condition(ifexp.test, tainted)
                    and _is_pure_literal(ifexp.body)
                    and _is_pure_literal(ifexp.orelse)):
                return True

        # If-statement form: if <gate_cond>: return <lit>
        # Only fire when all other returns are also input-independent literals,
        # ensuring we don't flag functions with real computation fallbacks.
        if all_returns_independent and isinstance(stmt, ast.If):
            if _is_literal_gate_condition(stmt.test, tainted):
                for s in stmt.body:
                    if isinstance(s, ast.Return) and _is_pure_literal(s.value):
                        return True

    return False


def _references_tainted_local(expr: ast.expr, tainted: set[str]) -> bool:
    """True if any Name node under expr is in the tainted set."""
    for n in ast.walk(expr):
        if isinstance(n, ast.Name) and n.id in tainted:
            return True
    return False


def _body_has_bypass_return_local(body: list, tainted: set[str]) -> bool:
    """True if any top-level return in body is input-independent."""
    for stmt in body:
        if not isinstance(stmt, ast.Return):
            continue
        if stmt.value is None:
            continue
        refs = set(_name_references(stmt.value))
        if not (refs & tainted):
            return True
    return False


def _collect_bypass_events(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    tainted: set[str],
) -> tuple:
    """Collect per-branch bypass event data for Check 8 IR field.

    Returns a tuple of (line, scalars_frozenset, containers_tuple) for each
    top-level if-branch that has (a) tainted-vs-literal condition and (b)
    input-independent return in the branch body.

    containers_tuple contains (original_len, element_values_tuple) pairs for
    each container (List/Tuple/Set) comparator found in qualifying conditions.
    """
    body = func.body
    # Skip leading docstring.
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]

    events = []
    seen_lines: set = set()

    for stmt in body:
        if not isinstance(stmt, ast.If):
            continue

        # Collect all Compare nodes in the condition where one side is tainted
        # and the other side is a pure literal.
        scalars: set = set()
        containers: list = []

        for node in ast.walk(stmt.test):
            if not isinstance(node, ast.Compare):
                continue
            # Only equality-class operators signal test-case hardcoding
            # (== / is / in).  Range checks (<, >, <=, >=) are legitimate
            # algorithmic boundaries, and inequality checks (!= / is not /
            # not in) are structural counts or validation guards (e.g.
            # `if distances.count(side) != 4: return False` is correct
            # geometry, not a hardcoded test value).
            if not any(isinstance(op, (ast.Eq, ast.Is, ast.In))
                       for op in node.ops):
                continue
            sides = [node.left] + list(node.comparators)
            for i, side in enumerate(sides):
                if not _references_tainted_local(side, tainted):
                    continue
                for j, other in enumerate(sides):
                    if i == j:
                        continue
                    if not _is_pure_literal(other):
                        continue
                    if isinstance(other, ast.Constant):
                        try:
                            hash(other.value)
                            scalars.add(other.value)
                        except TypeError:
                            pass
                    elif isinstance(other, (ast.List, ast.Tuple, ast.Set)):
                        elts = other.elts
                        elt_values = tuple(
                            e.value for e in elts
                            if isinstance(e, ast.Constant)
                        )
                        containers.append((len(elts), elt_values))

        if not scalars and not containers:
            continue

        if not _body_has_bypass_return_local(stmt.body, tainted):
            continue

        line = getattr(stmt, "lineno", None)
        if line in seen_lines:
            continue
        seen_lines.add(line)

        events.append((line, frozenset(scalars), tuple(containers)))

    return tuple(events)


def _compute_dataflow_fields(tree: ast.Module) -> dict:
    """Compute per-function dataflow_independence fields for all functions in tree.

    Returns dict mapping qname -> dict-of-field-values.  Only non-dunder,
    non-nullary functions get full analysis; others get neutral defaults.
    Body statement counts are computed for all functions (used orig-side).
    """
    result: dict = {}

    for qname, func in _walk_functions_with_qnames(tree):
        stmt_count = _body_stmt_count(func)
        bare = qname.rsplit(".", 1)[-1]

        # Dunder methods and nullary functions get neutral defaults.
        # (Check 7/8 skip them at check time anyway; this avoids redundant work.)
        params = _function_params(func)
        is_dunder = bare.startswith("__") and bare.endswith("__")
        func_line = getattr(func, "lineno", None)
        if is_dunder or not params:
            result[qname] = {
                "line": func_line,
                "body_stmt_count": stmt_count,
                "param_names": (),
                "all_returns_input_independent": False,
                "has_pure_literal_return": False,
                "is_compare_return_hack": False,
                "has_tainted_control_flow": False,
                "bypass_events": (),
            }
            continue

        returns = _collect_returns(func)
        tainted = _compute_tainted_names(func, params)

        all_independent = True
        has_literal_return = False

        if returns:
            for ret in returns:
                if ret.value is None:
                    continue
                refs = set(_name_references(ret.value))
                if refs & tainted:
                    all_independent = False
                    break
                if _is_pure_literal(ret.value):
                    has_literal_return = True
                elif isinstance(ret.value, ast.Name):
                    if _is_literal_assigned_local(func, ret.value.id):
                        has_literal_return = True
        else:
            all_independent = False

        is_compare_hack = (
            bool(returns)
            and not (all_independent and has_literal_return)
            and _is_pure_compare_return_hack_local(returns, tainted)
        )

        has_tcf = _has_tainted_control_flow_local(func, tainted)
        bypass_events = _collect_bypass_events(func, tainted)
        is_gate = _is_single_branch_literal_gate_local(
            func, tainted, all_independent and bool(returns)
        )

        result[qname] = {
            "line": func_line,
            "body_stmt_count": stmt_count,
            "param_names": tuple(sorted(params)),
            "all_returns_input_independent": all_independent and bool(returns),
            "has_pure_literal_return": has_literal_return,
            "is_compare_return_hack": is_compare_hack,
            "is_single_branch_literal_gate": is_gate,
            "has_tainted_control_flow": has_tcf,
            "bypass_events": bypass_events,
        }

    return result


def _build_per_function(metrics: dict, dataflow_fields: dict | None = None) -> list:
    """Merge function_complexities, enumeration_analysis, dispatch_analysis, and
    optional dataflow_fields into a FunctionIR list.

    function_complexities uses qualified names (ClassName.method); enumeration
    and dispatch use bare names, merged by last component. dataflow_fields is
    keyed by qualified name (exact match; the #2 disambiguation edge case gets
    neutral defaults, which is conservative).
    """
    func_comps: dict = metrics.get("function_complexities", {}) or {}
    enum_analysis: list = metrics.get("enumeration_analysis", []) or []
    dispatch_analysis: list = metrics.get("dispatch_analysis", []) or []
    df: dict = dataflow_fields or {}

    # bare-name -> first matching entry maps
    enum_map: dict = {}
    for entry in enum_analysis:
        bare = entry.get("name", "")
        if bare and bare not in enum_map:
            enum_map[bare] = entry

    dispatch_map: dict = {}
    for entry in dispatch_analysis:
        bare = entry.get("name", "")
        if bare and bare not in dispatch_map:
            dispatch_map[bare] = entry

    result = []
    for qname, mccabe in sorted(func_comps.items()):
        bare = qname.rsplit(".", 1)[-1]
        ed = enum_map.get(bare, {})
        dd = dispatch_map.get(bare, {})
        dfw = df.get(qname, {})
        result.append(FunctionIR(
            identity=qname,
            mccabe=mccabe,
            total_ifs=ed.get("total_ifs", 0),
            enumeration_ifs=ed.get("enumeration_ifs", 0),
            loop_count=ed.get("loop_count", 0),
            line=dfw.get("line", None),
            dispatch_table_size=dd.get("dispatch_table_size", 0),
            dispatch_all_literal=dd.get("dispatch_all_literal", False),
            body_stmt_count=dfw.get("body_stmt_count", 0),
            param_names=dfw.get("param_names", ()),
            all_returns_input_independent=dfw.get("all_returns_input_independent", False),
            has_pure_literal_return=dfw.get("has_pure_literal_return", False),
            is_compare_return_hack=dfw.get("is_compare_return_hack", False),
            is_single_branch_literal_gate=dfw.get("is_single_branch_literal_gate", False),
            has_tainted_control_flow=dfw.get("has_tainted_control_flow", False),
            bypass_events=dfw.get("bypass_events", ()),
        ))
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_ir(code: str, tree: ast.Module, metrics: dict) -> CodeIR:
    """Build a full Python CodeIR from pre-parsed tree and pre-extracted metrics.

    Accepts pre-computed inputs so scan() avoids duplicate parsing.
    All Python enhancement flags are set to 'supported'.
    """
    lineno_idx = build_lineno_index(tree)
    string_set = _extract_non_docstring_strings(tree)

    if_count_adjusted = metrics.get("if_count", 0)
    guard_count = metrics.get("guard_clause_count", 0)

    return CodeIR(
        language="python",
        if_count_raw=if_count_adjusted + guard_count,
        if_count=if_count_adjusted,
        guard_clause_count=guard_count,
        loop_depth=metrics.get("loop_depth", 0),
        literal_count=metrics.get("literal_count", 0),
        string_set=string_set,
        string_linenos=lineno_idx["strings"],
        import_set=set(metrics.get("import_list", [])),
        call_set=set(metrics.get("call_list", [])),
        call_linenos=lineno_idx["calls"],
        mccabe_complexity=metrics.get("mccabe_complexity", 1),
        non_trivial_binop_count=metrics.get("non_trivial_binop_count", 0),
        max_set_literal_size=metrics.get("max_set_literal_size", 0),
        max_dict_literal_size=metrics.get("max_dict_literal_size", 0),
        comprehension_count=metrics.get("comprehension_count", 0),
        functional_call_count=metrics.get("functional_call_count", 0),
        per_function=_build_per_function(metrics, _compute_dataflow_fields(tree)),
        enumeration_analysis=metrics.get("enumeration_analysis", []) or [],
        dangerous_call_events=[],  # populated by scan() when needed
        scalar_set=_collect_scalar_set(tree),
        enhancements=_PYTHON_ENHANCEMENTS,
    )


def metrics_to_stub_ir(metrics: dict, language: str = "python") -> CodeIR:
    """Convert a metrics dict to a CodeIR for non-Python or stub paths.

    Used by scan_multilang() and scan_standalone() where only a metrics dict
    is available (no Python AST tree). String sets and lineno maps are empty;
    the enhancement flags reflect the target language.
    """
    if language == "python":
        # Standalone Python path: enhancements still supported but no tree
        enh = _PYTHON_ENHANCEMENTS
    elif language == "javascript":
        enh = _JS_ENHANCEMENTS
    elif language == "typescript":
        enh = _TS_ENHANCEMENTS
    elif language == "bash":
        enh = _BASH_ENHANCEMENTS
    else:
        enh = EnhancementFlags()  # all not_applicable

    if_count_adjusted = metrics.get("if_count", 0)
    guard_count = metrics.get("guard_clause_count", 0)

    return CodeIR(
        language=language,
        if_count_raw=if_count_adjusted + guard_count,
        if_count=if_count_adjusted,
        guard_clause_count=guard_count,
        loop_depth=metrics.get("loop_depth", 0),
        literal_count=metrics.get("literal_count", 0),
        string_set=set(),
        string_linenos={},
        import_set=set(metrics.get("import_list", [])),
        call_set=set(metrics.get("call_list", [])),
        call_linenos={},
        mccabe_complexity=metrics.get("mccabe_complexity", 1),
        non_trivial_binop_count=metrics.get("non_trivial_binop_count", 0),
        max_set_literal_size=metrics.get("max_set_literal_size", 0),
        max_dict_literal_size=metrics.get("max_dict_literal_size", 0),
        comprehension_count=metrics.get("comprehension_count", 0),
        functional_call_count=metrics.get("functional_call_count", 0),
        per_function=_build_per_function(metrics, metrics.get("dataflow_fields")),
        enumeration_analysis=metrics.get("enumeration_analysis", []) or [],
        dangerous_call_events=metrics.get("dangerous_call_events", []),
        scalar_set=metrics.get("scalar_set", frozenset()),
        enhancements=enh,
    )


def empty_ir(language: str = "python") -> CodeIR:
    """Return an IR with all neutral values (mirrors _EMPTY_METRICS in scan()).

    Used as orig_ir in scan_standalone() where no baseline exists.
    """
    if language == "python":
        enh = _PYTHON_ENHANCEMENTS
    elif language == "javascript":
        enh = _JS_ENHANCEMENTS
    elif language == "typescript":
        enh = _TS_ENHANCEMENTS
    elif language == "bash":
        enh = _BASH_ENHANCEMENTS
    else:
        enh = EnhancementFlags()
    return CodeIR(language=language, enhancements=enh)
