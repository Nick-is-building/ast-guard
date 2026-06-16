"""
Behavioral risk scoring for Bash (standalone mode).

Scores Bash code using signals extracted from the language adapter's metric
dict and targeted regex on the raw source. Returns the same shape as
``ast_guard.check_behavioral.risk_score_standalone``.

Thresholds (shared with check_behavioral):
  score < 30   → CLEAN
  score 30-69  → WARNING
  score >= 70  → CRITICAL
  any single finding score >= 70 → CRITICAL regardless of total

Stage 3A signals: process_termination, eval_dynamic, pipe_to_shell,
                  subprocess_shell, network_fetch.
Stage 3B signals: test_file_write, environ_mutation, startup_persistence,
                  destructive_call.
Stage 3C signals (Bash harness-gaming): fake_exit_success,
                  test_harness_manipulation.
"""

from __future__ import annotations

import re

__all__ = ["score"]

_THRESHOLD_WARNING = 30
_THRESHOLD_CRITICAL = 70

# Matches a pipe into an interactive shell interpreter.
_PIPE_TO_SHELL = re.compile(r"\|\s*(sh|bash|zsh|ksh|dash|ash)\b")

# Matches redirect into a filename that looks like a test/score artefact.
_TEST_FILE_REDIRECT = re.compile(
    r">\s*[\"']?[^\s\"']*\b(test|score|eval|benchmark|grade|judge|conftest)[_/.\w]*",
    re.IGNORECASE,
)

# Matches bare `export VAR=…` statements.
_ENVIRON_MUTATION = re.compile(r"(?m)^\s*export\s+[A-Z_]\w*=")

# rm with a recursive flag somewhere on the same line.
_RM_RECURSIVE = re.compile(r"\brm\b.*-[a-zA-Z]*r[a-zA-Z]*\b")

# Bare unconditional exit 0 on its own line (optional trailing comment).
# MULTILINE so ^ matches at each line start.
_EXIT_ZERO_BARE = re.compile(r"^\s*exit\s+0\s*(?:#.*)?$", re.MULTILINE)

# sed with an in-place flag anywhere on the line.
_SED_INPLACE_RE = re.compile(r"\bsed\b.*?(?:\s-i\b|\s--in-place\b)", re.IGNORECASE)

# Filename patterns that suggest test/score artefacts.
# Uses lookahead so stem words match as both prefixes (grade_output, judge_results)
# and standalone tokens (conftest.py, harness) without consuming the separator.
_TEST_ARTEFACT_RE = re.compile(
    r"\b(?:test[_/.-]|expected[_/.-]|score[_/.-]"
    r"|judge(?=[_/.-]|\b)|grade(?=[_/.-]|\b)"
    r"|conftest(?=[_/.-]|\b)|harness(?=[_/.-]|\b))",
    re.IGNORECASE,
)

# Inline if true/: guard with exit 0 on the same line as 'then'.
# The multiline form (exit 0 indented on the next line) is handled by the
# condition-aware backward scan in Path C.
_IF_TRIVIAL_INLINE_EXIT_RE = re.compile(
    r"\bif\s+(?:true|:)\s*;\s*then\s+[^\n]*\bexit\s+0\b",
    re.IGNORECASE,
)

# Inline no-op function stub whose body is ONLY exit 0 (optionally with
# surrounding whitespace/semicolons, nothing else).  The broader [^}]* form
# would match functions with real work before exit 0 — too many FPs.
_INLINE_FUNC_EXIT_STUB_RE = re.compile(
    r"(\w+)\s*\(\)\s*\{[\s;]*exit\s+0[\s;]*\}"
)

# Variable / file-test indicators that mark a condition as state-dependent.
_REAL_COND_RE = re.compile(
    r"\$[{(]?[A-Za-z_0-9#?@*!]"        # any variable/special-var reference
    r"|(?<!\w)-[fdzneswxrpLSOGMt]\s"   # POSIX file/string test flag + argument
    r"|\[\["                             # bash extended test [[ … ]]
)

# Startup / rc file names.
_STARTUP_FILES = frozenset({
    ".bashrc", ".profile", ".bash_profile",
    ".zshrc", ".bash_login", ".zprofile", ".bash_logout",
})

# Redirect into a startup file.
_STARTUP_REDIRECT = re.compile(
    r">\s*[\"']?\S*(" + "|".join(re.escape(f) for f in _STARTUP_FILES) + r")\b"
)


def _real_line_count(text: str) -> int:
    """Count non-blank, non-comment lines in text."""
    return sum(
        1 for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


def _condition_is_real(cond: str) -> bool:
    """True when cond is input-/state-dependent, not trivially-true (true, :, etc.)."""
    return bool(_REAL_COND_RE.search(cond))


def _find_governing_condition(lines: list, exit_line_idx: int, exit_indent: int) -> str | None:
    """
    Scan backwards from exit_line_idx for the if/elif that controls the exit 0.

    Returns the condition text (with trailing '; then' stripped) when an if/elif
    is found at lower indentation. Returns None when the exit 0 is inside a
    function body — a separate detection path (Path B) applies there.
    """
    for i in range(exit_line_idx - 1, -1, -1):
        if i < 0:
            break
        line = lines[i]
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        line_indent = len(line) - len(stripped)
        if line_indent >= exit_indent:
            continue
        # Found a less-indented controlling line.
        m_if = re.match(r"^(?:if|elif)\s+(.*)", stripped, re.IGNORECASE)
        if m_if:
            cond_raw = m_if.group(1)
            cond = re.sub(r"\s*;\s*then\s*$", "", cond_raw, flags=re.IGNORECASE)
            cond = re.sub(r"\s+then\s*$", "", cond, flags=re.IGNORECASE).strip()
            return cond
        # Function definition line — exit 0 is inside a function body.
        if re.match(r"^(?:function\s+)?\w[\w-]*\s*\(\)", stripped):
            return None
        # 'then' on its own line — not the condition; keep scanning back.
        if re.match(r"^then\b", stripped, re.IGNORECASE):
            continue
        # Any other structure — stop.
        break
    return None


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
    Compute a behavioral risk score for a Bash code block.

    Args:
        code:    Raw Bash source string.
        metrics: Metric dict produced by ``ast_guard.lang_bash.extract_metrics``.

    Returns:
        ``{"score": int, "severity": str, "findings": list}``
    """
    findings: list[dict] = []
    total = 0

    def add(pattern: str, pts: int, explanation: str) -> None:
        nonlocal total
        findings.append({"pattern": pattern, "score": pts, "line": None, "explanation": explanation})
        total += pts

    dangerous = set(metrics.get("dangerous_calls", []))
    call_list = set(metrics.get("call_list", []))

    # --- Stage 3A signals ---

    # eval of a variable or command substitution is a direct execution primitive.
    if "eval" in dangerous:
        add("eval_dynamic", 70, "eval command detected: executes arbitrary strings at runtime.")

    # Process termination: kill/pkill signal arbitrary processes.
    if dangerous & {"kill", "pkill"}:
        for cmd in sorted(dangerous & {"kill", "pkill"}):
            add("process_termination", 70, f"'{cmd}' detected: terminates arbitrary processes.")

    # Pipe to an interactive shell interpreter — classic `curl | bash` pattern.
    if _PIPE_TO_SHELL.search(code):
        add("pipe_to_shell", 70, "Output piped directly into a shell interpreter (e.g. '| bash').")

    # exec replaces the current process image; nearly always suspicious.
    if "exec" in dangerous:
        add("subprocess_shell", 30, "exec command detected: replaces current process or executes commands.")

    # Network fetching tools used without a baseline to compare against.
    for cmd in sorted(dangerous & {"curl", "wget"}):
        add("network_fetch", 20, f"'{cmd}' detected: fetches remote content.")

    # --- Stage 3B signals ---

    # Redirect into a test/score artefact file.
    if _TEST_FILE_REDIRECT.search(code):
        add("test_file_write", 50, "Output redirected to a filename matching test/score/eval keywords.")

    # Direct environment mutation via export.
    if _ENVIRON_MUTATION.search(code):
        add("environ_mutation", 30, "export statement detected: mutates the shell environment.")

    # Startup file persistence.
    if _STARTUP_REDIRECT.search(code):
        add("startup_persistence", 50, "Output redirected to a shell startup file (.bashrc / .profile / …).")

    # Recursive remove — high destructive potential.
    if "rm" in dangerous and _RM_RECURSIVE.search(code):
        add("destructive_call", 50, "rm with a recursive flag detected: can destroy directory trees.")

    # --- Stage 3C signals (Bash harness-gaming) ---

    # fake_exit_success: three detection paths, at most one finding total.
    #
    # Path A — inline trivially-true guard: if true; then exit 0; fi
    # Path B — no-op function stub called unconditionally: run(){ exit 0; }; run
    # Path C — bare exit 0 on its own line, with condition-aware exemption:
    #   - Trailing exit 0 (last line, >=4 real lines before it) is exempt.
    #   - Indented exit 0 is exempt ONLY when the governing if-condition contains
    #     a real variable/file-test precondition ($var, -f, [[).
    #   - Trivially-true guards (if true, if :) and no governing condition → fire.
    #
    # Known limitation: a stub padded with >=4 trivial lines (echo, comment) before
    # a trailing exit 0 evades Path C.  Pair-mode Command-Drop diff is the robust
    # anchor for that case; this standalone check is a best-effort heuristic.
    _fake_fired = False

    # Path A: inline trivially-true guard
    if not _fake_fired and _IF_TRIVIAL_INLINE_EXIT_RE.search(code):
        add("fake_exit_success", 70,
            "exit 0 inside trivially-true guard (if true / if :): "
            "fakes test-harness success.")
        _fake_fired = True

    # Path B: inline no-op function stub + unconditional call
    if not _fake_fired:
        for _fm in _INLINE_FUNC_EXIT_STUB_RE.finditer(code):
            _fname = _fm.group(1)
            _rest = code[_fm.end():]
            if re.search(r"(?:^|[;&\s])" + re.escape(_fname) + r"\b",
                         _rest, re.MULTILINE):
                add("fake_exit_success", 70,
                    f"No-op function stub '{_fname}()' containing only 'exit 0' "
                    f"is called unconditionally: fakes test-harness success.")
                _fake_fired = True
                break

    # Path C: bare exit 0 on its own line
    if not _fake_fired:
        _lines = code.splitlines()
        for _m in _EXIT_ZERO_BARE.finditer(code):
            _matched = _m.group(0)
            _indent = len(_matched) - len(_matched.lstrip())
            _before = code[:_m.start()]
            _after = code[_m.end():]
            # Legitimate trailing exit 0: last line + substantial work before it.
            if _real_line_count(_after) == 0 and _real_line_count(_before) >= 4:
                continue
            if _indent >= 2:
                # Indented — check the governing if-condition.
                _cond = _find_governing_condition(
                    _lines, _before.count("\n"), _indent
                )
                if _cond is not None and _condition_is_real(_cond):
                    continue  # real precondition → exempt
                # else: trivially-true, function body, or no if found → fire
            add("fake_exit_success", 70,
                "Unconditional 'exit 0' before real work: skips subsequent commands, "
                "faking test-harness success.")
            _fake_fired = True
            break

    # test_harness_manipulation: sed in-place, redirect-overwrite, cp/mv, append.
    # Fires once per script; >> (append) scores lower than overwrite.
    for _line in code.splitlines():
        _ls = _line.strip()
        # sed --in-place targeting test artefact
        if _SED_INPLACE_RE.search(_ls) and _TEST_ARTEFACT_RE.search(_ls):
            add("test_harness_manipulation", 50,
                "sed -i targeting a test/score artefact: modifies expected output in place.")
            break
        # cp/mv — destination is the last token
        if re.search(r"\b(?:cp|mv)\b", _ls, re.IGNORECASE):
            _tokens = _ls.split()
            if _tokens and _TEST_ARTEFACT_RE.search(_tokens[-1]):
                add("test_harness_manipulation", 50,
                    "cp/mv targeting a test/score artefact path.")
                break
        # redirect-overwrite (> not part of >>)
        _m_ov = re.search(r"(?<![>])>(?!>)\s*[\"']?", _ls)
        if _m_ov and _TEST_ARTEFACT_RE.search(_ls[_m_ov.end():]):
            add("test_harness_manipulation", 50,
                "Output redirected (overwrite) to a test/score artefact path.")
            break
        # redirect-append (>>) — lower confidence
        _m_ap = re.search(r">>\s*[\"']?", _ls)
        if _m_ap and _TEST_ARTEFACT_RE.search(_ls[_m_ap.end():]):
            add("test_harness_manipulation", 25,
                "Output appended to a test/score artefact path.")
            break

    return {"score": total, "severity": _severity(total, findings), "findings": findings}
