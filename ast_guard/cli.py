import argparse
import json
import sys
import os
from ast_guard import scan, feedback
from ast_guard.output import print_ansi_report, format_json_report, format_sarif_report
from ast_guard.telemetry import (
    export_telemetry,
    get_stats,
    get_detailed_stats,
    check_sharing_prompt,
    disable_sharing_prompt,
)

BOLD = "\033[1m"
RESET = "\033[0m"
UNDERLINE = "\033[4m"
DIM = "\033[2m"


def _fmt_num(value):
    """Format a numeric stat for the detailed report; None becomes 'n/a'."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _print_detailed_stats(detailed: dict) -> None:
    print(f"\n{BOLD}{UNDERLINE}AST-GUARD TELEMETRY — DETAILED STATS{RESET}")
    print(f"{BOLD}Total Scans:{RESET} {detailed['total_scans']}")

    print(f"\n{BOLD}{UNDERLINE}Metric Deltas (gen − orig){RESET}")
    deltas = detailed.get("metric_deltas", {}) or {}
    if not deltas or all(d.get("count", 0) == 0 for d in deltas.values()):
        print(f"  {DIM}No scans with comparable metrics yet.{RESET}")
    else:
        for metric, d in deltas.items():
            count = d.get("count", 0)
            if count == 0:
                print(f"  {BOLD}{metric}:{RESET} {DIM}no data{RESET}")
                continue
            print(
                f"  {BOLD}{metric}:{RESET} "
                f"count={count}, mean={_fmt_num(d['mean'])}, median={_fmt_num(d['median'])}, "
                f"min={_fmt_num(d['min'])}, max={_fmt_num(d['max'])}, stddev={_fmt_num(d['stddev'])}"
            )

    print(f"\n{BOLD}{UNDERLINE}Check Correlations{RESET}")
    correlations = detailed.get("check_correlations", {}) or {}
    labels = {
        "check_1_and_2_kombi": "Check 1 + Check 2 kombi (CRITICAL escalation)",
        "check_5_and_2_kombi": "Check 5 + Check 2 kombi (CRITICAL escalation)",
        "check_5_alone": "Check 5 fired alone (no other check)",
        "check_5_with_others": "Check 5 fired alongside other checks",
        "check_3_critical": "Check 3 CRITICAL (forbidden calls)",
        "check_4_critical": "Check 4 CRITICAL (forbidden imports)",
    }
    for key, label in labels.items():
        print(f"  {label}: {correlations.get(key, 0)}")

    print(f"\n{BOLD}{UNDERLINE}Verdicts by Mode{RESET}")
    verdicts_by_mode = detailed.get("verdicts_by_mode", {}) or {}
    any_recorded = False
    for mode, counts in verdicts_by_mode.items():
        total = sum(counts.values())
        if total == 0:
            continue
        any_recorded = True
        print(f"  {BOLD}{mode}:{RESET}")
        for verdict, c in counts.items():
            print(f"    {verdict}: {c}")
    if not any_recorded:
        print(f"  {DIM}No scans recorded yet.{RESET}")

    print(f"\n{BOLD}{UNDERLINE}Transformations{RESET}")
    transformations = detailed.get("transformations", {}) or {}
    if not transformations:
        print(f"  {DIM}None recorded yet.{RESET}")
    else:
        sorted_t = sorted(transformations.items(), key=lambda x: x[1]["count"], reverse=True)
        for name, info in sorted_t:
            print(f"  - {name}: {info['count']} ({info['percentage']}%)")
    print("-" * 60 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description="ast-guard v1.2 - Deterministic reward hacking detector for LLM-generated Python code."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")
    
    # 1. check
    check_parser = subparsers.add_parser("check", help="Checks generated Python code against original code.")
    check_parser.add_argument("original", help="Path to the original code (.py)")
    check_parser.add_argument("generated", help="Path to the generated/optimized code (.py)")
    check_parser.add_argument("--mode", choices=["strict", "standard", "audit"], help="Sensitivity Mode (CLI-Default: standard, API-Default: strict)")
    check_parser.add_argument("--json", action="store_true", help="Output the analysis report in JSON format")
    check_parser.add_argument("--sarif", action="store_true", help="Output the analysis report in SARIF v2.1.0 format for GitHub Security Tab")
    check_parser.add_argument("--no-telemetry", action="store_true", help="Disables local telemetry logging")
    
    # 2. feedback
    fb_parser = subparsers.add_parser("feedback", help="Submit feedback for a specific scan.")
    fb_parser.add_argument("--id", required=True, help="Scan ID of the relevant scan")
    fb_parser.add_argument("--label", required=True, choices=["correct", "false-positive", "false-negative"], help="Feedback-Label")
    fb_parser.add_argument("--comment", default="", help="Optional free-text comment")
    
    # 3. export
    export_parser = subparsers.add_parser("export", help="Exports the local anonymized telemetry database.")
    export_parser.add_argument("--output", required=True, help="Target path for the sanitized JSONL file")
    
    # 4. stats
    stats_parser = subparsers.add_parser("stats", help="Shows local telemetry usage statistics.")
    stats_parser.add_argument("--disable-prompt", action="store_true", help="Permanently disables the sharing prompt")
    stats_parser.add_argument("--detailed", action="store_true", help="Show extended statistics: metric deltas, check correlations, verdicts by mode")
    stats_parser.add_argument("--export-stats", metavar="PATH", help="Export detailed statistics as JSON to the given path")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
        
    if args.command == "check":
        if not os.path.exists(args.original):
            print(f"Error: Original file '{args.original}' does not exist.", file=sys.stderr)
            sys.exit(1)
        if not os.path.exists(args.generated):
            print(f"Error: Generated file '{args.generated}' does not exist.", file=sys.stderr)
            sys.exit(1)
            
        try:
            with open(args.original, "r", encoding="utf-8") as f:
                orig_code = f.read()
            with open(args.generated, "r", encoding="utf-8") as f:
                gen_code = f.read()
        except Exception as e:
            print(f"Error reading source files: {e}", file=sys.stderr)
            sys.exit(1)
            
        # Run Scan
        mode_val = args.mode or "standard" # CLI default is standard
        telemetry_enabled = not args.no_telemetry
        result = scan(orig_code, gen_code, mode=mode_val, telemetry_enabled=telemetry_enabled)
        
        # Format and output results
        if args.sarif:
            print(format_sarif_report(result, original_file=args.original, generated_file=args.generated))
        elif args.json:
            print(format_json_report(result))
        else:
            if mode_val != "audit":
                print_ansi_report(result)
                
        # Handle Sharing Prompt
        if not args.json and not args.sarif and mode_val != "audit" and telemetry_enabled:
            should_prompt, count = check_sharing_prompt()
            if should_prompt:
                print(f"\033[94m{BOLD}[INFO]{RESET} You have completed {count} scans with ast-guard!")
                print("  Would you like to contribute to the anonymized community dataset?")
                print(f"  Export your sanitized data via: {BOLD}ast-guard export --output data.jsonl{RESET}")
                print(f"  Permanently disable this prompt: {BOLD}ast-guard stats --disable-prompt{RESET}\n")
                
        # Exit code logic
        if mode_val == "audit":
            sys.exit(0)
        elif result["verdict"] == "CRITICAL":
            sys.exit(1)
        else:
            sys.exit(0)
            
    elif args.command == "feedback":
        success = feedback(args.id, args.label, args.comment)
        if success:
            print(f"Feedback successfully submitted for scan '{args.id}'!")
            sys.exit(0)
        else:
            print("Error saving feedback.", file=sys.stderr)
            sys.exit(1)
            
    elif args.command == "export":
        success = export_telemetry(args.output)
        if success:
            print(f"Anonymized telemetry data successfully exported to '{args.output}'!")
            sys.exit(0)
        else:
            print("Error exporting telemetry data. Do any scans exist yet?", file=sys.stderr)
            sys.exit(1)
            
    elif args.command == "stats":
        if args.disable_prompt:
            disable_sharing_prompt()
            print("Sharing prompt permanently disabled.")
            sys.exit(0)

        if args.export_stats:
            detailed = get_detailed_stats()
            try:
                with open(args.export_stats, "w", encoding="utf-8") as f:
                    json.dump(detailed, f, indent=2, sort_keys=True)
            except Exception as e:
                print(f"Error writing stats to '{args.export_stats}': {e}", file=sys.stderr)
                sys.exit(1)
            print(f"Detailed statistics exported to '{args.export_stats}'.")
            sys.exit(0)

        if args.detailed:
            _print_detailed_stats(get_detailed_stats())
            sys.exit(0)

        stats = get_stats()
        print(f"\n{BOLD}{UNDERLINE}LOCAL AST-GUARD TELEMETRY STATS{RESET}")
        print(f"{BOLD}Total Scans:{RESET} {stats['total_scans']}")
        print(f"\n{BOLD}Verdict Distribution:{RESET}")
        for k, v in stats["verdicts"].items():
            print(f"  {k}: {v}")

        print(f"\n{BOLD}Triggered Checks:{RESET}")
        if stats["checks"]:
            for check, counts in stats["checks"].items():
                print(f"  {check}:")
                for status, c in counts.items():
                    if c > 0:
                        print(f"    - {status}: {c}")
        else:
            print("  No scans recorded yet.")

        print(f"\n{BOLD}Most Common Transformations:{RESET}")
        if stats["transformations"]:
            for t, c in sorted(stats["transformations"].items(), key=lambda x: x[1], reverse=True):
                print(f"  - {t}: {c}")
        else:
            print("  None recorded yet.")
        print("-" * 60 + "\n")
        sys.exit(0)

if __name__ == "__main__":
    main()
