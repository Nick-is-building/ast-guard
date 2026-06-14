"""
Bash language adapter (v1.4, Phase 2).

Parses Bash scripts via tree-sitter-bash and produces the same metric dict
that ``ast_guard.analyzer.extract_metrics`` returns for Python, so checks.py
can operate on Bash without any language-specific changes.

Keys that have no Bash analogue (``comprehension_count``,
``functional_call_count``, ``max_set_literal_size``, ``guard_clause_count``,
``enumeration_analysis``) are filled with neutral defaults (0 or []).

Requires the optional ``ast-guard[multilang]`` extras.
"""

from __future__ import annotations

# Dangerous Bash command names. Surfaced as both a constant and an explicit
# ``dangerous_calls`` field in the metrics dict so downstream tooling can flag
# them without re-implementing the list.
DANGEROUS_CALLS = frozenset({
    "curl", "wget", "eval", "exec",
    "rm", "chmod", "chown",
    "dd", "mkfs",
    "nc", "ncat",
    "sudo", "pkill", "kill", "nohup",
})

# Commands that source another file -- treated as "imports" for Check 4.
_SOURCE_COMMANDS = frozenset({"source", "."})

# Tree-sitter node types that add a cyclomatic-complexity branch.
_BRANCH_NODES = frozenset({
    "if_statement", "elif_clause",
    "for_statement", "while_statement", "c_style_for_statement",
    "case_item",
})

# Loop node types (used for both loop_depth and complexity).
_LOOP_NODES = frozenset({"for_statement", "while_statement", "c_style_for_statement"})

# Literal node types.
_LITERAL_NODES = frozenset({"string", "raw_string", "ansi_c_string", "number"})


def _import_tree_sitter():
    """Lazy-import tree-sitter so core ast-guard stays zero-dep."""
    try:
        import tree_sitter
        import tree_sitter_bash
    except ImportError as exc:  # pragma: no cover - exercised only without extras
        raise ImportError(
            "Bash analysis requires the multilang extras: "
            "`pip install ast-guard[multilang]`"
        ) from exc
    return tree_sitter, tree_sitter_bash


_LANGUAGE = None
_PARSER = None


def _get_parser():
    """Lazily build the singleton tree-sitter parser bound to Bash."""
    global _LANGUAGE, _PARSER
    if _PARSER is None:
        ts, tsbash = _import_tree_sitter()
        _LANGUAGE = ts.Language(tsbash.language())
        _PARSER = ts.Parser(_LANGUAGE)
    return _PARSER


def _node_text(node) -> str:
    """Decode a tree-sitter node's UTF-8 text, replacing bad bytes."""
    return node.text.decode("utf-8", errors="replace")


def _command_name(cmd_node) -> str | None:
    """Return the command name for a ``command`` node, or None if missing."""
    name_node = cmd_node.child_by_field_name("name")
    if name_node is None:
        # Older grammar versions expose the command_name as the first
        # ``command_name`` child rather than via a named field.
        for c in cmd_node.children:
            if c.type == "command_name":
                name_node = c
                break
    if name_node is None:
        return None
    text = _node_text(name_node).strip()
    return text or None


def _resolve_string_argument(node) -> str | None:
    """For a node that may be a string/word, return its literal text content."""
    if node is None:
        return None
    if node.type == "word":
        return _node_text(node)
    if node.type in ("string", "raw_string"):
        # Strip surrounding quotes.
        text = _node_text(node)
        if len(text) >= 2 and text[0] in ("'", '"') and text[-1] == text[0]:
            return text[1:-1]
        return text
    return None


def _is_loop(node) -> bool:
    return node.type in _LOOP_NODES


def _walk(node):
    """Yield every node in pre-order without descending into nested functions."""
    yield node
    for child in node.children:
        yield from _walk(child)


def _walk_skip_funcs(node, skip_root=True):
    """Pre-order walk that does NOT descend into function_definition bodies.

    ``skip_root=False`` lets you start at a function body and still skip any
    nested function definitions inside it.
    """
    if not skip_root and node.type == "function_definition":
        return
    yield node
    for child in node.children:
        if child.type == "function_definition":
            continue
        yield from _walk_skip_funcs(child, skip_root=False)


def _loop_depth(root) -> int:
    """Maximum nesting depth of for/while loops below ``root``."""
    max_depth = 0

    def visit(node, depth):
        nonlocal max_depth
        cur = depth + 1 if _is_loop(node) else depth
        if cur > max_depth:
            max_depth = cur
        for child in node.children:
            if child.type == "function_definition":
                continue
            visit(child, cur)

    visit(root, 0)
    return max_depth


def _calculate_complexity(root) -> int:
    """McCabe complexity for a function body or the whole module."""
    complexity = 1
    for node in _walk_skip_funcs(root, skip_root=True):
        if node.type in _BRANCH_NODES:
            complexity += 1
        elif node.type == "list":
            # `&&` / `||` chains add one decision per operator.
            for child in node.children:
                if child.type in ("&&", "||"):
                    complexity += 1
    return complexity


def _collect_function_complexities(root) -> dict[str, int]:
    """Per-function McCabe complexity, keyed by qualified function name."""
    complexities: dict[str, int] = {}

    def visit(node, prefix: str):
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for c in node.children:
                    if c.type == "word":
                        name_node = c
                        break
            name = _node_text(name_node) if name_node is not None else "<anon>"
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
        else:
            child_prefix = prefix
        for child in node.children:
            visit(child, child_prefix)

    visit(root, "")
    return complexities


_EXPANSION_TYPES = frozenset({
    "simple_expansion", "expansion", "command_substitution",
    "process_substitution", "arithmetic_expansion",
})


def _is_bare_literal(node) -> bool:
    """Return True if ``node`` is a bash token with no variable expansions."""
    if node.type == "raw_string":
        return True
    if node.type in ("word", "string"):
        return not any(c.type in _EXPANSION_TYPES for c in node.children)
    return False


def _case_item_is_literal(case_item_node) -> bool:
    """Return True if a case_item uses a literal pattern rather than a wildcard."""
    for c in case_item_node.children:
        if not c.is_named:
            continue
        # extglob_pattern covers *, ?, [...] glob wildcards.
        if c.type == "extglob_pattern":
            return False
        return _is_bare_literal(c)
    return False


def _if_condition_has_literal(if_or_elif_node) -> bool:
    """Return True if the condition of an if/elif compares against a literal value.

    Handles both POSIX single-bracket ``[ "$x" = "y" ]`` (operator ``=``) and
    extended double-bracket ``[[ $x == "y" ]]`` (operator ``==``) forms, plus
    inequality variants (``!=``).  Both forms are parsed as ``test_command``
    with a ``binary_expression`` child in tree-sitter-bash.
    """
    for c in if_or_elif_node.children:
        if c.type != "test_command":
            continue
        for tc_child in c.children:
            if tc_child.type != "binary_expression":
                continue
            ops = {ch.type for ch in tc_child.children}
            # "=" is the POSIX single-bracket equality operator ([ "$x" = "y" ]).
            # "==" is the extended double-bracket form ([[ $x == "y" ]]).
            if "==" not in ops and "!=" not in ops and "=" not in ops:
                continue
            named = [ch for ch in tc_child.children if ch.is_named]
            if any(_is_bare_literal(n) for n in named):
                return True
    return False


def _collect_enumeration_analysis(root) -> list:
    """
    Per-function enumeration pattern statistics for Check 5.

    For each function returns:
        {"name": str, "total_ifs": int, "enumeration_ifs": int, "loop_count": int}

    total_ifs    — if_statement + elif_clause + case_item nodes in the function body
    enumeration_ifs — subset that uses a literal constant in the branch condition
    loop_count   — for/while loop nodes in the function body

    Known limitation: glob patterns (``case $x in [0-9]*)``) are counted as
    non-enumeration because the first case_item child is an extglob_pattern.
    Only bare word/string literals are detected as enumeration branches.
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
            elif t == "elif_clause":
                total_ifs += 1
                if _if_condition_has_literal(node):
                    enum_ifs += 1
            elif t == "case_item":
                total_ifs += 1
                if _case_item_is_literal(node):
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
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for c in node.children:
                    if c.type == "word":
                        name_node = c
                        break
            name = _node_text(name_node) if name_node is not None else "<anon>"
            qname = f"{prefix}.{name}" if prefix else name
            _analyze(node, qname)
            body = node.child_by_field_name("body")
            if body is not None:
                for c in body.children:
                    _visit(c, qname)
        else:
            for c in node.children:
                _visit(c, prefix)

    _visit(root, "")
    return result


def _extract_calls_and_imports(root):
    """Walk the tree once to collect command/function calls plus sourced files."""
    calls: list[str] = []
    imports: set[str] = set()

    for node in _walk(root):
        if node.type != "command":
            continue
        name = _command_name(node)
        if not name:
            continue
        if name in _SOURCE_COMMANDS:
            # First non-name child word/string is the file being sourced.
            args = [c for c in node.children if c.type in ("word", "string", "raw_string")]
            # Drop the command_name word itself if it appears in this list.
            target = None
            for arg in args:
                txt = _resolve_string_argument(arg)
                if txt and txt != name:
                    target = txt
                    break
            if target:
                imports.add(target)
            else:
                imports.add(name)
            calls.append(name)
        else:
            calls.append(name)
    return calls, sorted(imports)


def _count_literals_and_long_strings(root):
    """Return (literal_count, long_string_count) for the module."""
    literal_count = 0
    long_string_count = 0
    for node in _walk(root):
        if node.type in _LITERAL_NODES:
            literal_count += 1
            if node.type in ("string", "raw_string"):
                text = _node_text(node)
                # Drop surrounding quotes when measuring length.
                if len(text) >= 2 and text[0] in ("'", '"'):
                    text = text[1:-1]
                if len(text) > 200:
                    long_string_count += 1
    return literal_count, long_string_count


def _count_top_level_ifs(root) -> int:
    """Count if_statement + elif_clause nodes anywhere in the script."""
    n = 0
    for node in _walk(root):
        if node.type == "if_statement" or node.type == "elif_clause":
            n += 1
    return n


def extract_metrics(code: str) -> dict:
    """
    Parse Bash source and return ast-guard's standard metric dictionary.

    Keys with no Bash analogue (e.g. ``comprehension_count``) are filled with
    neutral defaults so checks.py can consume the dict directly.
    """
    parser = _get_parser()
    src = code.encode("utf-8")
    tree = parser.parse(src)
    root = tree.root_node

    if_count = _count_top_level_ifs(root)
    loop_depth = _loop_depth(root)
    mccabe_complexity = _calculate_complexity(root)
    literal_count, long_string_count = _count_literals_and_long_strings(root)
    call_list, import_list = _extract_calls_and_imports(root)
    function_complexities = _collect_function_complexities(root)
    enumeration_analysis = _collect_enumeration_analysis(root)
    dangerous_calls = sorted({c for c in call_list if c in DANGEROUS_CALLS})

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
        "non_trivial_binop_count": 0,
        "language": "bash",
    }
