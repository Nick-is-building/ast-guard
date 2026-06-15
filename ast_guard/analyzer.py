import ast

def is_docstring(node):
    """
    Helper to check if an AST statement node is a docstring.
    """
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
        return True
    return False

def find_docstring_node_ids(tree):
    """
    Finds and returns the object IDs of all docstring nodes (module, function, class)
    in the given AST to prevent them from being counted as normal/long strings.
    """
    docstring_ids = set()
    
    def check_body(body):
        if body and isinstance(body[0], ast.Expr):
            expr = body[0]
            if isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str):
                docstring_ids.add(id(expr.value))
                
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            check_body(node.body)
            
    return docstring_ids

def find_guard_clauses(func_node):
    """
    Identifies guard clauses directly on the top-level body of a function node.
    Returns a set of guard clause If node IDs.
    """
    guards = set()
    body = func_node.body
    
    # If the first statement is a docstring, ignore it for positioning checks
    if body and is_docstring(body[0]):
        body = body[1:]
        
    # Check the top-level statements at index 0, 1, or 2 of the remaining body
    for i in range(min(3, len(body))):
        stmt = body[i]
        if isinstance(stmt, ast.If):
            # Must have no orelse (else/elif)
            if not stmt.orelse:
                # Must end with Return or Raise in its body
                if stmt.body:
                    last_stmt = stmt.body[-1]
                    if isinstance(last_stmt, (ast.Return, ast.Raise)):
                        guards.add(id(stmt))
    return guards

def count_ifs(tree):
    """
    Counts normal If nodes, excluding identified guard clauses in any function.
    Returns a tuple: (if_count, guard_clause_count).
    """
    # 1. Find all function nodes
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(node)
            
    # 2. Identify all guard clauses
    all_guard_ids = set()
    for func in funcs:
        all_guard_ids.update(find_guard_clauses(func))
        
    # 3. Count all If nodes in AST that are not guard clauses
    if_count = 0
    guard_clause_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if id(node) in all_guard_ids:
                guard_clause_count += 1
            else:
                if_count += 1
                
    return if_count, guard_clause_count

def get_node_loop_depth(root_node):
    """
    Calculates the maximum loop nesting depth inside root_node, skipping nested functions/classes.
    """
    def visit(node, current_depth):
        if node is not root_node and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return 0
            
        if isinstance(node, (ast.For, ast.While)):
            new_depth = current_depth + 1
            max_depth = new_depth
            for child in ast.iter_child_nodes(node):
                max_depth = max(max_depth, visit(child, new_depth))
            return max_depth
        else:
            max_depth = current_depth
            for child in ast.iter_child_nodes(node):
                max_depth = max(max_depth, visit(child, current_depth))
            return max_depth
            
    return visit(root_node, 0)

def calculate_node_complexity(root_node):
    """
    Calculates McCabe Cyclomatic Complexity for a single function or module node,
    skipping nested functions/classes.
    """
    complexity = 1
    queue = [root_node]
    while queue:
        node = queue.pop(0)
        
        # Skip nested functions/classes
        if node is not root_node and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
            
        # Add to complexity for control flow nodes
        if isinstance(node, (ast.If, ast.IfExp, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.Assert)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            # len(node.values) - 1 is the number of 'and' / 'or' operators
            complexity += len(node.values) - 1
        elif hasattr(ast, 'match_case') and isinstance(node, ast.match_case):
            complexity += 1
            
        for child in ast.iter_child_nodes(node):
            queue.append(child)
            
    return complexity

def count_literals(tree, docstring_ids=None):
    """
    Counts literal values. Includes all ast.Constant nodes, and dictionary keys
    that are not ast.Constant nodes (to prevent double-counting).
    """
    if docstring_ids is None:
        docstring_ids = set()
    literal_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if id(node) not in docstring_ids:
                literal_count += 1
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None and not isinstance(key, ast.Constant):
                    literal_count += 1
    return literal_count

def count_long_strings(tree, docstring_ids):
    """
    Counts string constants longer than 200 characters, excluding those identified as docstrings.
    """
    long_string_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstring_ids:
                if len(node.value) > 200:
                    long_string_count += 1
    return long_string_count

def extract_imports(tree):
    """
    Extracts imported modules and names as flat strings.
    For `import os` -> 'os'
    For `from os import path` -> 'os', 'os.path'
    """
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module
            if module:
                imports.add(module)
                for alias in node.names:
                    imports.add(f"{module}.{alias.name}")
            else:
                for alias in node.names:
                    imports.add(alias.name)
    return sorted(list(imports))

def resolve_call_name(func_node):
    """
    Recursively resolves call names to flat string representation.
    e.g., os.path.join -> 'os.path.join'
    Returns None when the base is unresolvable (e.g. a Call or Subscript),
    avoiding false matches where any .eval() or .open() collides with blocked names.
    """
    if isinstance(func_node, ast.Name):
        return func_node.id
    elif isinstance(func_node, ast.Attribute):
        base = resolve_call_name(func_node.value)
        if base:
            return f"{base}.{func_node.attr}"
        return None
    return None

def resolve_constant_string(node):
    """
    Recursively resolves string concatenation via ast.BinOp(ast.Add) to a
    constant string value. Handles nested concatenation like 'ev' + 'al'.
    Returns the resolved string, or None if the expression is not a constant string.
    
    Added in v1.2 for constant folding detection in obfuscation checks.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = resolve_constant_string(node.left)
        right = resolve_constant_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None

def extract_calls(tree):
    """
    Extracts all resolved call names in the AST as a flat list.
    """
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = resolve_call_name(node.func)
            if name:
                calls.append(name)
    return calls

def count_comprehensions(tree):
    """
    Counts comprehensions (list, set, dict, or generator expressions).
    """
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            count += 1
    return count

def count_functional_calls(calls):
    """
    Counts calls to functional built-ins and standard patterns:
    map, filter, reduce, sorted, min, max, sum.
    """
    functional_names = {"map", "filter", "reduce", "functools.reduce", "sorted", "min", "max", "sum"}
    count = 0
    for call in calls:
        if call in functional_names:
            count += 1
    return count

def count_set_literals(tree):
    """
    Counts the maximum number of elements in any set literal (ast.Set) in the tree.
    Used by the allowlist to block Data Structure Swap overrides when
    a suspiciously large set literal is present (e.g., precomputed prime lookup).

    Added in v1.2.
    """
    max_size = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Set):
            max_size = max(max_size, len(node.elts))
    return max_size

def count_non_trivial_binops(tree):
    """Counts BinOp nodes where at least one operand is not a constant.

    A binop is trivial only when both operands are literals (e.g. 1 + 2).
    Non-trivial binops indicate arithmetic on variable data — a strong signal
    that the code is genuinely computing rather than returning hardcoded results.
    Used by the algorithmic-rewrite suppression rule in scan().
    """
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp):
            if not (isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant)):
                count += 1
    return count


def _all_literal_dict(dict_node: ast.Dict) -> bool:
    """True when every key and value in dict_node is an ast.Constant (no **unpacking)."""
    for k, v in zip(dict_node.keys, dict_node.values):
        if k is None:  # **unpacking placeholder
            return False
        if not isinstance(k, ast.Constant):
            return False
        if not isinstance(v, ast.Constant):
            return False
    return True


def _func_param_names(func_node) -> frozenset:
    """Flat set of all formal parameter names for a function node."""
    names = set()
    args = func_node.args
    for a in args.args + args.posonlyargs + args.kwonlyargs:
        names.add(a.arg)
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return frozenset(names)


def _is_param_key(key_node, params: frozenset) -> bool:
    """True when key_node is directly a function parameter name (not a derived expression)."""
    return isinstance(key_node, ast.Name) and key_node.id in params


def _check_dispatch_return(ret, params, local_dicts, module_dicts):
    """Check whether ``ret`` is a dict-dispatch lookup keyed by a parameter.

    Detects:
      {k: v, ...}[param]          -- inline dict subscript
      TABLE[param]                -- name subscript, local or module scope
      TABLE.get(param)            -- .get() form, local or module scope
      TABLE.get(param, default)   -- .get() with default

    Returns (table_size, all_literal) or (0, False) when the pattern is absent.
    """
    # Subscript form: expr[param]
    if isinstance(ret, ast.Subscript):
        if not _is_param_key(ret.slice, params):
            return 0, False
        src = ret.value
        if isinstance(src, ast.Dict):
            return len(src.keys), _all_literal_dict(src)
        if isinstance(src, ast.Name):
            d = local_dicts.get(src.id) or module_dicts.get(src.id)
            if d is not None:
                return len(d.keys), _all_literal_dict(d)

    # .get() form: TABLE.get(param [, default])
    if (isinstance(ret, ast.Call)
            and isinstance(ret.func, ast.Attribute)
            and ret.func.attr == "get"
            and len(ret.args) >= 1
            and _is_param_key(ret.args[0], params)):
        src = ret.func.value
        if isinstance(src, ast.Name):
            d = local_dicts.get(src.id) or module_dicts.get(src.id)
            if d is not None:
                return len(d.keys), _all_literal_dict(d)

    return 0, False


def _scan_dispatch_in_func(func_node, module_dicts):
    """Scan one function for the largest dict-dispatch-return pattern.

    Uses a BFS that does not descend into nested function/class bodies so
    each function's metrics reflect its own scope only.
    """
    params = _func_param_names(func_node)
    if not params:
        return 0, False

    local_dicts: dict = {}
    returns: list = []

    queue = list(ast.iter_child_nodes(func_node))
    while queue:
        node = queue.pop(0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and isinstance(node.value, ast.Dict):
                    local_dicts[t.id] = node.value
        if isinstance(node, ast.Return) and node.value is not None:
            returns.append(node.value)
        for c in ast.iter_child_nodes(node):
            queue.append(c)

    max_size = 0
    all_lit = False
    for ret in returns:
        sz, al = _check_dispatch_return(ret, params, local_dicts, module_dicts)
        if sz > max_size:
            max_size = sz
            all_lit = al
    return max_size, all_lit


def analyze_dispatch_tables(tree) -> list:
    """Per-function dict-dispatch memorisation detection.

    For each FunctionDef / AsyncFunctionDef, returns a dict:
        {"name": str, "dispatch_table_size": int, "dispatch_all_literal": bool}

    dispatch_table_size > 0 means the function has a dominant return of the
    form ``return TABLE[param]`` or ``return TABLE.get(param)`` where TABLE is
    a constant dict (all keys and values are ast.Constant) and param is a
    function parameter.  The field records the number of entries in that dict.

    dispatch_all_literal is True only when ALL keys and values are ast.Constant.
    A table with computed values (e.g. values that are expressions) sets this
    False so runtime caches are not flagged.

    Module-level dict assignments are collected as a fallback for the common
    pattern ``_ANSWERS = {1: 42, ...}`` followed by ``return _ANSWERS[n]``.
    """
    module_dicts: dict = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and isinstance(node.value, ast.Dict):
                    module_dicts[t.id] = node.value

    results = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            size, all_lit = _scan_dispatch_in_func(node, module_dicts)
            results.append({
                "name": node.name,
                "dispatch_table_size": size,
                "dispatch_all_literal": all_lit,
            })
    return results


def count_dict_literals(tree):
    """
    Returns the maximum number of keys in any dict literal (ast.Dict) in the tree.
    Used by the allowlist to block Data Structure Swap overrides when a
    suspiciously large dict literal is present (e.g., a precomputed lookup table).

    Added in v2.0.1 as the dict-literal parallel to count_set_literals.
    """
    max_size = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            max_size = max(max_size, len(node.keys))
    return max_size

def count_enumeration_pattern(tree):
    """
    Per-function analysis of the "extensional enumeration" pattern (Check 5).

    For each FunctionDef / AsyncFunctionDef in the tree, counts:
      - enumeration_ifs: ast.If nodes whose test is an ast.Compare with at
        least one ast.Eq against an ast.Constant AND whose body has at most
        2 statements. ast.match_case nodes whose body has at most 2 statements
        also count.
      - total_ifs: all ast.If nodes in the function (excluding guard clauses
        as identified by find_guard_clauses) plus all ast.match_case nodes.
      - loop_count: number of ast.For and ast.While nodes in the function.

    Traversal skips nested functions and classes so each function's metrics
    reflect only its own control flow.

    Returns a list of dicts: [{"name", "enumeration_ifs", "total_ifs", "loop_count"}, ...].

    Added in v1.3 to detect a Python analogue of extensional enumeration. The
    concept is from Helff et al. (arXiv:2604.15149), who studied it in
    inductive logic-reasoning tasks (Prolog-style rule induction); the
    `if`/`elif` and `match`/`case` pattern measured here is ast-guard's own
    operationalization of that idea.
    """
    results = []

    def _is_enumeration_if(if_node):
        if len(if_node.body) > 2:
            return False
        if not isinstance(if_node.test, ast.Compare):
            return False
        # At least one Eq comparator that is a Constant (handles both
        # `n == 1` and `1 == n` chained forms).
        for op, comparator in zip(if_node.test.ops, if_node.test.comparators):
            if isinstance(op, ast.Eq):
                if isinstance(comparator, ast.Constant):
                    return True
                if isinstance(if_node.test.left, ast.Constant):
                    return True
        return False

    def _is_literal_match_pattern(pat) -> bool:
        """True when a match_case pattern is a constant literal (not a wildcard, capture, or guard)."""
        if isinstance(pat, ast.MatchValue):
            return isinstance(pat.value, ast.Constant)
        if isinstance(pat, ast.MatchSingleton):
            # case True: / case False: / case None:
            return True
        if isinstance(pat, ast.MatchOr):
            return all(_is_literal_match_pattern(p) for p in pat.patterns)
        return False

    def _is_enumeration_match_case(case_node) -> bool:
        """True when a match_case is a literal-constant enumeration branch with trivial body.

        Guards (``case x if cond:``) and wildcards/captures (``case _:``, ``case x:``)
        are excluded — they are not input/output pair enumeration.
        """
        if case_node.guard is not None:
            return False
        if not _is_literal_match_pattern(case_node.pattern):
            return False
        return len(case_node.body) <= 2

    def _is_enum_ifexp(ifexp_node):
        if not isinstance(ifexp_node.test, ast.Compare):
            return False
        for op, comparator in zip(ifexp_node.test.ops, ifexp_node.test.comparators):
            if isinstance(op, ast.Eq):
                if isinstance(comparator, ast.Constant):
                    return True
                if isinstance(ifexp_node.test.left, ast.Constant):
                    return True
        return False

    def _analyze_function(func_node):
        guard_ids = find_guard_clauses(func_node)
        enumeration_ifs = 0
        total_ifs = 0
        loop_count = 0

        queue = list(ast.iter_child_nodes(func_node))
        while queue:
            node = queue.pop(0)

            # Don't descend into nested functions/classes — they have their
            # own entry in the results list.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue

            if isinstance(node, ast.If):
                if id(node) not in guard_ids:
                    total_ifs += 1
                    if _is_enumeration_if(node):
                        enumeration_ifs += 1
            elif isinstance(node, ast.IfExp):
                # Walk the IfExp chain iteratively to count each node exactly
                # once without double-counting via the recursive orelse path.
                current = node
                while isinstance(current, ast.IfExp):
                    total_ifs += 1
                    if _is_enum_ifexp(current):
                        enumeration_ifs += 1
                    queue.append(current.test)
                    queue.append(current.body)
                    current = current.orelse
                # current is now the final non-IfExp orelse value
                queue.append(current)
                continue  # skip the generic ast.iter_child_nodes below
            elif isinstance(node, (ast.For, ast.While)):
                loop_count += 1
            elif hasattr(ast, 'match_case') and isinstance(node, ast.match_case):
                total_ifs += 1
                if _is_enumeration_match_case(node):
                    enumeration_ifs += 1

            for child in ast.iter_child_nodes(node):
                queue.append(child)

        return {
            "name": func_node.name,
            "enumeration_ifs": enumeration_ifs,
            "total_ifs": total_ifs,
            "loop_count": loop_count,
        }

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            results.append(_analyze_function(node))

    return results


def collect_function_complexities(tree):
    """
    Walks the AST and returns a dict mapping qualified function names to their
    individual McCabe complexity scores. Qualified names use dotted paths to
    avoid collisions between functions of the same name in different scopes:

      - Module-level function `foo`           -> "foo"
      - Method `bar` of class `C`             -> "C.bar"
      - Method `bar` of nested class `C.Inner`-> "C.Inner.bar"
      - Nested function `inner` inside `foo`  -> "foo.inner"

    If two functions still collide on their qualified name (e.g. two functions
    with identical full paths defined in different branches of the same scope),
    later occurrences are disambiguated with a numeric suffix like "name#2".

    Each value is computed via `calculate_node_complexity`, which already skips
    nested functions/classes so each score reflects only that node's own
    control flow.
    """
    complexities = {}

    def visit(node, prefix):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qname = f"{prefix}.{node.name}" if prefix else node.name
            key = qname
            if key in complexities:
                # Disambiguate duplicate qualified names (rare; e.g. duplicate
                # defs in if/else branches at the same scope).
                i = 2
                while f"{qname}#{i}" in complexities:
                    i += 1
                key = f"{qname}#{i}"
            complexities[key] = calculate_node_complexity(node)
            child_prefix = qname
        elif isinstance(node, ast.ClassDef):
            child_prefix = f"{prefix}.{node.name}" if prefix else node.name
        else:
            child_prefix = prefix

        for child in ast.iter_child_nodes(node):
            visit(child, child_prefix)

    visit(tree, "")
    return complexities


def build_lineno_index(tree) -> dict:
    """Single-pass index over the AST.

    Returns a dict with two sub-dicts:
      "strings": {string_value: first_lineno}
      "calls":   {resolved_call_name: first_lineno}

    Use this instead of per-finding ast.walk() calls to avoid O(n*k)
    traversal cost when many findings reference the same tree.
    """
    string_locs: dict = {}
    call_locs: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if v not in string_locs:
                string_locs[v] = getattr(node, "lineno", None)
        elif isinstance(node, ast.Call):
            name = resolve_call_name(node.func)
            if name and name not in call_locs:
                call_locs[name] = getattr(node, "lineno", None)
    return {"strings": string_locs, "calls": call_locs}


def extract_metrics(code: str) -> dict:
    """
    Parses the given Python code string and extracts structured AST metrics.
    
    Returns a dictionary containing:
        - if_count (int)
        - guard_clause_count (int)
        - loop_depth (int)
        - mccabe_complexity (int)
        - literal_count (int)
        - long_string_count (int)
        - import_list (list[str])
        - call_list (list[str])
        - comprehension_count (int)
        - functional_call_count (int)
        - max_set_literal_size (int)  [v1.2]
        - function_complexities (dict[str, int])  [v1.3] per-function McCabe complexity
    """
    tree = ast.parse(code)
    
    # 1. Docstring detection
    docstring_ids = find_docstring_node_ids(tree)
    
    # 2. If count & Guard Clauses
    if_count, guard_clause_count = count_ifs(tree)
    
    # 3. Find all functions to calculate per-function metrics
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(node)
            
    # 4. McCabe Complexity & Loop Depth
    module_complexity = calculate_node_complexity(tree)
    module_loop_depth = get_node_loop_depth(tree)
    
    if funcs:
        mccabe_complexity = (module_complexity - 1) + sum(calculate_node_complexity(f) for f in funcs)
        loop_depth = max([module_loop_depth] + [get_node_loop_depth(f) for f in funcs])
    else:
        # Fallback to module level
        mccabe_complexity = module_complexity
        loop_depth = module_loop_depth
        
    # 5. Literal & Long String Counts
    literal_count = count_literals(tree, docstring_ids)
    long_string_count = count_long_strings(tree, docstring_ids)
    
    # 6. Imports & Calls
    import_list = extract_imports(tree)
    call_list = extract_calls(tree)
    
    # 7. Comprehensions & Functional calls
    comprehension_count = count_comprehensions(tree)
    functional_call_count = count_functional_calls(call_list)
    
    # 8. Set literal size (v1.2)
    max_set_literal_size = count_set_literals(tree)

    # 8b. Dict literal size (v2.0.1)
    max_dict_literal_size = count_dict_literals(tree)

    # 9. Per-function McCabe complexity, keyed by qualified name
    function_complexities = collect_function_complexities(tree)

    # 10. Per-function extensional enumeration analysis (v1.3, Check 5)
    enumeration_analysis = count_enumeration_pattern(tree)

    # 11. Non-trivial binary operations (v2.2.1, Check 1 suppression)
    non_trivial_binop_count = count_non_trivial_binops(tree)

    # 12. Per-function dict-dispatch memorisation analysis (Check 5 sub-rule)
    dispatch_analysis = analyze_dispatch_tables(tree)

    return {
        "if_count": if_count,
        "guard_clause_count": guard_clause_count,
        "loop_depth": loop_depth,
        "mccabe_complexity": mccabe_complexity,
        "literal_count": literal_count,
        "long_string_count": long_string_count,
        "import_list": import_list,
        "call_list": call_list,
        "comprehension_count": comprehension_count,
        "functional_call_count": functional_call_count,
        "max_set_literal_size": max_set_literal_size,
        "max_dict_literal_size": max_dict_literal_size,
        "function_complexities": function_complexities,
        "enumeration_analysis": enumeration_analysis,
        "non_trivial_binop_count": non_trivial_binop_count,
        "dispatch_analysis": dispatch_analysis,
    }
