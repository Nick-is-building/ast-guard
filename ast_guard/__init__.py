__version__ = "1.3.0"
__all__ = ["scan", "scan_multilang", "feedback"]

import ast
from ast_guard.analyzer import extract_metrics
from ast_guard.allowlist import detect_allowlist_transformations
from ast_guard.checks import (
    check_1_hardcoding,
    check_2_complexity_collapse,
    check_3_forbidden_calls,
    check_4_import_drift,
    check_5_extensional_enumeration,
)
from ast_guard.config import load_effective_config
from ast_guard.telemetry import log_scan, add_feedback as add_telemetry_feedback

def scan(original_code: str, generated_code: str, mode: str = None, config_override: dict = None, telemetry_enabled: bool = True) -> dict:
    """
    Scans the generated code compared to the original code.
    
    Args:
        original_code: The original/base Python code.
        generated_code: The LLM-generated/optimized Python code.
        mode: Sensitivity mode ('strict', 'standard', 'audit'). Defaults to 'strict' for API.
        config_override: Dict with configuration overrides.
        telemetry_enabled: Whether to log the scan to the local telemetry.
        
    Returns:
        A dictionary with the scan results, check details, transformations, and telemetry.
    """
    # 1. Load configuration
    config = load_effective_config(config_override or {})
    if mode:
        config["settings"]["mode"] = mode
    else:
        # Default mode for API is strict
        if "settings" not in config:
            config["settings"] = {}
        if "mode" not in config["settings"]:
            config["settings"]["mode"] = "strict"
            
    effective_mode = config["settings"]["mode"]
    
    # 2. Extract metrics & Parse trees
    # Only catch SyntaxError — other exceptions indicate real bugs in the
    # analyzer and must propagate so they can be fixed, not silently masked
    # as if the input were unparseable.
    try:
        orig_tree = ast.parse(original_code)
        orig_metrics = extract_metrics(original_code)
    except SyntaxError:
        orig_tree = ast.parse("")
        orig_metrics = extract_metrics("")

    try:
        gen_tree = ast.parse(generated_code)
        gen_metrics = extract_metrics(generated_code)
    except SyntaxError as e:
        # If generated code fails to parse, return CRITICAL for syntax error
        check_results = {
            "check_1_hardcoding": {"status": "CLEAN", "findings": []},
            "check_2_complexity_collapse": {"status": "CLEAN", "findings": []},
            "check_3_forbidden_calls": {"status": "CRITICAL", "findings": [{"severity": "CRITICAL", "line": None, "explanation": f"Syntax Error: Generated code failed to parse: {e}"}]},
            "check_4_import_drift": {"status": "CLEAN", "findings": []},
            "check_5_extensional_enumeration": {"status": "CLEAN", "findings": []}
        }
        if telemetry_enabled:
            # gen_metrics doesn't exist (parse failed), so pass an empty dict.
            # Logging orig_metrics twice would falsely claim gen == orig.
            telemetry_record = log_scan(original_code, generated_code, orig_metrics, {}, check_results, [], effective_mode, "CRITICAL")
        else:
            telemetry_record = {}
        return {
            "verdict": "CRITICAL",
            "mode": effective_mode,
            "checks": check_results,
            "transformations": [],
            "telemetry": telemetry_record
        }
        
    # 3. Detect Allowlist Transformations (v1.2: now receives config for set-literal-size check)
    transformations = detect_allowlist_transformations(original_code, generated_code, orig_metrics, gen_metrics, config)
    
    # 4. Run Checks
    check_1 = check_1_hardcoding(orig_metrics, gen_metrics, orig_tree, gen_tree, config)
    check_2 = check_2_complexity_collapse(orig_metrics, gen_metrics, config)
    check_3 = check_3_forbidden_calls(orig_metrics, gen_metrics, gen_tree, config)
    check_4 = check_4_import_drift(orig_metrics, gen_metrics, config)
    check_5 = check_5_extensional_enumeration(orig_metrics, gen_metrics, config)

    # 5. Handle Flag Override logic
    # Allowlist override for Check 2 is blocked when Check 1, Check 3, or
    # Check 5 also fire — those signal the "optimization" is actually a
    # reward-hack and not a legitimate transformation.
    if check_2["status"] == "WARNING":
        if len(transformations) > 0:
            if check_1["status"] != "CLEAN" or check_3["status"] != "CLEAN" or check_5["status"] != "CLEAN":
                pass
            else:
                check_2["status"] = "CLEAN"

    # 6. Combination Logic
    # Check 1 WARNING + Check 2 WARNING = CRITICAL
    # Check 5 WARNING + Check 2 WARNING = CRITICAL (enumeration + complexity collapse)
    # Check 5 WARNING + Check 1 WARNING = CRITICAL (enumeration + hardcoding,
    #   covers the case where Check 2 misses because the original was too small)
    kombi_triggered = False
    if check_1["status"] == "WARNING" and check_2["status"] == "WARNING":
        kombi_triggered = True
    if check_5["status"] == "WARNING" and check_2["status"] == "WARNING":
        kombi_triggered = True
    if check_5["status"] == "WARNING" and check_1["status"] == "WARNING":
        kombi_triggered = True

    # 7. Aggregate Check Statuses
    check_results = {
        "check_1_hardcoding": check_1,
        "check_2_complexity_collapse": check_2,
        "check_3_forbidden_calls": check_3,
        "check_4_import_drift": check_4,
        "check_5_extensional_enumeration": check_5
    }
    
    # Determine raw overall verdict
    if kombi_triggered:
        raw_verdict = "CRITICAL"
    elif check_3["status"] == "CRITICAL" or check_4["status"] == "CRITICAL":
        raw_verdict = "CRITICAL"
    elif any(c["status"] == "WARNING" for c in check_results.values()):
        raw_verdict = "WARNING"
    else:
        raw_verdict = "CLEAN"
        
    # 8. Apply sensitivity mode degradations
    if effective_mode == "standard":
        if check_1["status"] == "CRITICAL":
            check_1["status"] = "WARNING"
        if check_2["status"] == "CRITICAL":
            check_2["status"] = "WARNING"
        if check_5["status"] == "CRITICAL":
            check_5["status"] = "WARNING"
        if check_4["status"] == "CRITICAL":
            check_4["status"] = "WARNING"
            for f in check_4["findings"]:
                if f["severity"] == "CRITICAL":
                    f["severity"] = "WARNING"
                    
        # In standard mode, ONLY Check 3 CRITICAL remains CRITICAL
        if check_3["status"] == "CRITICAL":
            verdict = "CRITICAL"
        elif kombi_triggered or check_4["status"] == "WARNING" or any(c["status"] == "WARNING" for c in check_results.values()):
            verdict = "WARNING"
        else:
            verdict = "CLEAN"
    else:
        # strict or audit modes
        verdict = raw_verdict
        
    # 9. Log Scan Telemetry
    if telemetry_enabled:
        telemetry_record = log_scan(
            original_code,
            generated_code,
            orig_metrics,
            gen_metrics,
            check_results,
            transformations,
            effective_mode,
            verdict
        )
    else:
        telemetry_record = {}
    
    return {
        "verdict": verdict,
        "mode": effective_mode,
        "checks": check_results,
        "transformations": transformations,
        "telemetry": telemetry_record
    }

def scan_multilang(
    original_code: str,
    generated_code: str,
    language: str,
    mode: str = None,
    config_override: dict = None,
    telemetry_enabled: bool = True,
) -> dict:
    """
    Scan non-Python code using the multilang metric adapters.

    Uses extract_metrics_multilang() for bash and JavaScript so the same
    5-check pipeline can operate on those languages. Check 1 (long-string
    sub-rule) and Check 3 (alias obfuscation) are Python-AST-specific and are
    skipped; language-specific dangerous calls from the adapter's
    ``dangerous_calls`` field supplement Check 3 instead.

    Args:
        original_code: The original/baseline code.
        generated_code: The LLM-generated code.
        language: One of 'bash', 'javascript'.
        mode: 'strict', 'standard', or 'audit'.
        config_override: Optional config overrides dict.
        telemetry_enabled: Whether to log telemetry.

    Returns:
        Same result dict shape as scan().
    """
    from ast_guard.multilang import extract_metrics_multilang, SUPPORTED_LANGUAGES

    config = load_effective_config(config_override or {})
    if mode:
        config["settings"] = {"mode": mode}
    else:
        config.setdefault("settings", {}).setdefault("mode", "strict")
    effective_mode = config["settings"]["mode"]

    # Neutral empty metrics used as fallback when a side fails to parse.
    _EMPTY_METRICS: dict = {
        "if_count": 0, "guard_clause_count": 0, "loop_depth": 0,
        "mccabe_complexity": 1, "literal_count": 0, "long_string_count": 0,
        "import_list": [], "call_list": [], "comprehension_count": 0,
        "functional_call_count": 0, "max_set_literal_size": 0,
        "function_complexities": {}, "enumeration_analysis": [],
        "dangerous_calls": [],
    }

    try:
        orig_metrics = extract_metrics_multilang(original_code, language)
    except Exception:
        orig_metrics = dict(_EMPTY_METRICS)

    try:
        gen_metrics = extract_metrics_multilang(generated_code, language)
    except Exception:
        gen_metrics = dict(_EMPTY_METRICS)

    # Empty Python AST placeholder — Check 1 long-string sub-rule and
    # Check 3 alias-obfuscation sub-rule are Python-AST-only and won't fire.
    empty_tree = ast.parse("")

    check_1 = check_1_hardcoding(orig_metrics, gen_metrics, empty_tree, empty_tree, config)
    check_2 = check_2_complexity_collapse(orig_metrics, gen_metrics, config)
    check_3 = check_3_forbidden_calls(orig_metrics, gen_metrics, empty_tree, config)
    check_4 = check_4_import_drift(orig_metrics, gen_metrics, config)
    check_5 = check_5_extensional_enumeration(orig_metrics, gen_metrics, config)

    # Supplement Check 3 with language-specific dangerous calls that are
    # new in generated code (the standard blocklist covers eval/exec; the
    # adapter's dangerous_calls field adds curl, wget, rm, execSync, …).
    orig_dangerous = set(orig_metrics.get("dangerous_calls", []))
    gen_dangerous = set(gen_metrics.get("dangerous_calls", []))
    new_dangerous = gen_dangerous - orig_dangerous
    for call in sorted(new_dangerous):
        check_3["findings"].append({
            "severity": "CRITICAL",
            "line": None,
            "explanation": f"New dangerous {language} call '{call}' in generated code.",
        })
    if new_dangerous:
        check_3["status"] = "CRITICAL"

    # Combination logic (same as scan()).
    kombi_triggered = (
        (check_1["status"] == "WARNING" and check_2["status"] == "WARNING")
        or (check_5["status"] == "WARNING" and check_2["status"] == "WARNING")
        or (check_5["status"] == "WARNING" and check_1["status"] == "WARNING")
    )

    # Allowlist override for Check 2 is blocked if Check 1/3/5 also fire.
    if check_2["status"] == "WARNING":
        transformations = detect_allowlist_transformations(
            original_code, generated_code, orig_metrics, gen_metrics, config
        )
        if transformations:
            if check_1["status"] == "CLEAN" and check_3["status"] == "CLEAN" and check_5["status"] == "CLEAN":
                check_2["status"] = "CLEAN"
    else:
        transformations = []

    check_results = {
        "check_1_hardcoding": check_1,
        "check_2_complexity_collapse": check_2,
        "check_3_forbidden_calls": check_3,
        "check_4_import_drift": check_4,
        "check_5_extensional_enumeration": check_5,
    }

    if kombi_triggered:
        raw_verdict = "CRITICAL"
    elif check_3["status"] == "CRITICAL" or check_4["status"] == "CRITICAL":
        raw_verdict = "CRITICAL"
    elif any(c["status"] == "WARNING" for c in check_results.values()):
        raw_verdict = "WARNING"
    else:
        raw_verdict = "CLEAN"

    if effective_mode == "standard":
        for chk in (check_1, check_2, check_4, check_5):
            if chk["status"] == "CRITICAL":
                chk["status"] = "WARNING"
        verdict = "CRITICAL" if check_3["status"] == "CRITICAL" else (
            "WARNING" if (kombi_triggered or any(c["status"] == "WARNING" for c in check_results.values()))
            else "CLEAN"
        )
    else:
        verdict = raw_verdict

    telemetry_record: dict = {}
    if telemetry_enabled:
        telemetry_record = log_scan(
            original_code, generated_code,
            orig_metrics, gen_metrics,
            check_results, transformations,
            effective_mode, verdict,
        )

    return {
        "verdict": verdict,
        "mode": effective_mode,
        "checks": check_results,
        "transformations": transformations,
        "telemetry": telemetry_record,
    }


def feedback(scan_id: str, label: str, comment: str = "") -> bool:
    """Submits user feedback for a given scan."""
    return add_telemetry_feedback(scan_id, label, comment)
