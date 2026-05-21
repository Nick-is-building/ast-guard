import argparse
import sys
import os
from ast_guard import scan, feedback
from ast_guard.output import print_ansi_report, format_json_report
from ast_guard.telemetry import export_telemetry, get_stats, check_sharing_prompt, disable_sharing_prompt

BOLD = "\033[1m"
RESET = "\033[0m"
UNDERLINE = "\033[4m"

def main():
    parser = argparse.ArgumentParser(
        description="ast-guard v1.0 - Deterministischer Reward-Hacking-Detektor fuer LLM-generierten Python-Code."
    )
    subparsers = parser.add_subparsers(dest="command", help="Verfuegbare Subcommands")
    
    # 1. check
    check_parser = subparsers.add_parser("check", help="Prueft generierten Python-Code gegen Originalcode.")
    check_parser.add_argument("original", help="Pfad zum Originalcode (.py)")
    check_parser.add_argument("generated", help="Pfad zum generierten/optimierten Code (.py)")
    check_parser.add_argument("--mode", choices=["strict", "standard", "audit"], help="Sensitivity Mode (CLI-Default: standard, API-Default: strict)")
    check_parser.add_argument("--json", action="store_true", help="Gibt den Analyse-Report im JSON-Format aus")
    check_parser.add_argument("--no-telemetry", action="store_true", help="Deaktiviert das lokale Loggen der Telemetrie-Daten")
    
    # 2. feedback
    fb_parser = subparsers.add_parser("feedback", help="Gibt Feedback zu einem bestimmten Scan ab.")
    fb_parser.add_argument("--id", required=True, help="Scan-ID des betreffenden Scans")
    fb_parser.add_argument("--label", required=True, choices=["correct", "false-positive", "false-negative"], help="Feedback-Label")
    fb_parser.add_argument("--comment", default="", help="Optionaler Freitext-Kommentar")
    
    # 3. export
    export_parser = subparsers.add_parser("export", help="Exportiert die lokale anonymisierte Telemetrie-Datenbank.")
    export_parser.add_argument("--output", required=True, help="Zielpfad fuer die bereinigte JSONL-Datei")
    
    # 4. stats
    stats_parser = subparsers.add_parser("stats", help="Zeigt Statistiken zur lokalen Telemetrie-Nutzung an.")
    stats_parser.add_argument("--disable-prompt", action="store_true", help="Deaktiviert den einmaligen Sharing-Prompt dauerhaft")
    
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
        if args.json:
            print(format_json_report(result))
        else:
            if mode_val != "audit":
                print_ansi_report(result)
                
        # Handle Sharing Prompt
        if not args.json and mode_val != "audit" and telemetry_enabled:
            should_prompt, count = check_sharing_prompt()
            if should_prompt:
                print(f"\033[94m{BOLD}[INFO]{RESET} Sie haben bereits {count} Scans mit ast-guard durchgefuehrt!")
                print("  Moechten Sie das anonymisierte Community-Dataset unterstuetzen?")
                print(f"  Exportieren Sie Ihre bereinigten Daten via: {BOLD}ast-guard export --output data.jsonl{RESET}")
                print(f"  Diesen Prompt dauerhaft deaktivieren: {BOLD}ast-guard stats --disable-prompt{RESET}\n")
                
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
            print(f"Feedback erfolgreich fuer Scan '{args.id}' hinterlegt!")
            sys.exit(0)
        else:
            print("Fehler beim Speichern des Feedbacks.", file=sys.stderr)
            sys.exit(1)
            
    elif args.command == "export":
        success = export_telemetry(args.output)
        if success:
            print(f"Anonymisierte Telemetrie-Daten erfolgreich nach '{args.output}' exportiert!")
            sys.exit(0)
        else:
            print("Fehler beim Exportieren der Telemetrie-Daten. Existieren bereits Scans?", file=sys.stderr)
            sys.exit(1)
            
    elif args.command == "stats":
        if args.disable_prompt:
            disable_sharing_prompt()
            print("Sharing-Prompt erfolgreich dauerhaft deaktiviert.")
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
