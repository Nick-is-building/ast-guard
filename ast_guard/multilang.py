"""
Multi-language dispatch (v1.4, Phase 2).

Detects which language a snippet is written in and routes it to the
appropriate adapter. All adapters return the same metric-dict shape that
``ast_guard.analyzer.extract_metrics`` returns for Python, so the checks in
``checks.py`` remain language-agnostic.

Languages supported:
    - python      (built-in, zero-dep, via ``ast``)
    - bash        (requires ``ast-guard[multilang]``)
    - javascript  (requires ``ast-guard[multilang]``)

Detection is deterministic and best-effort: shebang first, then a small
keyword-scored heuristic. When nothing scores, returns ``"unknown"``.
"""

from __future__ import annotations

import re

SUPPORTED_LANGUAGES = ("python", "bash", "javascript")

_SHEBANG_BASH = re.compile(r"^#!.*\b(bash|/sh|zsh|ksh|dash|ash)\b")
_SHEBANG_PYTHON = re.compile(r"^#!.*\bpython[23]?\b")
_SHEBANG_JS = re.compile(r"^#!.*\b(node|deno|bun)\b")

# Python signals.
_PY_PATTERNS = (
    (re.compile(r"^\s*def\s+\w+\s*\(", re.M), 3),
    (re.compile(r"^\s*async\s+def\s+\w+\s*\(", re.M), 3),
    (re.compile(r"^\s*from\s+[\w.]+\s+import\s+", re.M), 3),
    (re.compile(r"^\s*import\s+[\w.]+\s*$", re.M), 2),
    (re.compile(r"^\s*class\s+\w+\s*[(:]", re.M), 3),
    (re.compile(r"\bself\b"), 2),
    (re.compile(r"\b__name__\b"), 2),
    (re.compile(r"\bprint\s*\("), 1),
    (re.compile(r":\s*(#.*)?$", re.M), 1),
    (re.compile(r"\bNone\b"), 1),
    (re.compile(r"\bTrue\b|\bFalse\b"), 1),
    (re.compile(r"\belif\b"), 2),
)

# JavaScript signals.
_JS_PATTERNS = (
    (re.compile(r"\bfunction\s+\w+\s*\("), 3),
    (re.compile(r"\bfunction\s*\("), 2),
    (re.compile(r"\b(const|let|var)\s+[\w{[]"), 2),
    (re.compile(r"=>"), 2),
    (re.compile(r"\brequire\s*\(\s*['\"]"), 3),
    (re.compile(r"^\s*import\s+.+\s+from\s+['\"]", re.M), 3),
    (re.compile(r"\bconsole\s*\.\s*log\b"), 2),
    (re.compile(r"\bundefined\b"), 1),
    (re.compile(r";\s*$", re.M), 1),
    (re.compile(r"\bnew\s+[A-Z]\w*\s*\("), 1),
    (re.compile(r"`[^`]*\$\{"), 1),
)

# Bash signals.
_BASH_PATTERNS = (
    (re.compile(r"^\s*(if|elif|while|until)\s+\[\[?", re.M), 3),
    (re.compile(r"\bfi\b"), 2),
    (re.compile(r"\bdone\b"), 2),
    (re.compile(r"\besac\b"), 2),
    (re.compile(r"^\s*\w+\s*\(\)\s*\{", re.M), 2),
    (re.compile(r"^\s*(source|\.)\s+\S+", re.M), 2),
    (re.compile(r"\$\{[A-Za-z_]\w*\}"), 1),
    (re.compile(r"\$\([^)]*\)"), 1),
    (re.compile(r"\becho\s+"), 1),
    (re.compile(r"\bthen\b"), 1),
    (re.compile(r"\[\[\s+.+\s+\]\]"), 2),
    (re.compile(r"^\s*[A-Z_]\w*=[^=]", re.M), 1),
)


def _score(code: str, patterns) -> int:
    return sum(weight for pattern, weight in patterns if pattern.search(code))


def detect_language(code: str) -> str:
    """
    Detect the source language of ``code``.

    Returns one of ``"python"``, ``"bash"``, ``"javascript"``, or
    ``"unknown"``. Detection is purely lexical:

        1. Look at the shebang line if present.
        2. Otherwise, score each language's keyword/syntax markers and
           return the winner if any score is positive.
    """
    if not code or not code.strip():
        return "unknown"

    first_line = code.lstrip().split("\n", 1)[0]
    if first_line.startswith("#!"):
        if _SHEBANG_PYTHON.match(first_line):
            return "python"
        if _SHEBANG_JS.match(first_line):
            return "javascript"
        if _SHEBANG_BASH.match(first_line):
            return "bash"

    scores = {
        "python": _score(code, _PY_PATTERNS),
        "javascript": _score(code, _JS_PATTERNS),
        "bash": _score(code, _BASH_PATTERNS),
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "unknown"
    return best


def extract_metrics_multilang(code: str, language: str | None = None) -> dict:
    """
    Extract the standard ast-guard metric dictionary for any supported
    language. If ``language`` is None, it is auto-detected via
    :func:`detect_language`.

    Raises:
        ValueError: if the language is unsupported or detection failed.
        ImportError: if a non-Python language is requested without the
            optional ``ast-guard[multilang]`` extras installed.
    """
    if language is None:
        language = detect_language(code)

    if language == "python":
        # Python adapter wraps the existing stdlib analyzer so users without
        # the multilang extras can still scan Python.
        from .analyzer import extract_metrics as _py_extract
        metrics = _py_extract(code)
        metrics.setdefault("language", "python")
        return metrics

    if language == "bash":
        from . import lang_bash
        return lang_bash.extract_metrics(code)

    if language == "javascript":
        from . import lang_javascript
        return lang_javascript.extract_metrics(code)

    raise ValueError(
        f"Unsupported language: {language!r}. "
        f"Supported: {', '.join(SUPPORTED_LANGUAGES)}."
    )
