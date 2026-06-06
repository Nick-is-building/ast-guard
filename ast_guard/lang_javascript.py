"""
JavaScript / TypeScript language adapter (v1.4, Phase 2).

Parses JS source via tree-sitter-javascript and emits the same metric dict
shape produced by ``ast_guard.analyzer.extract_metrics`` for Python.

Requires the optional ``ast-guard[multilang]`` extras.
"""

from __future__ import annotations

DANGEROUS_CALLS = frozenset({
    "eval", "Function", "execSync", "spawn", "exec",
    "spawnSync", "execFile", "execFileSync",
})

DANGEROUS_IMPORTS = frozenset({
    "child_process", "fs", "net", "dgram", "cluster", "vm",
})

_BRANCH_NODES = frozenset({
    "if_statement",
    "for_statement", "for_in_statement", "for_of_statement",
    "while_statement", "do_statement",
    "switch_case", "case",
    "ternary_expression",
    "catch_clause",
})

_LOOP_NODES = frozenset({
    "for_statement", "for_in_statement", "for_of_statement",
    "while_statement", "do_statement",
})

_LITERAL_NODES = frozenset({
    "string", "template_string", "number", "regex",
    "true", "false", "null", "undefined",
})

_FUNCTION_NODES = frozenset({
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "generator_function_declaration",
    "generator_function",
})


def _import_tree_sitter():
    """Lazy-import tree-sitter so core ast-guard stays zero-dep."""
    try:
        import tree_sitter
        import tree_sitter_javascript
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "JavaScript analysis requires the multilang extras: "
            "`pip install ast-guard[multilang]`"
        ) from exc
    return tree_sitter, tree_sitter_javascript


_LANGUAGE = None
_PARSER = None


def _get_parser():
    """Lazily build the singleton tree-sitter parser bound to JavaScript."""
    global _LANGUAGE, _PARSER
    if _PARSER is None:
        ts, tsjs = _import_tree_sitter()
        _LANGUAGE = ts.Language(tsjs.language())
        _PARSER = ts.Parser(_LANGUAGE)
    return _PARSER


def _node_text(node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _walk_skip_funcs(node, skip_root=True):
    """Pre-order walk that doesn't descend into nested function bodies."""
    if not skip_root and node.type in _FUNCTION_NODES:
        return
    yield node
    for child in node.children:
        if child.type in _FUNCTION_NODES:
            continue
        yield from _walk_skip_funcs(child, skip_root=False)


def _resolve_callee(func_node) -> str | None:
    """Best-effort dotted name for the callee of a call_expression."""
    if func_node is None:
        return None
    t = func_node.type
    if t == "identifier" or t == "property_identifier":
        return _node_text(func_node)
    if t == "member_expression":
        obj = func_node.child_by_field_name("object")
        prop = func_node.child_by_field_name("property")
        base = _resolve_callee(obj) if obj is not None else None
        leaf = _node_text(prop) if prop is not None else None
        if base and leaf:
            return f"{base}.{leaf}"
        return leaf
    if t == "super":
        return "super"
    if t == "this":
        return "this"
    if t == "import":
        return "import"
    return None


def _string_literal_value(node) -> str | None:
    """If ``node`` is a string-like literal, return its contents (no quotes)."""
    if node is None:
        return None
    if node.type == "string":
        for c in node.children:
            if c.type == "string_fragment":
                return _node_text(c)
        text = _node_text(node)
        if len(text) >= 2 and text[0] in ("'", '"') and text[-1] == text[0]:
            return text[1:-1]
        return text
    if node.type == "template_string":
        text = _node_text(node)
        if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
            return text[1:-1]
        return text
    return None


def _extract_calls_and_imports(root):
    """Collect call_list, import_list, and dynamic require/import() targets."""
    calls: list[str] = []
    imports: set[str] = set()

    for node in _walk(root):
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            name = _resolve_callee(func)
            if name:
                calls.append(name)
            # require('...') and import('...') both surface their target string.
            if name in ("require", "import"):
                args = node.child_by_field_name("arguments")
                if args is not None:
                    for arg in args.children:
                        target = _string_literal_value(arg)
                        if target:
                            imports.add(target)
                            break
        elif node.type == "new_expression":
            constructor = node.child_by_field_name("constructor")
            name = _resolve_callee(constructor)
            if name:
                calls.append(name)
        elif node.type == "import_statement":
            source = node.child_by_field_name("source")
            target = _string_literal_value(source)
            if target:
                imports.add(target)
        elif node.type == "export_statement":
            # `export ... from '...'` — capture the source if present.
            source = node.child_by_field_name("source")
            target = _string_literal_value(source)
            if target:
                imports.add(target)

    return calls, sorted(imports)


def _loop_depth(root) -> int:
    """Maximum nesting depth of any loop construct."""
    max_depth = 0

    def visit(node, depth):
        nonlocal max_depth
        cur = depth + 1 if node.type in _LOOP_NODES else depth
        if cur > max_depth:
            max_depth = cur
        for child in node.children:
            if child.type in _FUNCTION_NODES:
                continue
            visit(child, cur)

    visit(root, 0)
    return max_depth


def _calculate_complexity(root) -> int:
    """McCabe complexity over a function body or the module."""
    complexity = 1
    for node in _walk_skip_funcs(root, skip_root=True):
        if node.type in _BRANCH_NODES:
            complexity += 1
        elif node.type == "binary_expression":
            for child in node.children:
                if child.type in ("&&", "||", "??"):
                    complexity += 1
    return complexity


def _count_ifs(root) -> int:
    """Count every if_statement node (including chained `else if`)."""
    n = 0
    for node in _walk(root):
        if node.type == "if_statement":
            n += 1
    return n


def _count_literals_and_long_strings(root):
    """Return (literal_count, long_string_count)."""
    literal_count = 0
    long_string_count = 0
    for node in _walk(root):
        if node.type in _LITERAL_NODES:
            literal_count += 1
            if node.type in ("string", "template_string"):
                value = _string_literal_value(node)
                if value is not None and len(value) > 200:
                    long_string_count += 1
    return literal_count, long_string_count


def _function_name(node) -> str:
    """Best-effort name for a function-ish node."""
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text(name_node)
    # method_definition's name field is "name" but the property_identifier
    # might also live as a direct child of a pair / declarator.
    parent = node.parent
    if parent is not None:
        if parent.type == "variable_declarator":
            n = parent.child_by_field_name("name")
            if n is not None:
                return _node_text(n)
        if parent.type == "pair":
            k = parent.child_by_field_name("key")
            if k is not None:
                return _node_text(k)
        if parent.type == "assignment_expression":
            left = parent.child_by_field_name("left")
            if left is not None:
                return _node_text(left)
    return "<anonymous>"


def _collect_function_complexities(root) -> dict[str, int]:
    """Per-function McCabe complexity keyed by qualified name."""
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
        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            cname = _node_text(name_node) if name_node is not None else "<anon>"
            child_prefix = f"{prefix}.{cname}" if prefix else cname
        else:
            child_prefix = prefix
        for child in node.children:
            visit(child, child_prefix)

    visit(root, "")
    return complexities


def _is_js_literal(node) -> bool:
    """Return True if ``node`` is a JavaScript literal value."""
    return node.type in ("string", "number", "true", "false", "null")


def _switch_case_is_literal(switch_case_node) -> bool:
    """Return True if a switch_case matches a literal value (not a variable)."""
    for c in switch_case_node.children:
        if not c.is_named:
            continue
        return _is_js_literal(c)
    return False


def _if_condition_has_literal(if_node) -> bool:
    """Return True if the if-condition is a literal equality comparison (=== or ==)."""
    for c in if_node.children:
        if c.type != "parenthesized_expression":
            continue
        for inner in c.children:
            if inner.type != "binary_expression":
                continue
            ops = {ch.type for ch in inner.children}
            if "===" not in ops and "==" not in ops:
                continue
            named = [ch for ch in inner.children if ch.is_named]
            if any(_is_js_literal(n) for n in named):
                return True
    return False


def _collect_enumeration_analysis(root) -> list:
    """
    Per-function enumeration pattern statistics for Check 5.

    For each function returns:
        {"name": str, "total_ifs": int, "enumeration_ifs": int, "loop_count": int}

    total_ifs       — if_statement + switch_case nodes in the function body
    enumeration_ifs — subset with a literal constant in the branch condition
    loop_count      — for/while/do loop nodes in the function body

    Known limitation: the object-as-lookup dispatch pattern
        ``const actions = { foo: fn, bar: fn2 }; actions[var]();``
    is not detected as enumeration. Detecting it requires tracking the
    variable type through assignment, which is beyond tree-sitter structural
    analysis and would belong to a future dataflow pass.
    """
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
        elif node.type == "class_declaration":
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


def extract_metrics(code: str) -> dict:
    """
    Parse JavaScript source and return ast-guard's standard metric dictionary.
    Includes the JS-specific ``dangerous_calls`` and ``dangerous_imports``
    fields alongside the language-neutral keys.
    """
    parser = _get_parser()
    src = code.encode("utf-8")
    tree = parser.parse(src)
    root = tree.root_node

    if_count = _count_ifs(root)
    loop_depth = _loop_depth(root)
    mccabe_complexity = _calculate_complexity(root)
    literal_count, long_string_count = _count_literals_and_long_strings(root)
    call_list, import_list = _extract_calls_and_imports(root)
    function_complexities = _collect_function_complexities(root)
    enumeration_analysis = _collect_enumeration_analysis(root)

    dangerous_calls = sorted({
        c for c in call_list
        # Match either the bare name (`eval`) or any member call ending in it
        # (`cp.execSync` -> ends with `.execSync`).
        if c in DANGEROUS_CALLS or c.split(".")[-1] in DANGEROUS_CALLS
    })
    dangerous_imports = sorted({
        imp for imp in import_list
        # `child_process` matches directly; `node:fs` matches via the suffix.
        if imp in DANGEROUS_IMPORTS or imp.split("/")[-1].split(":")[-1] in DANGEROUS_IMPORTS
    })

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
        "language": "javascript",
    }
