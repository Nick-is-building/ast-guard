"""
Behavioral risk scoring for JavaScript/TypeScript (standalone mode).

Scores JS code using signals from the language adapter's metric dict and
targeted regex on the raw source. Returns the same shape as
``ast_guard.check_behavioral.risk_score_standalone``.

Thresholds (shared with check_behavioral):
  score < 30   → CLEAN
  score 30-69  → WARNING
  score >= 70  → CRITICAL
  any single finding score >= 70 → CRITICAL regardless of total

Stage 3A signals: eval_dynamic, process_termination, subprocess_shell,
                  dangerous_import.
Stage 3B signals: test_file_write, environ_mutation, module_cache_manipulation.

Known limitation: the object-as-lookup dispatch pattern
  ``const actions = { foo: fn, bar: fn2 }; actions[var]();``
is not detected as enumeration. Detecting it requires tracking the variable
type through assignment; that is beyond tree-sitter structural analysis and
belongs to a future dataflow pass.
"""

from __future__ import annotations

import re

__all__ = ["score"]

_THRESHOLD_WARNING = 30
_THRESHOLD_CRITICAL = 70

# process.env.VAR = ... mutation
_ENVIRON_MUTATION = re.compile(r"process\.env\.[A-Z_]\w*\s*=")

# require.cache manipulation
_MODULE_CACHE = re.compile(r"require\.cache\b")

# Score/test file path inside a write call argument.
_TEST_FILE_PATH = re.compile(
    r"""['"]/[^'"]*\b(test|score|eval|benchmark|grade|judge|conftest)[_/.\w]*['"]""",
    re.IGNORECASE,
)

# Function() constructor — dynamic code generation.
_FUNCTION_CTOR = re.compile(r"\bFunction\s*\(")


def _severity(total: int, findings: list) -> str:
    if any(f["score"] >= _THRESHOLD_CRITICAL for f in findings):
        return "CRITICAL"
    if total >= _THRESHOLD_CRITICAL:
        return "CRITICAL"
    if total >= _THRESHOLD_WARNING:
        return "WARNING"
    return "CLEAN"


def score(code: str, metrics: dict) -> dict:
    """
    Compute a behavioral risk score for a JavaScript/TypeScript code block.

    Args:
        code:    Raw JS/TS source string.
        metrics: Metric dict produced by ``ast_guard.lang_javascript.extract_metrics``.

    Returns:
        ``{"score": int, "severity": str, "findings": list}``
    """
    findings: list[dict] = []
    total = 0

    def add(pattern: str, pts: int, explanation: str) -> None:
        nonlocal total
        findings.append({"pattern": pattern, "score": pts, "line": None, "explanation": explanation})
        total += pts

    dangerous_calls = set(metrics.get("dangerous_calls", []))
    call_list = set(metrics.get("call_list", []))
    dangerous_imports = set(metrics.get("dangerous_imports", []))

    # --- Stage 3A signals ---

    # eval() is direct code injection; Function() is the constructor equivalent.
    if "eval" in dangerous_calls:
        add("eval_dynamic", 70, "eval() detected: executes arbitrary strings as code.")
    if _FUNCTION_CTOR.search(code):
        add("eval_dynamic", 70, "Function() constructor detected: dynamic code generation.")

    # process.exit() terminates the process unconditionally.
    if any("process.exit" in c for c in call_list):
        add("process_termination", 70, "process.exit() detected: terminates the Node.js process.")

    # Child-process execution functions — ability to run shell commands.
    for cmd in sorted(dangerous_calls & {"execSync", "exec", "spawnSync", "spawn", "execFileSync", "execFile"}):
        add("subprocess_shell", 30, f"'{cmd}' detected: executes shell commands from JavaScript.")

    # Importing child_process grants shell execution capability.
    if "child_process" in dangerous_imports:
        add("dangerous_import", 30, "child_process imported: provides shell command execution APIs.")

    # --- Stage 3B signals ---

    # fs writes to paths that look like test/score artefacts.
    if "fs" in dangerous_imports and _TEST_FILE_PATH.search(code):
        add("test_file_write", 50, "fs write to a path matching test/score/eval keywords detected.")

    # Direct process.env mutation — changes observable program behaviour.
    if _ENVIRON_MUTATION.search(code):
        add("environ_mutation", 30, "process.env mutation detected: alters environment variables at runtime.")

    # require.cache manipulation — can hide or replace modules.
    if _MODULE_CACHE.search(code):
        add("module_cache_manipulation", 70, "require.cache manipulation detected: can replace or hide imported modules.")

    return {"score": total, "severity": _severity(total, findings), "findings": findings}
