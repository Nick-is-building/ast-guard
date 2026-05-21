import json

# ANSI Escape Sequences
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"
UNDERLINE = "\033[4m"

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
        
    print(f"\n{BOLD}{UNDERLINE}AST-GUARD v1.0 ANALYSIS REPORT{RESET}")
    print(f"{BOLD}Verdict:{RESET} {v_color}{BOLD}{verdict}{RESET}")
    print(f"{BOLD}Sensitivity Mode:{RESET} {mode.upper()}")
    print(f"{BOLD}Scan ID:{RESET} {scan_id}")
    print(f"{BOLD}Metrics Fingerprint:{RESET} {fingerprint}")
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
    # Build a SARIF-compatible flat structure or output the full scan result dict
    # To be extremely useful, we serialize the main dict.
    return json.dumps(result, indent=2, sort_keys=True)
