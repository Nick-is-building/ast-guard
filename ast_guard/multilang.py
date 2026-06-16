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

SUPPORTED_LANGUAGES = ("python", "bash", "javascript", "typescript")


def is_multilang_available() -> bool:
    """Return True if the optional tree-sitter extras are installed."""
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_bash  # noqa: F401
        import tree_sitter_javascript  # noqa: F401
        return True
    except ImportError:
        return False


def is_typescript_available() -> bool:
    """Return True if the tree-sitter-typescript extra is installed."""
    try:
        import tree_sitter_typescript  # noqa: F401
        return True
    except ImportError:
        return False

_SHEBANG_BASH = re.compile(r"^#!.*\b(bash|/sh|zsh|ksh|dash|ash)\b")
_SHEBANG_PYTHON = re.compile(r"^#!.*\bpython[23]?\b")
_SHEBANG_JS = re.compile(r"^#!.*\b(node|deno|bun)\b")
# TypeScript has no standard shebang; ts-node scripts sometimes use node shebang.

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

# TypeScript signals (must score higher than JS on TS-specific syntax).
_TS_PATTERNS = (
    (re.compile(r"\binterface\s+\w+\s*\{", re.M), 4),
    (re.compile(r"\btype\s+\w+\s*="), 3),
    (re.compile(r"\benum\s+\w+\s*\{"), 3),
    (re.compile(r"\bimplements\s+\w+"), 3),
    (re.compile(r"\breadonly\s+\w+"), 2),
    (re.compile(r"\bdeclare\s+(class|function|const|var|let|module|namespace)\b"), 2),
    (re.compile(r":\s*(string|number|boolean|void|any|never|unknown)\b"), 2),
    (re.compile(r"<\w+\s*extends\s+\w+>"), 2),
    (re.compile(r"\?\s*:"), 1),  # optional property `foo?: string`
    (re.compile(r"\babstract\s+(class|method)\b"), 2),
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


def detect_language_with_info(code: str) -> dict:
    """
    Detect the source language of ``code`` and report *how* the decision was made.

    Returns a dict:
        ``language``  — one of ``"python"``, ``"bash"``, ``"javascript"``,
                        ``"typescript"``, or ``"unknown"``
        ``method``    — ``"shebang"`` | ``"keyword_score"`` | ``"unknown"``
        ``score``     — winning keyword score (0 when method is not ``"keyword_score"``)
    """
    if not code or not code.strip():
        return {"language": "unknown", "method": "unknown", "score": 0}

    first_line = code.lstrip().split("\n", 1)[0]
    if first_line.startswith("#!"):
        if _SHEBANG_PYTHON.match(first_line):
            return {"language": "python", "method": "shebang", "score": 0}
        if _SHEBANG_JS.match(first_line):
            return {"language": "javascript", "method": "shebang", "score": 0}
        if _SHEBANG_BASH.match(first_line):
            return {"language": "bash", "method": "shebang", "score": 0}

    ts_score = _score(code, _TS_PATTERNS)
    scores = {
        "python": _score(code, _PY_PATTERNS),
        "javascript": _score(code, _JS_PATTERNS),
        "bash": _score(code, _BASH_PATTERNS),
        # TypeScript: JS score + TS-specific bonus; wins over plain JS when
        # TS-specific patterns are present.
        "typescript": _score(code, _JS_PATTERNS) + ts_score,
    }
    # A code that scores TS-specific patterns but no JS at all is still TS.
    if ts_score > 0 and scores["typescript"] == ts_score:
        scores["typescript"] = ts_score
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return {"language": "unknown", "method": "unknown", "score": 0}
    return {"language": best, "method": "keyword_score", "score": scores[best]}


def detect_language(code: str) -> str:
    """
    Detect the source language of ``code``.

    Returns one of ``"python"``, ``"bash"``, ``"javascript"``,
    ``"typescript"``, or ``"unknown"``. Detection is purely lexical:

        1. Look at the shebang line if present.
        2. Otherwise, score each language's keyword/syntax markers and
           return the winner if any score is positive.
    """
    return detect_language_with_info(code)["language"]


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
        # Guard: if the code contains TypeScript-specific syntax, upgrading to
        # the TS parser prevents silent param-name corruption (tree-sitter JS
        # reads `: TypeAnnotation` as a parameter name instead of the real
        # identifier, producing wrong tainted-name sets for Check 7/8).
        ts_score = _score(code, _TS_PATTERNS)
        if ts_score > 0:
            import warnings
            warnings.warn(
                f"TypeScript syntax detected (score={ts_score}) in code passed as "
                f"language='javascript'. Upgrading to the TypeScript parser to prevent "
                f"silent metric corruption. Pass language='typescript' explicitly to "
                f"suppress this warning.",
                UserWarning,
                stacklevel=3,
            )
            from . import lang_typescript
            return lang_typescript.extract_metrics(code)
        from . import lang_javascript
        return lang_javascript.extract_metrics(code)

    if language == "typescript":
        from . import lang_typescript
        return lang_typescript.extract_metrics(code)

    raise ValueError(
        f"Unsupported language: {language!r}. "
        f"Supported: {', '.join(SUPPORTED_LANGUAGES)}."
    )
