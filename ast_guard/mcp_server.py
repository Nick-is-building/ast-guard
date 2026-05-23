"""
ast-guard MCP Server

Exposes ast-guard's reward hacking detection as MCP tools
for Claude Code, Cursor, Codex, and any MCP-compatible agent.

Usage:
    pip install ast-guard[mcp]
    ast-guard-mcp                          # start the server
"""

from mcp.server.fastmcp import FastMCP
from ast_guard import scan, feedback

mcp = FastMCP(
    "ast-guard",
    instructions="Deterministic reward hacking detector for LLM-generated Python code",
)


@mcp.tool()
def ast_guard_scan(
    original_code: str,
    generated_code: str,
    mode: str = "strict",
) -> dict:
    """Scan LLM-generated Python code for reward hacking patterns.

    Compares original code against generated code using deterministic
    AST analysis. Detects hardcoded lookup tables, complexity collapses,
    forbidden system calls, obfuscation, and import drift.

    No LLM involved — pure static analysis, zero latency, fully reproducible.

    Args:
        original_code: The original Python source code before LLM modification.
        generated_code: The LLM-generated or modified Python source code.
        mode: Detection sensitivity — "strict" (default, blocks CRITICAL),
              "standard" (warns only), or "audit" (silent, telemetry only).

    Returns:
        A dict with:
        - verdict: "CLEAN", "WARNING", or "CRITICAL"
        - checks: Per-check results with findings and severity
        - allowlist_transformations: Detected legitimate optimizations
        - telemetry: Anonymized scan metrics (no code content)
    """
    if mode not in ("strict", "standard", "audit"):
        return {"error": f"Invalid mode '{mode}'. Use 'strict', 'standard', or 'audit'."}

    try:
        result = scan(original_code, generated_code, mode=mode)
        return result
    except SyntaxError as e:
        return {
            "verdict": "ERROR",
            "error": f"Could not parse code: {e}",
            "hint": "Ensure both original_code and generated_code are valid Python.",
        }
    except Exception as e:
        return {
            "verdict": "ERROR",
            "error": f"Scan failed: {type(e).__name__}: {e}",
        }


@mcp.tool()
def ast_guard_feedback(
    scan_id: str,
    label: str,
) -> dict:
    """Submit feedback on a scan result to improve ast-guard's thresholds.

    After reviewing a scan result, use this tool to label it as correct
    or incorrect. Feedback is stored locally and contributes to the
    community dataset when exported.

    Args:
        scan_id: The scan_id from a previous scan result's telemetry.
        label: One of "true_positive", "false_positive", "true_negative", "false_negative".

    Returns:
        Confirmation of feedback submission.
    """
    valid_labels = ("true_positive", "false_positive", "true_negative", "false_negative")
    if label not in valid_labels:
        return {"error": f"Invalid label '{label}'. Use one of: {', '.join(valid_labels)}"}

    try:
        feedback(scan_id, label)
        return {"status": "ok", "scan_id": scan_id, "label": label}
    except Exception as e:
        return {"error": f"Feedback failed: {type(e).__name__}: {e}"}


def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
