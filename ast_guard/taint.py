"""
Intra-file taint tracker for Check 6 (standalone).

Tracks references to forbidden module attributes that escape direct call
detection by flowing through:

    (a) function returns                — def f(): return sys.exit
    (b) class attribute assignment      — self._e = sys.exit
    (c) setattr() on an imported module — setattr(time, "sleep", lambda: ...)
    (d) globals() subscript writes      — g = globals(); g["x"] = sys.exit
    (e) closure capture                 — def outer(): _e = sys.exit; def inner(): _e()

A fixed-point propagation pass then expands taint through simple aliasing
(`x = tainted_func()` or `x = tainted_name`), catching recursive chains
such as `def a(): return b(); def b(): return os.remove`.

The pass is intentionally local: no cross-file analysis, no execution.
Same input always produces the same dict, preserving the determinism
invariant.

Public API:
    collect_tainted_names(tree, imported_modules) -> dict[str, TaintSource]
    find_tainted_calls(tree, tainted) -> list of (call_node, key, source)
"""
import ast
from dataclasses import dataclass
from typing import Optional

from ast_guard.checks import is_blocked_call

__all__ = ["TaintSource", "collect_tainted_names", "find_tainted_calls"]


@dataclass(frozen=True)
class TaintSource:
    """A reason why a name is considered tainted.

    origin       human-readable description (e.g. "sys.exit", "B._exit")
    line         source line of the tainting statement, if available
    score        Check-6 contribution when the tainted name is observed
    source_type  one of: return | class_attr | setattr | globals | closure | propagated
    """
    origin: str
    line: Optional[int]
    score: int
    source_type: str


# Mirrors of the sets in check_behavioral.py — duplicated to avoid a circular
# import. These sets are stable; if they change there, update both places.
_EXIT_CALLS = frozenset({"sys.exit", "os._exit", "exit", "quit"})
_INTROSPECT_CALLS = frozenset({
    "inspect.currentframe", "inspect.stack", "inspect.getframeinfo",
    "inspect.getouterframes", "sys._getframe",
})
_TIMER_ATTRS = frozenset({
    "time", "perf_counter", "sleep", "monotonic", "process_time",
})

_MAX_PROPAGATION_ITERATIONS = 10


def _is_forbidden_attr(module_name: str, attr_name: str) -> bool:
    """True when `module_name.attr_name` matches a forbidden-reference pattern.

    Combines three signals:
        - the pair-mode is_blocked_call() blocklist (sys.*, os.*, subprocess.*, ...)
        - the _EXIT_CALLS and _INTROSPECT_CALLS sets used by Check 6
        - time.<timer-attr> monkey-patch targets

    Used for both return-taint and setattr-taint sources so the same notion
    of "forbidden" applies everywhere.
    """
    full = f"{module_name}.{attr_name}"
    if full in _EXIT_CALLS or full in _INTROSPECT_CALLS:
        return True
    if module_name == "time" and attr_name in _TIMER_ATTRS:
        return True
    return is_blocked_call(full)


def _forbidden_attr_pair(node, imported_modules):
    """If `node` is `module.attr` for an imported, forbidden module-attribute,
    return (module_name, attr_name). Otherwise return None.

    Restricted to a single-level Attribute over a Name so two-level chains
    like `os.path.join` (which is not the dangerous direction of the wildcard)
    do not match.
    """
    if (isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in imported_modules
            and _is_forbidden_attr(node.value.id, node.attr)):
        return (node.value.id, node.attr)
    return None


def _iter_self_assigns(method_node):
    """Yield (Attribute target, value) for each `self.<attr> = value` in a method."""
    for sub in ast.walk(method_node):
        if not isinstance(sub, ast.Assign):
            continue
        for tgt in sub.targets:
            if (isinstance(tgt, ast.Attribute)
                    and isinstance(tgt.value, ast.Name)
                    and tgt.value.id == "self"):
                yield sub, tgt


def collect_tainted_names(tree: ast.Module, imported_modules: set) -> dict:
    """Run two-pass intra-file taint analysis on `tree`.

    Returns a dict mapping tainted name → TaintSource. Key conventions:
        function-return taint:   "<funcname>"
        class-attribute taint:   "<ClassName>.<attr>"
        setattr taint:           "<module>.<attr>"
        globals-write taint:     "<key>"
        closure taint:           "<inner_funcname>"
        propagated taint:        "<varname>"

    `imported_modules` is the set of top-level names bound to imported modules
    (the same set the caller already builds via _collect_imported_modules).
    """
    tainted: dict = {}
    globals_aliases: set = set()

    # ------------------------------------------------------------------
    # Pre-pass: identify variables bound to `globals()` so subscript
    # assignments through those variables can be tracked.
    # ------------------------------------------------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            v = node.value
            if (isinstance(v, ast.Call)
                    and isinstance(v.func, ast.Name)
                    and v.func.id == "globals"):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        globals_aliases.add(tgt.id)

    # ------------------------------------------------------------------
    # Pass 1a — return taint and closure taint, both anchored on FunctionDef.
    # ------------------------------------------------------------------
    for func_node in ast.walk(tree):
        if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # CLOSURE TAINT: collect names locally tainted inside this function's
        # body (assignment of a forbidden module-attribute). Then look at every
        # nested FunctionDef and flag those whose body Call-references one of
        # those locals. The inner function's name becomes tainted (+50) so
        # later calls to it are caught by find_tainted_calls.
        local_tainted: dict = {}
        for stmt in func_node.body:
            for sub in ast.walk(stmt):
                if not isinstance(sub, ast.Assign):
                    continue
                pair = _forbidden_attr_pair(sub.value, imported_modules)
                if pair is None:
                    continue
                for tgt in sub.targets:
                    if isinstance(tgt, ast.Name):
                        local_tainted[tgt.id] = f"{pair[0]}.{pair[1]}"

        if local_tainted:
            for inner in ast.walk(func_node):
                if inner is func_node:
                    continue
                if not isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for call_n in ast.walk(inner):
                    if not isinstance(call_n, ast.Call):
                        continue
                    if (isinstance(call_n.func, ast.Name)
                            and call_n.func.id in local_tainted):
                        if inner.name not in tainted:
                            tainted[inner.name] = TaintSource(
                                origin=(
                                    f"closure over '{call_n.func.id}' → "
                                    f"{local_tainted[call_n.func.id]}"
                                ),
                                line=getattr(inner, "lineno", None),
                                score=50,
                                source_type="closure",
                            )
                        break

        # RETURN TAINT: if any Return value is a forbidden module-attribute,
        # the function's bare name becomes tainted (+70). Calls of an
        # already-tainted name in a Return are caught later in propagation.
        for ret in ast.walk(func_node):
            if not isinstance(ret, ast.Return) or ret.value is None:
                continue
            pair = _forbidden_attr_pair(ret.value, imported_modules)
            if pair is None:
                continue
            if func_node.name not in tainted:
                tainted[func_node.name] = TaintSource(
                    origin=f"{pair[0]}.{pair[1]}",
                    line=getattr(ret, "lineno", None),
                    score=70,
                    source_type="return",
                )
            break

    # ------------------------------------------------------------------
    # Pass 1b — class attribute taint. Two flavors:
    #     self.attr = imported.forbidden_attr
    #     self.attr = <name already in tainted>
    # ------------------------------------------------------------------
    for cls_node in ast.walk(tree):
        if not isinstance(cls_node, ast.ClassDef):
            continue
        for item in cls_node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for assign, tgt in _iter_self_assigns(item):
                pair = _forbidden_attr_pair(assign.value, imported_modules)
                key = f"{cls_node.name}.{tgt.attr}"
                if pair is not None:
                    if key not in tainted:
                        tainted[key] = TaintSource(
                            origin=f"{pair[0]}.{pair[1]}",
                            line=getattr(assign, "lineno", None),
                            score=50,
                            source_type="class_attr",
                        )
                elif (isinstance(assign.value, ast.Name)
                      and assign.value.id in tainted):
                    if key not in tainted:
                        tainted[key] = TaintSource(
                            origin=assign.value.id,
                            line=getattr(assign, "lineno", None),
                            score=50,
                            source_type="class_attr",
                        )

    # ------------------------------------------------------------------
    # Pass 1c — setattr(module, "attr", lambda|tainted_name).
    # Fires on ANY imported module (not just sys/builtins/os), because
    # monkey-patching any third-party module with a Python-defined function
    # is high-signal in agent-generated code.
    # ------------------------------------------------------------------
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "setattr"):
            continue
        if len(node.args) < 3:
            continue
        first, second, third = node.args[0], node.args[1], node.args[2]
        if not (isinstance(first, ast.Name) and first.id in imported_modules):
            continue
        if not (isinstance(second, ast.Constant) and isinstance(second.value, str)):
            continue
        third_is_lambda = isinstance(third, ast.Lambda)
        third_is_tainted = isinstance(third, ast.Name) and third.id in tainted
        if not (third_is_lambda or third_is_tainted):
            continue
        key = f"{first.id}.{second.value}"
        if key not in tainted:
            tainted[key] = TaintSource(
                origin=f"setattr({first.id}, {second.value!r}, ...)",
                line=getattr(node, "lineno", None),
                score=70,
                source_type="setattr",
            )

    # ------------------------------------------------------------------
    # Pass 1d — globals subscript writes.
    #     g = globals()
    #     g["ex"] = sys.exit  →  "ex" becomes tainted
    # The key string is what subsequent module-level code will reference.
    # ------------------------------------------------------------------
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not (isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.value, ast.Name)
                    and tgt.value.id in globals_aliases):
                continue
            if not (isinstance(tgt.slice, ast.Constant)
                    and isinstance(tgt.slice.value, str)):
                continue
            key_str = tgt.slice.value
            pair = _forbidden_attr_pair(node.value, imported_modules)
            if pair is not None:
                if key_str not in tainted:
                    tainted[key_str] = TaintSource(
                        origin=(
                            f"globals()[{key_str!r}] = {pair[0]}.{pair[1]}"
                        ),
                        line=getattr(node, "lineno", None),
                        score=70,
                        source_type="globals",
                    )
            elif (isinstance(node.value, ast.Name)
                  and node.value.id in tainted):
                if key_str not in tainted:
                    tainted[key_str] = TaintSource(
                        origin=f"globals()[{key_str!r}] = {node.value.id}",
                        line=getattr(node, "lineno", None),
                        score=70,
                        source_type="globals",
                    )

    # ------------------------------------------------------------------
    # Pass 2 — propagation to a fixed point.
    # Two rules iterate until no new names appear:
    #     return-of-tainted    → outer function becomes tainted
    #     x = tainted_name     → x becomes tainted (propagated, same score)
    #     x = tainted_name()   → x becomes tainted (propagated, same score)
    # ------------------------------------------------------------------
    assign_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)]
    func_nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    for _ in range(_MAX_PROPAGATION_ITERATIONS):
        changed = False

        # Re-check returns: a return that yields a tainted Name or a call to
        # a tainted Name promotes the enclosing function.
        for fn in func_nodes:
            if fn.name in tainted:
                continue
            for ret in ast.walk(fn):
                if not isinstance(ret, ast.Return) or ret.value is None:
                    continue
                val = ret.value
                if isinstance(val, ast.Name) and val.id in tainted:
                    tainted[fn.name] = TaintSource(
                        origin=f"returns tainted name '{val.id}'",
                        line=getattr(ret, "lineno", None),
                        score=70,
                        source_type="return",
                    )
                    changed = True
                    break
                if (isinstance(val, ast.Call)
                        and isinstance(val.func, ast.Name)
                        and val.func.id in tainted):
                    tainted[fn.name] = TaintSource(
                        origin=f"returns call to tainted '{val.func.id}()'",
                        line=getattr(ret, "lineno", None),
                        score=70,
                        source_type="return",
                    )
                    changed = True
                    break

        # Simple-assignment propagation.
        for n in assign_nodes:
            value = n.value
            source_key = None
            if isinstance(value, ast.Name) and value.id in tainted:
                source_key = value.id
            elif (isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id in tainted):
                source_key = value.func.id
            if source_key is None:
                continue
            src = tainted[source_key]
            for tgt in n.targets:
                if isinstance(tgt, ast.Name) and tgt.id not in tainted:
                    tainted[tgt.id] = TaintSource(
                        origin=source_key,
                        line=getattr(n, "lineno", None),
                        score=src.score,
                        source_type="propagated",
                    )
                    changed = True

        if not changed:
            break

    return tainted


def find_tainted_calls(tree: ast.Module, tainted: dict) -> list:
    """Walk `tree` for Call nodes that resolve to a tainted name.

    Recognised call shapes:
        Name(id=<key>)(...)                    → tainted as `<key>`
        Attribute(Name('self'), <attr>)(...)   → tainted as `<ClassName>.<attr>`,
                                                  where ClassName is the class
                                                  that defines the enclosing method

    Returns a list of `(call_node, tainted_key, TaintSource)` tuples. The
    caller decides what severity to attach (Check 6 uses +70 each).
    """
    if not tainted:
        return []

    # Map every method (and nested function) back to its defining class so
    # `self.<attr>(...)` can resolve "ClassName.<attr>" without an enclosing
    # scope tracker.
    class_for_func: dict = {}
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for item in cls.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for sub in ast.walk(item):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    class_for_func[id(sub)] = cls.name

    func_for_call: dict = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call):
                func_for_call.setdefault(id(sub), fn)

    results = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        key = None
        if isinstance(node.func, ast.Name) and node.func.id in tainted:
            key = node.func.id
        elif (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"):
            enclosing = func_for_call.get(id(node))
            if enclosing is not None:
                cls_name = class_for_func.get(id(enclosing))
                if cls_name is not None:
                    candidate = f"{cls_name}.{node.func.attr}"
                    if candidate in tainted:
                        key = candidate
        if key is not None:
            results.append((node, key, tainted[key]))
    return results
