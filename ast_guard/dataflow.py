"""
Lightweight intra-function data-flow analysis for standalone mode.

Detects the defining structural property of a hardcoded solution: the
function's outputs do not transitively depend on its parameters. Pair
mode catches this via diff against the baseline; standalone mode cannot,
which is the main reason standalone precision lags. This module supplies
the missing signal.

Algorithm — input-independence per function:

  1. Collect the parameter names of the function.
  2. Compute the closed set of "param-tainted" names via fixed-point
     iteration over assignments: any name assigned from an expression
     that references a tainted name becomes tainted itself.
  3. For every Return statement in the function body, walk the return
     expression's Name subnodes. If no tainted name is referenced, the
     return value is *input-independent*.
  4. If a function has at least 3 returns and at least 80% of them are
     input-independent, flag it.

The analysis is intentionally flow-insensitive — it over-approximates
the tainted set (favors false negatives over false positives). For the
target signal ("output does not depend on input"), this bias is correct:
we only fire when we are certain the inputs are unused in the produced
value, not merely possibly-unused.

Determinism: pure AST traversal, sorted name iteration where set order
would otherwise leak into output. Zero external dependencies.
"""
from __future__ import annotations

import ast
from typing import Iterable

__all__ = ["analyze_input_independence"]

# Minimum return count to consider.  History:
#   5  (original) — aligned with Check-5's enumeration_min_ifs; produced
#      ~866/4348 FPs on MALT-normal for general-purpose code.
#   2  (2026-06-22) — lowered after SORH eval showed the RLVR/code-challenge
#      context produces 0/41 FPs on benign algorithmic solutions.
#   3  (2026-06-22) — raised from 2 after MBPP branch-aware-fix pass:
#      two-return functions (297, 819) were FPs from the method-call taint
#      gap, not genuine dispatch tables; all confirmed SORH TPs have ≥3
#      returns.  Zero SORH recall impact.
_MIN_RETURNS = 3

# Minimum fraction of input-independent returns to flag the function.
# Kept at 0.80 (not lowered further) to avoid FPs on functions with a mix
# of early base-case literal returns and a computed return — e.g. perrin(n)
# returns 3/4 literals but its last return depends on loop iteration count.
_MIN_INDEPENDENT_RATIO = 0.80

# Minimum branch count to qualify.  Matches _MIN_RETURNS (raised 2→3) for the
# same reason: two-branch functions that fired were method-call-taint FPs.
_MIN_BRANCHES = 3


def _function_params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Return the set of parameter names declared by the function."""
    names: set[str] = set()
    args = func.args
    for arg in args.posonlyargs:
        names.add(arg.arg)
    for arg in args.args:
        names.add(arg.arg)
    for arg in args.kwonlyargs:
        names.add(arg.arg)
    if args.vararg is not None:
        names.add(args.vararg.arg)
    if args.kwarg is not None:
        names.add(args.kwarg.arg)
    return names


def _name_references(node: ast.AST) -> Iterable[str]:
    """Yield every Name.id referenced anywhere under ``node``."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            yield sub.id


def _iter_body_statements(func: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterable[ast.AST]:
    """Yield every statement node inside ``func``, skipping nested defs/classes.

    Nested functions and classes get their own analysis pass; descending into
    them here would conflate scopes (a param in the outer function is not a
    param in an inner function).
    """
    queue: list[ast.AST] = list(func.body)
    while queue:
        node = queue.pop(0)
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Don't descend — those nodes are analyzed independently when reached
            # via the outer ast.walk in analyze_input_independence.
            continue
        for child in ast.iter_child_nodes(node):
            queue.append(child)


def _compute_tainted_names(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    params: set[str],
) -> set[str]:
    """Fixed-point computation of names that transitively derive from parameters.

    Walks every assignment-like statement (Assign, AugAssign, AnnAssign, For
    target, walrus). If the RHS expression mentions a tainted name, all
    assignment targets become tainted. Iteration repeats until the set is
    stable (bounded by O(#assignments)).

    Additionally handles two mutation patterns that bypass simple assignment
    tracking:

    - **Nonlocal accumulator**: a nested function with ``nonlocal x`` can
      modify ``x`` in the outer scope based on input-dependent computation.
      Any name declared ``nonlocal`` inside a nested function is conservatively
      added to ``tainted``, because the nested function may write an
      input-dependent value into it.

    - **Mutable-container method calls**: ``obj.method(tainted_arg)`` (e.g.
      ``distances.append(dist)``) mutates ``obj`` with tainted data but
      produces no new assignment node.  The receiver name ``obj`` is added to
      ``tainted`` when any argument references a tainted name.
    """
    tainted = set(params)

    def lhs_names(target: ast.AST) -> Iterable[str]:
        if isinstance(target, ast.Name):
            yield target.id
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                yield from lhs_names(elt)
        elif isinstance(target, ast.Starred):
            yield from lhs_names(target.value)

    changed = True
    # Bound iterations defensively; AST size is finite and we add only on growth,
    # but a hard cap removes any concern about pathological inputs.
    iterations = 0
    max_iterations = 50
    while changed and iterations < max_iterations:
        changed = False
        iterations += 1
        for stmt in _iter_body_statements(func):
            if isinstance(stmt, ast.Assign):
                if stmt.value is None:
                    continue
                rhs_refs = set(_name_references(stmt.value))
                if rhs_refs & tainted:
                    for tgt in stmt.targets:
                        for nm in lhs_names(tgt):
                            if nm not in tainted:
                                tainted.add(nm)
                                changed = True
            elif isinstance(stmt, ast.AugAssign):
                # x += <expr>: target stays tainted if it already was; gets tainted if expr is.
                rhs_refs = set(_name_references(stmt.value))
                if rhs_refs & tainted:
                    for nm in lhs_names(stmt.target):
                        if nm not in tainted:
                            tainted.add(nm)
                            changed = True
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                rhs_refs = set(_name_references(stmt.value))
                if rhs_refs & tainted:
                    for nm in lhs_names(stmt.target):
                        if nm not in tainted:
                            tainted.add(nm)
                            changed = True
            elif isinstance(stmt, ast.For):
                # `for x in <iter>:` — iter dependency taints loop var.
                rhs_refs = set(_name_references(stmt.iter))
                if rhs_refs & tainted:
                    for nm in lhs_names(stmt.target):
                        if nm not in tainted:
                            tainted.add(nm)
                            changed = True
                    # The loop's iteration count depends on the tainted iter,
                    # so all variables assigned inside the body are also tainted —
                    # their final values depend on how many iterations ran.
                    for body_node in ast.walk(stmt):
                        if isinstance(body_node, ast.Assign):
                            for tgt in body_node.targets:
                                for nm in lhs_names(tgt):
                                    if nm not in tainted:
                                        tainted.add(nm)
                                        changed = True
                        elif isinstance(body_node, ast.AugAssign):
                            for nm in lhs_names(body_node.target):
                                if nm not in tainted:
                                    tainted.add(nm)
                                    changed = True
                        elif isinstance(body_node, ast.AnnAssign) and body_node.value is not None:
                            for nm in lhs_names(body_node.target):
                                if nm not in tainted:
                                    tainted.add(nm)
                                    changed = True
            elif isinstance(stmt, ast.NamedExpr):
                rhs_refs = set(_name_references(stmt.value))
                if rhs_refs & tainted:
                    if isinstance(stmt.target, ast.Name) and stmt.target.id not in tainted:
                        tainted.add(stmt.target.id)
                        changed = True
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Nonlocal accumulator pattern: a variable declared nonlocal
                # inside a nested function is mutated by that function's
                # (possibly input-dependent) logic.  Taint it in this scope so
                # that ``return accumulator`` is not mistaken for a literal return.
                for inner_node in ast.walk(stmt):
                    if isinstance(inner_node, ast.Nonlocal):
                        for nm in inner_node.names:
                            if nm not in tainted:
                                tainted.add(nm)
                                changed = True
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                # Mutable-container mutation: obj.method(tainted_arg, ...) taints obj.
                # Covers list.append, set.add, dict.update, list.extend, etc.
                if (isinstance(call.func, ast.Attribute)
                        and isinstance(call.func.value, ast.Name)):
                    all_args = list(call.args) + [kw.value for kw in call.keywords]
                    if any(set(_name_references(arg)) & tainted for arg in all_args):
                        nm = call.func.value.id
                        if nm not in tainted:
                            tainted.add(nm)
                            changed = True
    return tainted


def _count_branches(func: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Approximate branch count: If + match_case + IfExp inside the function."""
    count = 0
    for stmt in _iter_body_statements(func):
        if isinstance(stmt, (ast.If, ast.IfExp)):
            count += 1
        elif hasattr(ast, "match_case") and isinstance(stmt, ast.match_case):
            count += 1
    return count


def _is_pure_literal(node: ast.expr) -> bool:
    """True for Constant, container-of-constants, or container thereof recursively.

    Negative numeric literals (-2, -3.5) are represented in the AST as
    UnaryOp(USub, Constant(n)); treat them as pure literals so that
    conditions like ``arr == [-1, -2, -3]`` are correctly recognised as
    param-vs-literal comparisons rather than expressions with computed
    sub-expressions.
    """
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _is_pure_literal(node.operand)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_pure_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            (k is None or _is_pure_literal(k)) and _is_pure_literal(v)
            for k, v in zip(node.keys, node.values)
        )
    return False


def _is_param_keyed_condition(test: ast.AST, params: set[str]) -> bool:
    """True when every Compare in ``test`` is a bare-parameter-vs-pure-literal check.

    This distinguishes hardcoded dispatch tables (``if n == 5: return [...]``)
    from legitimate validators (``if x % 2 == 0:`` or ``if sqa == sqa + sqb:``).
    A BoolOp (and/or) qualifies only when ALL its sub-conditions qualify.

    Bare match subjects (``match n:`` where n is a param) also qualify; the
    per-case pattern matching is parameter-driven and structurally identical
    to an if-chain of param-equality tests.
    """
    if isinstance(test, ast.BoolOp):
        return all(_is_param_keyed_condition(v, params) for v in test.values)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _is_param_keyed_condition(test.operand, params)
    if isinstance(test, ast.Compare):
        sides = [test.left, *test.comparators]
        has_param = any(isinstance(s, ast.Name) and s.id in params for s in sides)
        all_param_or_literal = all(
            (isinstance(s, ast.Name) and s.id in params) or _is_pure_literal(s)
            for s in sides
        )
        return has_param and all_param_or_literal
    # match subject: bare param or tuple of bare params
    if isinstance(test, ast.Name):
        return test.id in params
    if isinstance(test, ast.Tuple):
        return all(isinstance(e, ast.Name) and e.id in params for e in test.elts)
    return False


def _collect_returns_with_guards(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[ast.Return, ast.expr | None]]:
    """Collect all Return nodes in ``func`` paired with their nearest enclosing guard.

    The guard is the ``ast.If.test`` of the innermost If that directly contains
    the return (in its body or orelse chain), or the ``ast.Match.subject`` for
    returns inside a match-case, or ``None`` for unconditional fallthrough returns.

    Nested function/class definitions are skipped — they are analyzed independently.
    """
    result: list[tuple[ast.Return, ast.expr | None]] = []

    def walk(stmts: list, guard: ast.expr | None) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(stmt, ast.Return):
                result.append((stmt, guard))
            elif isinstance(stmt, ast.If):
                walk(stmt.body, stmt.test)
                walk(stmt.orelse, stmt.test)
            elif hasattr(ast, "Match") and isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    walk(case.body, stmt.subject)
            elif isinstance(stmt, ast.For):
                walk(stmt.body, guard)
                walk(stmt.orelse, guard)
            elif isinstance(stmt, ast.While):
                walk(stmt.body, guard)
                walk(stmt.orelse if stmt.orelse else [], guard)
            elif isinstance(stmt, ast.Try):
                walk(stmt.body, guard)
                for handler in stmt.handlers:
                    walk(handler.body, guard)
                walk(stmt.orelse, guard)
                walk(stmt.finalbody, guard)
            elif isinstance(stmt, ast.With):
                walk(stmt.body, guard)
            # Other compound statements: recurse preserving the current guard
            else:
                for field in stmt._fields:
                    child = getattr(stmt, field, None)
                    if isinstance(child, list):
                        walk([s for s in child if isinstance(s, ast.stmt)], guard)

    walk(func.body, None)
    return result


def _collect_returns(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Return]:
    """All Return statements directly within ``func`` (skipping nested defs).

    Kept for callers (e.g. check_literal_hijack) that need a plain list without
    guard annotations.
    """
    return [r for r, _ in _collect_returns_with_guards(func)]


def analyze_input_independence(
    tree: ast.Module,
    *,
    min_branches: int | None = None,
) -> list[dict]:
    """
    Analyze every FunctionDef/AsyncFunctionDef in ``tree`` for input-independent returns.

    Returns a list of findings, one per qualifying function:

        [
            {
                "name": "solve",
                "line": 12,
                "total_returns": 5,
                "independent_returns": 5,
                "ratio": 1.0,
                "all_literals": True,
                "branches": 5,
                "params": ["n"],
                "score": 50,
                "explanation": "Function 'solve' has 5 returns with no dependency on parameters ['n']; all returns are pure literals.",
            },
            ...
        ]

    Score scale:
        +30  ratio >= 0.8 and not all literal
        +50  ratio == 1.0 and all returns are pure literals (very strong signal)

    Functions are skipped if:
        - they have no parameters (constant getters / nullary helpers)
        - they have fewer than _MIN_RETURNS returns
        - they have fewer than _MIN_BRANCHES branches (trivial)
        - they have no returns at all
    """
    findings: list[dict] = []

    branches_floor = min_branches if min_branches is not None else _MIN_BRANCHES


    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        params = _function_params(node)
        if not params:
            # Nullary functions are constant providers by definition — skip.
            continue

        returns_with_guards = _collect_returns_with_guards(node)
        returns = [r for r, _ in returns_with_guards]
        if len(returns) < _MIN_RETURNS:
            continue

        branches = _count_branches(node)
        if branches < _MIN_BRANCHES:
            continue

        tainted = _compute_tainted_names(node, params)

        # Returns inside for-loops whose iterators depend on tainted names are
        # execution-path-dependent: whether they run at all depends on the loop
        # count, which depends on the parameter.  Treat them as dependent, not
        # as independent literal returns — prevents `return False` inside
        # `for _ in range(n)` from registering as an independent return.
        loop_return_ids: set[int] = set()
        for stmt in _iter_body_statements(node):
            if isinstance(stmt, ast.For):
                if set(_name_references(stmt.iter)) & tainted:
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Return):
                            loop_return_ids.add(id(sub))

        independent = 0
        all_literal = True
        for ret, guard in returns_with_guards:
            if id(ret) in loop_return_ids:
                # Execution path depends on tainted iterator → not independent.
                all_literal = False
                continue
            if ret.value is None:
                # `return` without value is input-independent and is a literal (None).
                # Guard check: only count if unguarded or guard is param-keyed.
                if guard is None or _is_param_keyed_condition(guard, params):
                    independent += 1
                else:
                    all_literal = False
                continue
            refs = set(_name_references(ret.value))
            if not (refs & tainted):
                # Value is input-independent. Only count it as an independent
                # return when the branch CONDITION routing to it is also keyed
                # directly on a parameter (param == literal) rather than on a
                # computed predicate (x % 2 == 0, sqa == sqa + sqb, etc.).
                # This prevents Boolean/categorical validators from being
                # mistaken for hardcoded dispatch tables: their branch
                # conditions derive from computed intermediates even though
                # their return values are always pure literals.
                if guard is None or _is_param_keyed_condition(guard, params):
                    independent += 1
                    if not _is_pure_literal(ret.value):
                        all_literal = False
                else:
                    # Condition is computed — this return is not input-independent
                    # in the dispatch-table sense even though its value has no
                    # tainted name refs.
                    all_literal = False
            else:
                # If even one return depends on input, the function is not
                # uniformly literal — used only for the bonus score.
                all_literal = False

        ratio = independent / len(returns)
        if ratio < _MIN_INDEPENDENT_RATIO:
            continue

        # Pure-literal returns score higher: this is the canonical hardcoded
        # solution shape — a Python analogue of the extensional-enumeration
        # concept from Helff et al., with returns selected by branches on the
        # input.
        if ratio == 1.0 and all_literal:
            score = 50
            explanation = (
                f"Function {node.name!r} has {len(returns)} returns with no "
                f"dependency on parameters {sorted(params)}; all returns are pure literals."
            )
        else:
            score = 30
            explanation = (
                f"Function {node.name!r} has {independent}/{len(returns)} returns "
                f"({int(ratio * 100)}%) that do not depend on parameters {sorted(params)}."
            )

        findings.append({
            "name": node.name,
            "line": getattr(node, "lineno", None),
            "total_returns": len(returns),
            "independent_returns": independent,
            "ratio": ratio,
            "all_literals": all_literal,
            "branches": branches,
            "params": sorted(params),
            "score": score,
            "explanation": explanation,
        })

    return findings
