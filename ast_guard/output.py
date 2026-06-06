import hashlib
import json
from ast_guard import __version__

# ANSI Escape Sequences
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"
UNDERLINE = "\033[4m"

# SARIF severity mapping
_SARIF_LEVEL_MAP = {
    "CRITICAL": "error",
    "WARNING": "warning",
    "CLEAN": "note"
}

# SARIF rule definitions for ast-guard checks
_SARIF_RULES = [
    {
        "id": "ast-guard/check-1-hardcoding",
        "name": "HardcodingDetection",
        "shortDescription": {"text": "Detects hardcoded outputs replacing algorithmic solutions"},
        "helpUri": "https://github.com/Nick-is-building/ast-guard#check-1--hardcoding-detection"
    },
    {
        "id": "ast-guard/check-2-complexity-collapse",
        "name": "ComplexityCollapse",
        "shortDescription": {"text": "Detects suspicious drops in cyclomatic complexity"},
        "helpUri": "https://github.com/Nick-is-building/ast-guard#check-2--complexity-collapse"
    },
    {
        "id": "ast-guard/check-3-forbidden-calls",
        "name": "ForbiddenCallsAndObfuscation",
        "shortDescription": {"text": "Detects forbidden system calls and obfuscation patterns"},
        "helpUri": "https://github.com/Nick-is-building/ast-guard#check-3--forbidden-calls--obfuscation"
    },
    {
        "id": "ast-guard/check-4-import-drift",
        "name": "ImportDrift",
        "shortDescription": {"text": "Detects new imports not present in the original code"},
        "helpUri": "https://github.com/Nick-is-building/ast-guard#check-4--import-drift"
    },
    {
        "id": "ast-guard/check-5-extensional-enumeration",
        "name": "ExtensionalEnumeration",
        "shortDescription": {"text": "Detects enumeration of constant input/output pairs replacing algorithmic logic"},
        "helpUri": "https://github.com/Nick-is-building/ast-guard#check-5--extensional-enumeration"
    },
    {
        "id": "ast-guard/check-6-behavioral",
        "name": "BehavioralRiskScoring",
        "shortDescription": {"text": "Detects behavioral reward-hacking patterns via additive risk scoring (standalone mode)"},
        "helpUri": "https://github.com/Nick-is-building/ast-guard#check-6--behavioral-risk-scoring"
    }
]

# Map check keys to SARIF rule IDs
_CHECK_KEY_TO_RULE = {
    "check_1_hardcoding": "ast-guard/check-1-hardcoding",
    "check_2_complexity_collapse": "ast-guard/check-2-complexity-collapse",
    "check_3_forbidden_calls": "ast-guard/check-3-forbidden-calls",
    "check_4_import_drift": "ast-guard/check-4-import-drift",
    "check_5_extensional_enumeration": "ast-guard/check-5-extensional-enumeration",
    "check_6_behavioral": "ast-guard/check-6-behavioral"
}


def print_ansi_report(result: dict) -> None:
    """Prints a beautiful, human-readable report with ANSI colors."""
    verdict = result["verdict"]
    mode = result["mode"]
    telemetry = result.get("telemetry", {})
    scan_id = telemetry.get("scan_id", "N/A")
    fingerprint = telemetry.get("metrics_fingerprint", "N/A")
    
    # Verdict color
    if verdict == "CRITICAL":
        v_color = RED
    elif verdict == "WARNING":
        v_color = YELLOW
    else:
        v_color = GREEN
        
    confidence = result.get("confidence", 0)

    print(f"\n{BOLD}{UNDERLINE}AST-GUARD v{__version__} ANALYSIS REPORT{RESET}")
    print(f"{BOLD}Verdict:{RESET} {v_color}{BOLD}{verdict}{RESET}")
    print(f"{BOLD}Confidence:{RESET} {confidence}/100")
    print(f"{BOLD}Sensitivity Mode:{RESET} {mode.upper()}")
    print(f"{BOLD}Scan ID:{RESET} {scan_id}")
    print(f"{BOLD}Metrics Fingerprint:{RESET} {fingerprint}")
    lang = result.get("language")
    if lang and lang != "python":
        via = result.get("language_detected_via", "")
        lang_score = result.get("language_detection_score")
        score_str = f", score: {lang_score}" if lang_score is not None else ""
        print(f"{BOLD}Language:{RESET} {lang} [{via}{score_str}]")
    print("-" * 60)
    
    print(f"\n{BOLD}CHECK DETAILS:{RESET}")
    checks = result.get("checks", {})
    for check_name, check_data in checks.items():
        status = check_data["status"]
        if status == "CRITICAL":
            c_color = RED
        elif status == "WARNING":
            c_color = YELLOW
        else:
            c_color = GREEN
            
        name_pretty = check_name.replace("_", " ").title()
        print(f"  {BOLD}{name_pretty}:{RESET} {c_color}{status}{RESET}")
        
        findings = check_data.get("findings", [])
        if findings:
            for f in findings:
                line_info = f"Line {f['line']}: " if f.get("line") is not None else ""
                sev = f["severity"]
                f_color = RED if sev == "CRITICAL" else YELLOW
                print(f"    - {f_color}[{sev}]{RESET} {line_info}{f['explanation']}")
                
    print("-" * 60)
    
    transformations = result.get("transformations", [])
    print(f"\n{BOLD}DETECTED LEGITIMATE OPTIMIZATIONS ({len(transformations)}):{RESET}")
    if transformations:
        for t in transformations:
            print(f"  {GREEN}✓ [{t['category']}] {t['reason']}{RESET}")
    else:
        print("  None detected or not applicable.")
        
    print("-" * 60)
    print(f"{BOLD}Telemetry & Privacy:{RESET}")
    print("  Anonymized metrics have been saved locally.")
    print(f"  Provide feedback: ast-guard feedback --id {scan_id} --label [correct/false-positive/false-negative]")
    print("-" * 60 + "\n")

def format_json_report(result: dict) -> str:
    """Returns the scan result formatted as a JSON string."""
    return json.dumps(result, indent=2, sort_keys=True)

def format_sarif_report(result: dict, original_file: str = "original.py", generated_file: str = "generated.py") -> str:
    """
    Formats scan results as SARIF v2.1.0 for GitHub Security Tab and CI/CD integration.

    The output follows the SARIF v2.1.0 specification (OASIS standard) and is compatible
    with GitHub's code scanning API (github/codeql-action/upload-sarif).

    Args:
        result: The scan result dictionary from ast_guard.scan().
        original_file: Path to the original file (for SARIF artifact reference).
        generated_file: Path to the generated file (findings are reported against this).

    Returns:
        A JSON string containing the SARIF report.

    Added in v1.2.
    """
    confidence = result.get("confidence", 0)
    results = []
    checks = result.get("checks", {})
    
    for check_key, check_data in checks.items():
        rule_id = _CHECK_KEY_TO_RULE.get(check_key, check_key)
        
        for finding in check_data.get("findings", []):
            # Stable fingerprint over ruleId + explanation only — line numbers
            # shift between commits, so excluding them lets SARIF consumers
            # (e.g. GitHub code scanning) deduplicate findings across runs.
            fingerprint_input = f"{rule_id}|{finding['explanation']}".encode("utf-8")
            fingerprint = hashlib.sha256(fingerprint_input).hexdigest()[:16]

            sarif_result = {
                "ruleId": rule_id,
                "level": _SARIF_LEVEL_MAP.get(finding["severity"], "warning"),
                "message": {
                    "text": finding["explanation"]
                },
                "partialFingerprints": {
                    "astGuardFingerprint/v1": fingerprint
                },
                "properties": {
                    "confidence": confidence
                },
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": generated_file
                        }
                    }
                }]
            }
            
            # Add line number if available
            if finding.get("line") is not None:
                sarif_result["locations"][0]["physicalLocation"]["region"] = {
                    "startLine": finding["line"]
                }
                
            results.append(sarif_result)
    
    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "ast-guard",
                    "version": __version__,
                    "informationUri": "https://github.com/Nick-is-building/ast-guard",
                    "rules": _SARIF_RULES
                }
            },
            "results": results,
            "properties": {
                k: result[k]
                for k in ("language", "language_detected_via", "language_detection_score")
                if k in result
            },
            "artifacts": [
                {"location": {"uri": original_file}},
                {"location": {"uri": generated_file}}
            ]
        }]
    }
    
    return json.dumps(sarif, indent=2)
