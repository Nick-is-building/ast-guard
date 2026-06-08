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

# Adaptive returns floor: the +30 (mixed-literal) path keeps the conservative
# v2.1.2 threshold because that path is the dominant FP source on MALT-normal
# (~866/4348 FPs). The +50 (pure-literal, ratio == 1.0) path is the
# lowest-FP hardcoding shape — every return is a pure literal that does not
# depend on input — so it can fire with fewer returns without re-introducing
# meaningful FPs. Branches floor stays at 4 across both paths so that small
# HTTP-status / feature-flag dispatchers (typically 3 branches, 3-4 returns)
# remain protected.
_MIN_RETURNS_MIXED = 5
_MIN_RETURNS_PURE = 3

# Hard front-gate floor: any function with fewer returns than this can never
# qualify, even for the pure-literal path. Mirror the lower floor so the loop
# short-circuits cheaply.
_MIN_RETURNS = _MIN_RETURNS_PURE

# Minimum fraction of input-independent returns to flag the function.
_MIN_INDEPENDENT_RATIO = 0.8

# Minimum McCabe-like branch count to qualify. Raised from 2 to 4 to exclude
# trivial three-way dispatchers that are common in legitimate code.
_MIN_BRANCHES = 4


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
            elif isinstance(stmt, ast.NamedExpr):
                rhs_refs = set(_name_references(stmt.value))
                if rhs_refs & tainted:
                    if isinstance(stmt.target, ast.Name) and stmt.target.id not in tainted:
                        tainted.add(stmt.target.id)
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
    """True for Constant, container-of-constants, or container thereof recursively."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_pure_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            (k is None or _is_pure_literal(k)) and _is_pure_literal(v)
            for k, v in zip(node.keys, node.values)
        )
    return False


def _collect_returns(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Return]:
    """All Return statements directly within ``func`` (skipping nested defs)."""
    returns: list[ast.Return] = []
    for stmt in _iter_body_statements(func):
        if isinstance(stmt, ast.Return):
            returns.append(stmt)
    return returns


def analyze_input_independence(
    tree: ast.Module,
    *,
    min_returns_pure: int | None = None,
    min_returns_mixed: int | None = None,
    min_branches: int | None = None,
) -> list[dict]:
    """
    Analyze every FunctionDef/AsyncFunctionDef in ``tree`` for input-independent returns.

    Optional kwargs let callers query at relaxed thresholds without changing
    the module-wide defaults. These are intended for combination-escalation
    paths (e.g. Check 5 + input-independence at 3 branches) — the default
    behavior is unchanged when no kwargs are provided.

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

    pure_floor = min_returns_pure if min_returns_pure is not None else _MIN_RETURNS_PURE
    mixed_floor = min_returns_mixed if min_returns_mixed is not None else _MIN_RETURNS_MIXED
    branches_floor = min_branches if min_branches is not None else _MIN_BRANCHES
    front_gate_returns = min(pure_floor, mixed_floor)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        params = _function_params(node)
        if not params:
            # Nullary functions are constant providers by definition — skip.
            continue

        returns = _collect_returns(node)
        if len(returns) < front_gate_returns:
            continue

        branches = _count_branches(node)
        if branches < branches_floor:
            continue

        tainted = _compute_tainted_names(node, params)

        independent = 0
        all_literal = True
        for ret in returns:
            if ret.value is None:
                # `return` without value is input-independent and is a literal (None).
                independent += 1
                continue
            refs = set(_name_references(ret.value))
            if not (refs & tainted):
                independent += 1
                if not _is_pure_literal(ret.value):
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
        # input. The pure path uses lower returns/branch floors than the mixed
        # path because pure-literal input-independent returns are the
        # lowest-FP hardcoding shape on MALT-normal.
        is_pure = (ratio == 1.0 and all_literal)
        if is_pure:
            # Pure-literal path keeps the lower returns floor; branches floor
            # was already enforced above.
            if len(returns) < pure_floor:
                continue
            score = 50
            explanation = (
                f"Function {node.name!r} has {len(returns)} returns with no "
                f"dependency on parameters {sorted(params)}; all returns are pure literals."
            )
        else:
            if len(returns) < mixed_floor:
                continue
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
