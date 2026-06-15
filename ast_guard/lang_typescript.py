"""
TypeScript language adapter (v1.0, IR-contract).

Thin extension of the JavaScript adapter: reuses the JS DANGEROUS_CALLS /
DANGEROUS_IMPORTS registry and all runtime metric logic. Adds TS-specific
exclusions so type-level constructs do not inflate runtime metrics.

Type-level subtrees excluded from literal / loop / if counting:
  type_alias_declaration   -- ``type T = "a" | "b"``
  type_annotation          -- ``: string``, ``: number``, ``: Promise<T>``
  type_parameters          -- ``<T extends {}>``
  interface_declaration    -- entire interface body
  enum_body                -- enum member initialisers

enum members: string/number values live inside enum_body and are therefore
excluded from literal_count. This is documented behaviour, not a gap.

Decorators (@Foo): the call_expression inside a decorator is a real runtime
call and is included in call_set normally.

abstract_class_declaration is treated identically to class_declaration for
complexity collection.

abstract_method_signature has no body; it is not in _FUNCTION_NODES and is
therefore skipped during function complexity collection.

Enhancement-flag contract (see ir.EnhancementFlags):
  match_case_enumeration = "partial"   -- Flag C: same as JS
  docstring_exclusion     = "partial"  -- JSDoc appears as comment nodes, not
    string literals; this flag is informational rather than active filtering.
  All other flags = "not_applicable".
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Re-use JS constants and stateless helpers verbatim
# ---------------------------------------------------------------------------
from ast_guard.lang_javascript import (
    DANGEROUS_CALLS,
    DANGEROUS_IMPORTS,
    _BRANCH_NODES,
    _FUNCTION_NODES,
    _LITERAL_NODES,
    _LOGICAL_OPS,
    _LOOP_NODES,
    _build_dangerous_call_events,
    _calculate_complexity,
    _count_ifs,
    _count_non_trivial_binops,
    _extract_calls_and_imports,
    _function_name,
    _if_condition_has_literal,
    _is_js_literal,
    _loop_depth,
    _node_text,
    _resolve_callee,
    _string_literal_value,
    _switch_case_is_literal,
    _walk,
    _walk_skip_funcs,
)
from ast_guard.ir import DangerousCallEvent  # noqa: F401 (re-exported for callers)

# ---------------------------------------------------------------------------
# TS-specific node sets
# ---------------------------------------------------------------------------

# Subtrees whose content is type-level only; skipped by _walk_ts_runtime.
_TS_TYPE_SKIP = frozenset({
    "type_alias_declaration",
    "type_annotation",
    "type_parameters",
    "interface_declaration",
    "enum_body",
})

# TS adds abstract_class_declaration alongside JS class_declaration.
_TS_CLASS_NODES = frozenset({"class_declaration", "abstract_class_declaration"})


# ---------------------------------------------------------------------------
# Parser singleton
# ---------------------------------------------------------------------------

_LANGUAGE = None
_PARSER = None


def _import_tree_sitter_ts():
    """Lazy-import tree-sitter-typescript so core ast-guard stays zero-dep."""
    try:
        import tree_sitter
        import tree_sitter_typescript
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "TypeScript analysis requires the multilang extras: "
            "`pip install ast-guard[multilang]` and "
            "`pip install tree-sitter-typescript`"
        ) from exc
    return tree_sitter, tree_sitter_typescript


def _get_parser():
    """Lazily build the singleton tree-sitter parser bound to TypeScript."""
    global _LANGUAGE, _PARSER
    if _PARSER is None:
        ts, tsty = _import_tree_sitter_ts()
        _LANGUAGE = ts.Language(tsty.language_typescript())
        _PARSER = ts.Parser(_LANGUAGE)
    return _PARSER


# ---------------------------------------------------------------------------
# TS-aware walk: skip type-level subtrees
# ---------------------------------------------------------------------------

def _walk_ts_runtime(node):
    """Pre-order walk that skips TS type-level subtrees.

    Entering any node in _TS_TYPE_SKIP suppresses the whole subtree so
    string literals inside type annotations, interface bodies, and enum
    member initialisers do not inflate runtime metrics.
    """
    if node.type in _TS_TYPE_SKIP:
        return
    yield node
    for child in node.children:
        yield from _walk_ts_runtime(child)


# ---------------------------------------------------------------------------
# Metric collectors (TS-aware overrides)
# ---------------------------------------------------------------------------

def _count_literals_and_long_strings_ts(root):
    """Count runtime literals, excluding TS type-level constructs."""
    literal_count = 0
    long_string_count = 0
    for node in _walk_ts_runtime(root):
        if node.type in _LITERAL_NODES:
            literal_count += 1
            if node.type in ("string", "template_string"):
                value = _string_literal_value(node)
                if value is not None and len(value) > 200:
                    long_string_count += 1
    return literal_count, long_string_count


def _collect_function_complexities_ts(root) -> dict[str, int]:
    """Per-function McCabe complexity; handles abstract_class_declaration."""
    complexities: dict[str, int] = {}

    def visit(node, prefix: str):
        if node.type in _FUNCTION_NODES:
            name = _function_name(node)
            qname = f"{prefix}.{name}" if prefix else name
            key = qname
            i = 2
            while key in complexities:
                key = f"{qname}#{i}"
                i += 1
            body = node.child_by_field_name("body")
            target = body if body is not None else node
            complexities[key] = _calculate_complexity(target)
            child_prefix = qname
        elif node.type in _TS_CLASS_NODES:
            name_node = node.child_by_field_name("name")
            cname = _node_text(name_node) if name_node is not None else "<anon>"
            child_prefix = f"{prefix}.{cname}" if prefix else cname
        else:
            child_prefix = prefix
        for child in node.children:
            visit(child, child_prefix)

    visit(root, "")
    return complexities


def _collect_enumeration_analysis_ts(root) -> list:
    """Per-function enumeration statistics; handles abstract_class_declaration."""
    result: list[dict] = []

    def _analyze(func_node, name: str) -> None:
        body = func_node.child_by_field_name("body")
        target = body if body is not None else func_node

        total_ifs = 0
        enum_ifs = 0
        loop_count = 0

        for node in _walk_skip_funcs(target, skip_root=False):
            t = node.type
            if t == "if_statement":
                total_ifs += 1
                if _if_condition_has_literal(node):
                    enum_ifs += 1
            elif t == "switch_case":
                total_ifs += 1
                if _switch_case_is_literal(node):
                    enum_ifs += 1
            elif t in _LOOP_NODES:
                loop_count += 1

        result.append({
            "name": name,
            "total_ifs": total_ifs,
            "enumeration_ifs": enum_ifs,
            "loop_count": loop_count,
        })

    def _visit(node, prefix: str) -> None:
        if node.type in _FUNCTION_NODES:
            name = _function_name(node)
            qname = f"{prefix}.{name}" if prefix else name
            _analyze(node, qname)
            body = node.child_by_field_name("body")
            if body is not None:
                for c in body.children:
                    _visit(c, qname)
        elif node.type in _TS_CLASS_NODES:
            name_node = node.child_by_field_name("name")
            cname = _node_text(name_node) if name_node is not None else "<anon>"
            child_prefix = f"{prefix}.{cname}" if prefix else cname
            for c in node.children:
                _visit(c, child_prefix)
        else:
            for c in node.children:
                _visit(c, prefix)

    _visit(root, "")
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_metrics(code: str) -> dict:
    """
    Parse TypeScript source and return ast-guard's standard metric dictionary.

    Uses the JS DANGEROUS_CALLS / DANGEROUS_IMPORTS registry. Type-level
    constructs (type aliases, interfaces, enum member values, type annotations,
    generic type parameters) are excluded from runtime metrics.
    """
    parser = _get_parser()
    src = code.encode("utf-8")
    tree = parser.parse(src)
    root = tree.root_node

    if_count = _count_ifs(root)
    loop_depth = _loop_depth(root)
    mccabe_complexity = _calculate_complexity(root)
    literal_count, long_string_count = _count_literals_and_long_strings_ts(root)
    call_list, import_list = _extract_calls_and_imports(root)
    function_complexities = _collect_function_complexities_ts(root)
    enumeration_analysis = _collect_enumeration_analysis_ts(root)
    non_trivial_binop_count = _count_non_trivial_binops(root)

    dangerous_calls = sorted({
        c for c in call_list
        if c in DANGEROUS_CALLS or c.split(".")[-1] in DANGEROUS_CALLS
    })
    dangerous_imports = sorted({
        imp for imp in import_list
        if imp in DANGEROUS_IMPORTS or imp.split("/")[-1].split(":")[-1] in DANGEROUS_IMPORTS
    })
    dangerous_call_events = _build_dangerous_call_events(call_list, root)

    return {
        "if_count": if_count,
        "guard_clause_count": 0,
        "loop_depth": loop_depth,
        "mccabe_complexity": mccabe_complexity,
        "literal_count": literal_count,
        "long_string_count": long_string_count,
        "import_list": import_list,
        "call_list": call_list,
        "comprehension_count": 0,
        "functional_call_count": 0,
        "max_set_literal_size": 0,
        "max_dict_literal_size": 0,
        "function_complexities": function_complexities,
        "enumeration_analysis": enumeration_analysis,
        "dangerous_calls": dangerous_calls,
        "dangerous_imports": dangerous_imports,
        "non_trivial_binop_count": non_trivial_binop_count,
        "dangerous_call_events": dangerous_call_events,
        "dispatch_analysis": [],  # not_applicable for TS; planned for next block
        "language": "typescript",
    }
