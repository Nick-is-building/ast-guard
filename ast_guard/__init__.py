__version__ = "1.3.0"
__all__ = ["scan", "feedback"]

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
    try:
        orig_tree = ast.parse(original_code)
        orig_metrics = extract_metrics(original_code)
    except Exception:
        orig_tree = ast.parse("")
        orig_metrics = extract_metrics("")
        
    try:
        gen_tree = ast.parse(generated_code)
        gen_metrics = extract_metrics(generated_code)
    except Exception as e:
        # If generated code fails to parse, return CRITICAL for syntax error
        check_results = {
            "check_1_hardcoding": {"status": "CLEAN", "findings": []},
            "check_2_complexity_collapse": {"status": "CLEAN", "findings": []},
            "check_3_forbidden_calls": {"status": "CRITICAL", "findings": [{"severity": "CRITICAL", "line": None, "explanation": f"Syntax Error: Generated code failed to parse: {e}"}]},
            "check_4_import_drift": {"status": "CLEAN", "findings": []},
            "check_5_extensional_enumeration": {"status": "CLEAN", "findings": []}
        }
        if telemetry_enabled:
            telemetry_record = log_scan(original_code, generated_code, orig_metrics, orig_metrics, check_results, [], effective_mode, "CRITICAL")
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

def feedback(scan_id: str, label: str, comment: str = "") -> bool:
    """Submits user feedback for a given scan."""
    return add_telemetry_feedback(scan_id, label, comment)
