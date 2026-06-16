"""
JavaScript / TypeScript language adapter (v1.6, IR-contract).

Parses JS source via tree-sitter-javascript and emits both the standard
ast-guard metric dict and pre-built DangerousCallEvent entries for the IR.

Requires the optional ``ast-guard[multilang]`` extras.

Enhancement-flag contract (see ir.EnhancementFlags):
  match_case_enumeration = "partial"   — Flag C: switch/case enumeration is
    detected only for literal-valued cases.
  dispatch_table = "supported"         — return TABLE[key] / TABLE.get(key) /
    new Map([[k,v],...]).get(key). All-literal tables keyed by a parameter
    or a trivial coercion thereof. Excludes computed values (arrow fns, calls),
    derived keys (x%7, +x), and ``as const`` type assertions (TS).
  All other flags = "not_applicable".

Anonymous function naming — Flag D:
  Functions with no resolvable name receive the synthetic identity
  "<anon@{line}>" where line is 1-indexed. This makes Check 2 function-level
  matching stable across orig/gen when the same anonymous function is present
  at the same source position.
"""

from __future__ import annotations

from ast_guard.ir import DangerousCallEvent

DANGEROUS_CALLS = frozenset({
    "eval", "Function", "execSync", "spawn", "exec",
    "spawnSync", "execFile", "execFileSync",
})

DANGEROUS_IMPORTS = frozenset({
    "child_process", "fs", "net", "dgram", "cluster", "vm",
})

# Logical short-circuit operators: already counted by McCabe, excluded from
# non_trivial_binop_count so the metric aligns with the Python BinOp count.
_LOGICAL_OPS = frozenset({"&&", "||", "??"})

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
    """Best-effort name for a function-ish node.

    Returns a synthetic "<anon@{line}>" identity (Flag D) when no static name
    is resolvable, so Check 2 can match the same anonymous function across
    orig/gen by source position.
    """
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
    # Flag D: 1-indexed line number makes the identity stable and debuggable.
    return f"<anon@{node.start_point[0] + 1}>"


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


# ---------------------------------------------------------------------------
# Dispatch-table detection helpers (Check 5 sub-rule, object/Map form)
# ---------------------------------------------------------------------------

# Trivial scalar coercions accepted as param-keyed access (mirrors Python's _COERCE_CALLS).
# Excluded (documented): x%7 (arithmetic), +x (unary numeric, changes type semantics).
_JS_COERCE_CALLS = frozenset({"Number", "String", "Boolean", "parseInt", "parseFloat"})


def _js_is_const_expr(node) -> bool:
    """True when ``node`` is a JS compile-time constant expression.

    Accepted: string/number/true/false/null/undefined literals; arrays and
    objects whose every element/pair is also constant; unary negation of a
    constant number.  Rejected: identifier (runtime variable), call,
    arrow/function expression, template_string with substitutions, spread.
    """
    if node is None:
        return False
    t = node.type
    if t in ("string", "number", "true", "false", "null", "undefined"):
        return True
    if t == "array":
        for c in node.named_children:
            if c.type == "spread_element" or not _js_is_const_expr(c):
                return False
        return True
    if t == "object":
        return _js_all_literal_object(node)
    if t == "unary_expression":
        arg = node.child_by_field_name("argument")
        if arg is not None:
            has_neg = any(
                not ch.is_named and ch.type == "-" for ch in node.children
            )
            if has_neg:
                return _js_is_const_expr(arg)
    return False


def _js_is_const_key(node) -> bool:
    """True when ``node`` is a constant object-literal key.

    Uncomputed identifier and property_identifier keys in object literals
    denote their literal string name (e.g. ``{foo: 1}`` → key "foo").
    computed_property_name (``[expr]``) is excluded.
    """
    if node is None:
        return False
    t = node.type
    if t in ("identifier", "property_identifier"):
        return True
    return _js_is_const_expr(node)


def _js_all_literal_object(node) -> bool:
    """True when all entries in an object literal are constant key-value pairs.

    Rejects: spread_element, shorthand_property_identifier, method_definition,
    computed_property_name, or any pair whose key/value is not constant.
    """
    for c in node.named_children:
        if c.type != "pair":
            return False
        k = c.child_by_field_name("key")
        v = c.child_by_field_name("value")
        if k is None or v is None:
            return False
        if not _js_is_const_key(k) or not _js_is_const_expr(v):
            return False
    return True


def _js_object_table_info(node) -> tuple:
    """Return (entry_count, all_literal) for an object literal or new Map([...]).

    Transparently unwraps TypeScript type-assertion wrappers before analysis:
      as_expression        -- ``{...} as const``, ``{...} as T``
      satisfies_expression -- ``{...} satisfies Record<K,V>``
    Both wrappers are structural-only; the runtime object is unchanged.
    """
    if node is None:
        return 0, False
    # Unwrap TS-only wrappers: as_expression and satisfies_expression both carry
    # the runtime value as their first named child.
    while node.type in ("as_expression", "satisfies_expression"):
        named = node.named_children
        if not named:
            return 0, False
        node = named[0]
    t = node.type

    if t == "object":
        pairs = [c for c in node.named_children if c.type == "pair"]
        non_pair = [c for c in node.named_children if c.type != "pair"]
        size = len(pairs)
        if size == 0:
            return 0, False
        all_lit = (not non_pair) and _js_all_literal_object(node)
        return size, all_lit

    if t == "new_expression":
        constructor = node.child_by_field_name("constructor")
        if constructor is None or _node_text(constructor) != "Map":
            return 0, False
        args_node = node.child_by_field_name("arguments")
        if args_node is None:
            return 0, False
        outer = next(
            (c for c in args_node.named_children if c.type == "array"), None
        )
        if outer is None:
            return 0, False
        entries = [c for c in outer.named_children if c.type == "array"]
        if not entries:
            return 0, False
        all_lit = True
        for entry in entries:
            elems = entry.named_children
            if len(elems) < 2:
                all_lit = False
                break
            if not _js_is_const_expr(elems[0]) or not _js_is_const_expr(elems[1]):
                all_lit = False
                break
        return len(entries), all_lit

    return 0, False


def _js_func_params(func_node) -> frozenset:
    """Flat set of simple formal parameter names for a function node.

    Handles: plain identifiers, parameters with default values (assignment_pattern),
    rest parameters, single-identifier arrow-function parameters (``x => ...``),
    and TypeScript required_parameter / optional_parameter / rest_parameter wrappers.
    Skips destructuring patterns (object_pattern, array_pattern); dispatch hacks
    use simple scalar parameters, not destructured ones.
    """
    params_node = func_node.child_by_field_name("parameters")
    single_param = False
    if params_node is None:
        params_node = func_node.child_by_field_name("parameter")
        single_param = True
    if params_node is None:
        return frozenset()

    names: set = set()
    if single_param:
        if params_node.type == "identifier":
            names.add(_node_text(params_node))
        return frozenset(names)

    for child in params_node.named_children:
        if child.type == "identifier":
            names.add(_node_text(child))
        elif child.type == "assignment_pattern":
            left = child.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                names.add(_node_text(left))
        elif child.type in ("rest_pattern", "rest_parameter"):
            for gc in child.named_children:
                if gc.type == "identifier":
                    names.add(_node_text(gc))
                    break
        elif child.type in ("required_parameter", "optional_parameter"):
            # TypeScript typed parameter: get name from 'pattern' field or first identifier
            name_node = child.child_by_field_name("pattern")
            if name_node is None:
                name_node = next(
                    (gc for gc in child.named_children if gc.type == "identifier"), None
                )
            if name_node is not None and name_node.type == "identifier":
                names.add(_node_text(name_node))
        # object_pattern / array_pattern: skip (destructured params)
    return frozenset(names)


def _js_is_param_key(key_node, params: frozenset) -> bool:
    """True when ``key_node`` is or trivially derives from a single function parameter.

    Accepted coercions: Number(x), String(x), Boolean(x), parseInt(x),
    parseFloat(x), x.toString(), and the single-substitution template literal
    with only ``${x}`` as content.

    Excluded (documented): x%7 (arithmetic modulo, changes the key domain),
    +x (unary numeric coercion, domain-changing in JS), x+const (shift).
    """
    if key_node is None:
        return False
    t = key_node.type

    if t == "identifier" and _node_text(key_node) in params:
        return True

    if t == "call_expression":
        func = key_node.child_by_field_name("function")
        args_node = key_node.child_by_field_name("arguments")
        named_args = args_node.named_children if args_node is not None else []

        # Number(x) / String(x) / Boolean(x) / parseInt(x) / parseFloat(x)
        if (func is not None and func.type == "identifier"
                and _node_text(func) in _JS_COERCE_CALLS
                and len(named_args) == 1
                and named_args[0].type == "identifier"
                and _node_text(named_args[0]) in params):
            return True

        # x.toString() — member call on the param with no arguments
        if func is not None and func.type == "member_expression":
            obj = func.child_by_field_name("object")
            prop = func.child_by_field_name("property")
            if (obj is not None and obj.type == "identifier"
                    and _node_text(obj) in params
                    and prop is not None
                    and _node_text(prop) == "toString"
                    and len(named_args) == 0):
                return True

    # `${x}` — template_string with exactly one substitution of a single param identifier
    if t == "template_string":
        subs = [c for c in key_node.named_children if c.type == "template_substitution"]
        non_subs = [c for c in key_node.named_children if c.type != "template_substitution"]
        if len(subs) == 1 and not non_subs:
            sub_children = subs[0].named_children
            if (len(sub_children) == 1
                    and sub_children[0].type == "identifier"
                    and _node_text(sub_children[0]) in params):
                return True

    return False


def _js_collect_module_tables(root) -> dict:
    """Collect top-level {name: (size, all_literal)} object/Map bindings.

    Handles both direct declarations and ``export const TABLE = ...`` forms.
    """
    tables: dict = {}
    for node in root.named_children:
        decl = None
        if node.type in ("lexical_declaration", "variable_declaration"):
            decl = node
        elif node.type == "export_statement":
            decl = node.child_by_field_name("declaration")
        if decl is not None and decl.type in ("lexical_declaration", "variable_declaration"):
            for child in decl.named_children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")
                    if (name_node is not None and name_node.type == "identifier"
                            and value_node is not None):
                        sz, al = _js_object_table_info(value_node)
                        if sz > 0:
                            name = _node_text(name_node)
                            if name not in tables:
                                tables[name] = (sz, al)
    return tables


def _js_collect_local_tables(func_node) -> dict:
    """Collect {name: (size, all_literal)} for object/Map bindings in one function scope.

    BFS over the function body; does not descend into nested function bodies so
    each function's local scope is self-contained.
    """
    body = func_node.child_by_field_name("body")
    if body is None or body.type != "statement_block":
        return {}

    tables: dict = {}
    queue = list(body.named_children)
    while queue:
        node = queue.pop(0)
        if node.type in _FUNCTION_NODES:
            continue
        if node.type in ("lexical_declaration", "variable_declaration"):
            for child in node.named_children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")
                    if (name_node is not None and name_node.type == "identifier"
                            and value_node is not None):
                        sz, al = _js_object_table_info(value_node)
                        if sz > 0:
                            name = _node_text(name_node)
                            if name not in tables:
                                tables[name] = (sz, al)
        for c in node.named_children:
            queue.append(c)
    return tables


def _js_check_dispatch_return(ret_value, params: frozenset,
                              local_tables: dict, module_tables: dict) -> tuple:
    """Check if ``ret_value`` is a dispatch lookup keyed by a function parameter.

    Detects:
      TABLE[param]              — subscript_expression on object or Map variable
      TABLE?.[param]            — optional-chain subscript (same field layout)
      TABLE[param] ?? default   — nullish-coalesced subscript
      TABLE.get(param)          — Map/object .get() call
      TABLE.get(param, default) — .get() with default

    Returns (table_size, all_literal) or (0, False) when the pattern is absent.
    """
    if ret_value is None:
        return 0, False
    t = ret_value.type

    # Unwrap parenthesized expressions: (TABLE[key]) or ({k:v,...}[key])
    if t == "parenthesized_expression":
        named = ret_value.named_children
        if named:
            ret_value = named[0]
            t = ret_value.type

    # Unwrap TABLE[key] ?? default → examine the left operand
    if t == "binary_expression":
        op = next((c.type for c in ret_value.children if not c.is_named), None)
        if op == "??":
            named = ret_value.named_children
            if named:
                ret_value = named[0]
                t = ret_value.type
        else:
            return 0, False

    # TABLE[key] or TABLE?.[key] → subscript_expression (optional_chain is an
    # extra unnamed child; object and index fields are present regardless)
    if t == "subscript_expression":
        obj = ret_value.child_by_field_name("object")
        index = ret_value.child_by_field_name("index")
        if obj is None or index is None:
            return 0, False
        if not _js_is_param_key(index, params):
            return 0, False
        # Unwrap ({...} as const)[x]: parenthesized_expression around an as/satisfies
        if obj.type == "parenthesized_expression":
            named = obj.named_children
            obj = named[0] if named else obj
        # Named table reference (identifier → look up in collected tables)
        if obj.type == "identifier":
            info = local_tables.get(_node_text(obj)) or module_tables.get(_node_text(obj))
            if info is not None:
                return info
            return 0, False
        # Inline table: object literal, as_expression, satisfies_expression, or new Map
        return _js_object_table_info(obj)

    # TABLE.get(key) or TABLE.get(key, default)
    if t == "call_expression":
        func = ret_value.child_by_field_name("function")
        args_node = ret_value.child_by_field_name("arguments")
        if func is None or func.type != "member_expression":
            return 0, False
        prop = func.child_by_field_name("property")
        if prop is None or _node_text(prop) != "get":
            return 0, False
        if args_node is None:
            return 0, False
        named_args = args_node.named_children
        if not named_args or not _js_is_param_key(named_args[0], params):
            return 0, False
        obj = func.child_by_field_name("object")
        if obj is None or obj.type != "identifier":
            return 0, False
        info = local_tables.get(_node_text(obj)) or module_tables.get(_node_text(obj))
        if info is not None:
            return info

    return 0, False


def _js_scan_dispatch_in_func(func_node, module_tables: dict) -> tuple:
    """Scan one function for the largest all-literal dispatch return pattern.

    Mirrors Python's _scan_dispatch_in_func: BFS over the function body, skips
    nested function bodies, tracks local table bindings, and checks every return
    value.  Returns (max_table_size, all_literal).
    """
    params = _js_func_params(func_node)
    if not params:
        return 0, False

    local_tables = _js_collect_local_tables(func_node)
    body_node = func_node.child_by_field_name("body")
    if body_node is None:
        return 0, False

    returns: list = []
    if body_node.type != "statement_block":
        # Expression-body arrow function: ``(x) => TABLE[x]``
        returns.append(body_node)
    else:
        queue = list(body_node.named_children)
        while queue:
            node = queue.pop(0)
            if node.type in _FUNCTION_NODES:
                continue
            if node.type == "return_statement":
                named = node.named_children
                if named:
                    returns.append(named[0])
            for c in node.named_children:
                queue.append(c)

    max_size = 0
    all_lit = False
    for ret_value in returns:
        sz, al = _js_check_dispatch_return(ret_value, params, local_tables, module_tables)
        if sz > max_size:
            max_size = sz
            all_lit = al
    return max_size, all_lit


def _collect_dispatch_analysis(root) -> list:
    """Per-function dispatch-table detection. Mirrors Python's analyze_dispatch_tables.

    Returns list of {"name": str, "dispatch_table_size": int, "dispatch_all_literal": bool}.
    Names are bare (unqualified) so _build_per_function can merge them by last
    component. Collision between same-named methods in different classes is
    accepted (same limitation as the Python path — see ir_python._build_per_function).
    """
    module_tables = _js_collect_module_tables(root)
    results: list = []

    def _visit(node, prefix: str) -> None:
        if node.type in _FUNCTION_NODES:
            name = _function_name(node)
            qname = f"{prefix}.{name}" if prefix else name
            size, all_lit = _js_scan_dispatch_in_func(node, module_tables)
            results.append({
                "name": name,  # bare name for _build_per_function merge
                "dispatch_table_size": size,
                "dispatch_all_literal": all_lit,
            })
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
    return results


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


def _count_non_trivial_binops(root) -> int:
    """Count binary_expression nodes where at least one operand is not a literal.

    Mirrors ast_guard.analyzer.count_non_trivial_binops for Python: a binop is
    trivial only when both operands are JS literals.  Logical operators (&&, ||,
    ??) are excluded — they are already captured by McCabe and are control-flow,
    not arithmetic computation signals.
    """
    count = 0
    for node in _walk(root):
        if node.type != "binary_expression":
            continue
        # Identify the operator (unnamed child between the two operands).
        op = next((c.type for c in node.children if not c.is_named), None)
        if op in _LOGICAL_OPS:
            continue
        named = [c for c in node.children if c.is_named]
        if any(not _is_js_literal(c) for c in named):
            count += 1
    return count


def _build_dangerous_call_events(call_list: list[str], root) -> list[DangerousCallEvent]:
    """Build DangerousCallEvent entries for calls in the JS dangerous registry.

    Scans the tree once to assign line numbers. Only the first occurrence of
    each resolved call name is emitted — deduplication mirrors the Python path.
    """
    dangerous_names: set[str] = {
        c for c in call_list
        if c in DANGEROUS_CALLS or c.split(".")[-1] in DANGEROUS_CALLS
    }
    if not dangerous_names:
        return []

    events: list[DangerousCallEvent] = []
    seen: set[str] = set()

    for node in _walk(root):
        if node.type not in ("call_expression", "new_expression"):
            continue
        func_field = "function" if node.type == "call_expression" else "constructor"
        func_node = node.child_by_field_name(func_field)
        name = _resolve_callee(func_node)
        if name is None:
            continue
        bare = name.split(".")[-1]
        if name not in dangerous_names and bare not in DANGEROUS_CALLS:
            continue
        if name in seen:
            continue
        seen.add(name)
        events.append(DangerousCallEvent(
            pattern_id=f"js_dangerous_call:{bare}",
            call_name=name,
            severity="CRITICAL",
            line=node.start_point[0] + 1,
        ))
    return events


def extract_metrics(code: str) -> dict:
    """
    Parse JavaScript source and return ast-guard's standard metric dictionary.
    Includes the JS-specific ``dangerous_calls``, ``dangerous_imports``, and
    pre-built ``dangerous_call_events`` (list[DangerousCallEvent]) for the IR.
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
    dispatch_analysis = _collect_dispatch_analysis(root)
    non_trivial_binop_count = _count_non_trivial_binops(root)

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
        "dispatch_analysis": dispatch_analysis,
        "language": "javascript",
    }
