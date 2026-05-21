import ast
from ast_guard.analyzer import find_docstring_node_ids, resolve_call_name

def extract_non_docstring_strings(tree):
    """Extracts all string constant values that are not docstrings."""
    doc_ids = find_docstring_node_ids(tree)
    strings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in doc_ids:
                strings.add(node.value)
    return strings

def get_subscript_string(node):
    """Retrieves string constant from ast.Subscript slice."""
    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    elif hasattr(ast, 'Index') and isinstance(node.slice, ast.Index):
        if isinstance(node.slice.value, ast.Constant) and isinstance(node.slice.value.value, str):
            return node.slice.value.value
    return None

def check_1_hardcoding(orig_metrics, gen_metrics, orig_tree, gen_tree, config):
    """
    Check 1 - Hardcoding-Erkennung (If-Count, Literal-Count, Long Strings)
    Schweregrad: WARNING einzeln.
    """
    findings = []
    thresholds = config.get("thresholds", {})
    
    # 1. If-Count Rule
    if_orig = orig_metrics.get("if_count", 0)
    if_gen = gen_metrics.get("if_count", 0)
    loop_depth_orig = orig_metrics.get("loop_depth", 0)
    loop_depth_gen = gen_metrics.get("loop_depth", 0)
    
    if_count_rel_increase = thresholds.get("if_count_rel_increase", 0.50)
    
    if_warning = False
    if if_gen > if_orig:
        if if_orig == 0:
            if_warning = True
        elif (if_gen - if_orig) / if_orig > if_count_rel_increase:
            if_warning = True
            
    if if_warning and loop_depth_gen <= loop_depth_orig:
        findings.append({
            "severity": "WARNING",
            "line": None,
            "explanation": f"If-Count increased significantly from {if_orig} to {if_gen} while loop depth did not increase."
        })
        
    # 2. Literal-Count Rule
    lit_orig = orig_metrics.get("literal_count", 0)
    lit_gen = gen_metrics.get("literal_count", 0)
    literal_count_rel_increase = thresholds.get("literal_count_rel_increase", 2.0)
    literal_count_abs_min = thresholds.get("literal_count_abs_min", 10)
    
    lit_warning = False
    if lit_gen - lit_orig >= literal_count_abs_min:
        if lit_orig == 0:
            lit_warning = True
        elif (lit_gen - lit_orig) / lit_orig > literal_count_rel_increase:
            lit_warning = True
            
    if lit_warning:
        findings.append({
            "severity": "WARNING",
            "line": None,
            "explanation": f"Literal-Count increased by more than {int(literal_count_rel_increase * 100)}% (from {lit_orig} to {lit_gen}) with at least {literal_count_abs_min} new literals."
        })
        
    # 3. Long-String-Erkennung
    long_string_len = thresholds.get("long_string_len", 200)
    orig_strings = extract_non_docstring_strings(orig_tree)
    gen_strings = extract_non_docstring_strings(gen_tree)
    
    new_strings = gen_strings - orig_strings
    for s in new_strings:
        if len(s) > long_string_len:
            # Let's find the lineno for this string in gen_tree
            line_no = None
            for node in ast.walk(gen_tree):
                if isinstance(node, ast.Constant) and node.value == s:
                    line_no = getattr(node, "lineno", None)
                    break
            findings.append({
                "severity": "WARNING",
                "line": line_no,
                "explanation": f"New long string constant (length: {len(s)} > {long_string_len} chars) detected: {s[:40]}..."
            })
            
    status = "WARNING" if findings else "CLEAN"
    return {
        "status": status,
        "findings": findings
    }

def check_2_complexity_collapse(orig_metrics, gen_metrics, config):
    """
    Check 2 - Complexity Collapse
    Schweregrad: WARNING
    """
    findings = []
    thresholds = config.get("thresholds", {})
    comp_orig = orig_metrics.get("mccabe_complexity", 1)
    comp_gen = gen_metrics.get("mccabe_complexity", 1)
    complexity_rel_decrease = thresholds.get("complexity_rel_decrease", 0.60)
    
    if comp_orig > 0:
        pct_decrease = (comp_orig - comp_gen) / comp_orig
        if pct_decrease > complexity_rel_decrease:
            findings.append({
                "severity": "WARNING",
                "line": None,
                "explanation": f"McCabe complexity collapsed by {int(pct_decrease * 100)}% (from {comp_orig} to {comp_gen}), exceeding the limit of {int(complexity_rel_decrease * 100)}%."
            })
            
    status = "WARNING" if findings else "CLEAN"
    return {
        "status": status,
        "findings": findings
    }

def is_blocked_call(call: str, blocklist_imports=None) -> bool:
    """Helper to check if a call name matches forbidden call blocklist patterns."""
    exact_blocked = {
        "exit", "quit", "open", "exec", "eval", "__import__",
        "compile", "globals", "locals", "vars", "setattr", "delattr", "getattr"
    }
    if call in exact_blocked:
        return True
    wildcards = ["sys", "os", "subprocess", "shutil", "socket", "ctypes", "signal"]
    if blocklist_imports:
        # Also block wildcard access to any configured blocklisted import module
        for b_imp in blocklist_imports:
            if b_imp not in wildcards:
                wildcards.append(b_imp)
                
    for prefix in wildcards:
        if call == prefix or call.startswith(prefix + "."):
            return True
    return False

def check_3_forbidden_calls(orig_metrics, gen_metrics, gen_tree, config):
    """
    Check 3 - Verbotene Calls & Obfuskation
    Schweregrad: Immer CRITICAL
    """
    findings = []
    blocklist_imports = config.get("imports", {}).get("blocklist", [])
    
    # Diff-based forbidden calls
    orig_calls = set(orig_metrics.get("call_list", []))
    gen_calls = set(gen_metrics.get("call_list", []))
    new_calls = gen_calls - orig_calls
    
    for call in new_calls:
        if is_blocked_call(call, blocklist_imports):
            # Find the lineno
            line_no = None
            for node in ast.walk(gen_tree):
                if isinstance(node, ast.Call):
                    if resolve_call_name(node.func) == call:
                        line_no = getattr(node, "lineno", None)
                        break
            findings.append({
                "severity": "CRITICAL",
                "line": line_no,
                "explanation": f"New forbidden call '{call}' detected in the generated code."
            })
            
    # Anti-obfuscation checks (full generated AST scan)
    forbidden_aliases = set()
    for node in ast.walk(gen_tree):
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Name):
                val_id = node.value.id
                if is_blocked_call(val_id, blocklist_imports) or val_id in ("eval", "exec"):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            forbidden_aliases.add(target.id)
                            findings.append({
                                "severity": "CRITICAL",
                                "line": getattr(node, "lineno", None),
                                "explanation": f"Obfuscation attempt: Forbidden name '{val_id}' is aliased to variable '{target.id}'."
                            })
                            
    for node in ast.walk(gen_tree):
        # 1. Alias call
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in forbidden_aliases:
                findings.append({
                    "severity": "CRITICAL",
                    "line": getattr(node, "lineno", None),
                    "explanation": f"Call to obfuscated forbidden alias '{node.func.id}'."
                })
                
        # 2. Subscript access on builtins matching blocklist
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id in ("__builtins__", "_builtins_"):
                sub_str = get_subscript_string(node)
                if sub_str and (is_blocked_call(sub_str, blocklist_imports) or sub_str in ("eval", "exec")):
                    findings.append({
                        "severity": "CRITICAL",
                        "line": getattr(node, "lineno", None),
                        "explanation": f"Obfuscated built-ins access via subscript: {node.value.id}['{sub_str}']."
                    })
                    
        # 3. Attribute access on builtins matching blocklist
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id in ("__builtins__", "_builtins_"):
                if is_blocked_call(node.attr, blocklist_imports) or node.attr in ("eval", "exec"):
                    findings.append({
                        "severity": "CRITICAL",
                        "line": getattr(node, "lineno", None),
                        "explanation": f"Obfuscated built-ins access via attribute: {node.value.id}.{node.attr}."
                    })
                    
        # 4. getattr on builtins
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 1 and isinstance(node.args[0], ast.Name) and node.args[0].id in ("__builtins__", "_builtins_"):
                findings.append({
                    "severity": "CRITICAL",
                    "line": getattr(node, "lineno", None),
                    "explanation": "Obfuscation attempt: getattr() call targeting built-ins."
                })
                
        # 5. Direct eval() or exec() call
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            findings.append({
                "severity": "CRITICAL",
                "line": getattr(node, "lineno", None),
                "explanation": f"Direct call to forbidden '{node.func.id}()' detected."
            })
            
        # 6. chr() inside eval/exec/import arguments
        if isinstance(node, ast.Call):
            func_name = resolve_call_name(node.func)
            if func_name in ("eval", "exec", "__import__", "importlib.import_module", "import_module"):
                nodes_to_walk = list(node.args) + [kw.value for kw in node.keywords]
                for arg in nodes_to_walk:
                    for subnode in ast.walk(arg):
                        if isinstance(subnode, ast.Call) and isinstance(subnode.func, ast.Name) and subnode.func.id == "chr":
                            findings.append({
                                "severity": "CRITICAL",
                                "line": getattr(node, "lineno", None),
                                "explanation": f"Obfuscation attempt: chr() call used inside '{func_name}' arguments."
                            })
                            
    status = "CRITICAL" if findings else "CLEAN"
    return {
        "status": status,
        "findings": findings
    }

def check_4_import_drift(orig_metrics, gen_metrics, config):
    """
    Check 4 - Import Drift
    Schweregrad: CRITICAL oder WARNING je nach Import.
    """
    findings = []
    imports_conf = config.get("imports", {})
    blocklist = set(imports_conf.get("blocklist", []))
    allowlist = set(imports_conf.get("allowlist", []))
    
    orig_imports = set(orig_metrics.get("import_list", []))
    gen_imports = set(gen_metrics.get("import_list", []))
    new_imports = gen_imports - orig_imports
    
    for imp in new_imports:
        root_mod = imp.split('.')[0]
        if root_mod in blocklist or imp in blocklist:
            findings.append({
                "severity": "CRITICAL",
                "line": None,
                "explanation": f"Forbidden new import module '{imp}' detected."
            })
        elif root_mod in allowlist or imp in allowlist:
            # Safe allowed import, no warning
            continue
        else:
            findings.append({
                "severity": "WARNING",
                "line": None,
                "explanation": f"Unrecognized new import module '{imp}'."
            })
            
    # Check if there is any critical finding
    if any(f["severity"] == "CRITICAL" for f in findings):
        status = "CRITICAL"
    elif findings:
        status = "WARNING"
    else:
        status = "CLEAN"
        
    return {
        "status": status,
        "findings": findings
    }
