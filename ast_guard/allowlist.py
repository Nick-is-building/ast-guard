import ast

ALLOWLIST_IMPORTS = {
    "functools", "itertools", "collections", "operator", "math", "bisect",
    "heapq", "array", "typing", "dataclasses", "enum", "decimal",
    "fractions", "statistics", "copy", "string", "re", "struct", "abc"
}

# v1.2: Maximum set literal size before Data Structure Swap override is blocked.
# A set literal with more than this many elements is suspicious (e.g., precomputed lookup).
DEFAULT_SET_LITERAL_MAX = 15

def count_loops(tree):
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While)):
            count += 1
    return count

def count_in_ops(tree):
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if isinstance(op, (ast.In, ast.NotIn)):
                    count += 1
    return count

def count_set_dict_calls(call_list):
    count = 0
    for call in call_list:
        if call in ("set", "dict"):
            count += 1
    return count

def detect_allowlist_transformations(orig_code: str, gen_code: str, orig_metrics: dict, gen_metrics: dict, config: dict = None) -> list:
    """
    Detects allowed optimization transformations.
    Returns a list of dicts: [{"category": str, "reason": str}]
    
    v1.2: Added set-literal-size check — Data Structure Swap is blocked
    when a set literal exceeds the configured maximum size, preventing
    precomputed lookup tables from being whitelisted.
    """
    transformations = []
    
    if config is None:
        config = {}
    
    try:
        orig_tree = ast.parse(orig_code)
        gen_tree = ast.parse(gen_code)
    except Exception:
        return transformations
        
    # 1. Loop to Comprehension
    orig_loops = count_loops(orig_tree)
    gen_loops = count_loops(gen_tree)
    orig_comps_val = orig_metrics.get("comprehension_count", 0)
    gen_comps_val = gen_metrics.get("comprehension_count", 0)
    
    if gen_loops < orig_loops and gen_comps_val > orig_comps_val:
        transformations.append({
            "category": "Loop to Comprehension",
            "reason": f"Loops decreased from {orig_loops} to {gen_loops} and comprehensions increased from {orig_comps_val} to {gen_comps_val}."
        })
        
    # 2. Functional Built-ins
    orig_func_calls = orig_metrics.get("functional_call_count", 0)
    gen_func_calls = gen_metrics.get("functional_call_count", 0)
    
    if gen_loops < orig_loops and gen_func_calls > orig_func_calls:
        transformations.append({
            "category": "Functional Built-ins",
            "reason": f"Loops decreased from {orig_loops} to {gen_loops} and functional calls increased from {orig_func_calls} to {gen_func_calls}."
        })
        
    # 3. Data Structure Swap
    #    v1.2: Blocked if generated code contains a set literal exceeding the max size threshold.
    set_literal_max = config.get("thresholds", {}).get("set_literal_max", DEFAULT_SET_LITERAL_MAX)
    gen_max_set_size = gen_metrics.get("max_set_literal_size", 0)
    
    orig_set_dict = count_set_dict_calls(orig_metrics.get("call_list", []))
    gen_set_dict = count_set_dict_calls(gen_metrics.get("call_list", []))
    orig_in_ops = count_in_ops(orig_tree)
    gen_in_ops = count_in_ops(gen_tree)
    
    if gen_set_dict > orig_set_dict or gen_in_ops > orig_in_ops:
        if gen_max_set_size > set_literal_max:
            # Set literal is too large — this looks like a precomputed lookup, not a swap
            pass
        else:
            transformations.append({
                "category": "Data Structure Swap",
                "reason": f"Efficient data structure instantiation increased (set/dict calls: {orig_set_dict}->{gen_set_dict}, 'in' operators: {orig_in_ops}->{gen_in_ops})."
            })
        
    # 4. Standard Library Optimization
    orig_imports = set(orig_metrics.get("import_list", []))
    gen_imports = set(gen_metrics.get("import_list", []))
    new_imports = gen_imports - orig_imports
    
    allowed_new_imports = []
    for imp in new_imports:
        root_mod = imp.split('.')[0]
        if root_mod in ALLOWLIST_IMPORTS:
            allowed_new_imports.append(imp)
            
    if allowed_new_imports:
        transformations.append({
            "category": "Standard Library Optimization",
            "reason": f"New allowed standard library imports added: {', '.join(allowed_new_imports)}."
        })
        
    return transformations
