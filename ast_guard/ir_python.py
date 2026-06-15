"""
Python AST -> CodeIR adapter.

Translates the output of ast_guard.analyzer.extract_metrics and direct AST
traversal into a language-agnostic CodeIR struct. Takes already-computed
tree and metrics to avoid duplicate parsing inside scan().

Also provides metrics_to_stub_ir() for scan_multilang() and
scan_standalone() paths where only a metrics dict is available.
"""
from __future__ import annotations

import ast
from typing import Optional

from ast_guard.analyzer import find_docstring_node_ids, build_lineno_index
from ast_guard.ir import CodeIR, DangerousCallEvent, EnhancementFlags, FunctionIR

__all__ = ["build_ir", "metrics_to_stub_ir", "empty_ir"]

# ---------------------------------------------------------------------------
# Per-language enhancement flag sets
# ---------------------------------------------------------------------------

_PYTHON_ENHANCEMENTS = EnhancementFlags(
    guard_clause_exemption="supported",
    docstring_exclusion="supported",
    alias_resolution="supported",
    anti_obfuscation_deep="supported",
    taint_analysis="supported",
    match_case_enumeration="supported",
    dataflow_independence="supported",
    intent_mismatch="supported",
    normalized_tree="not_applicable",  # reserved for future TED work
)

# Flag C: switch/case enumeration is partial — only literal-valued cases are
# detected. Object-as-lookup-table dispatch requires dataflow (not_applicable).
_JS_ENHANCEMENTS = EnhancementFlags(
    match_case_enumeration="partial",
)

# TS: same as JS + docstring_exclusion=partial (JSDoc appears as comment nodes,
# not string literals; flag is informational rather than actively filtered).
_TS_ENHANCEMENTS = EnhancementFlags(
    match_case_enumeration="partial",
    docstring_exclusion="partial",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_non_docstring_strings(tree: ast.Module) -> set:
    """String constant values that are not docstrings."""
    doc_ids = find_docstring_node_ids(tree)
    strings: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in doc_ids:
                strings.add(node.value)
    return strings


def _build_per_function(metrics: dict) -> list:
    """Merge function_complexities and enumeration_analysis into FunctionIR list.

    function_complexities uses qualified names (ClassName.method); enumeration_
    analysis uses bare names. We attempt a best-effort merge by matching the
    bare name (last component) of each qualified name. Collisions (two methods
    with the same bare name in different classes) produce a merge with the first
    enumeration_analysis entry found — acceptable because Check 5 reads
    enumeration_analysis directly, not per_function.
    """
    func_comps: dict = metrics.get("function_complexities", {}) or {}
    enum_analysis: list = metrics.get("enumeration_analysis", []) or []

    # bare-name -> first matching enum entry
    enum_map: dict = {}
    for entry in enum_analysis:
        bare = entry.get("name", "")
        if bare and bare not in enum_map:
            enum_map[bare] = entry

    result = []
    for qname, mccabe in sorted(func_comps.items()):
        bare = qname.rsplit(".", 1)[-1]
        ed = enum_map.get(bare, {})
        result.append(FunctionIR(
            identity=qname,
            mccabe=mccabe,
            total_ifs=ed.get("total_ifs", 0),
            enumeration_ifs=ed.get("enumeration_ifs", 0),
            loop_count=ed.get("loop_count", 0),
        ))
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_ir(code: str, tree: ast.Module, metrics: dict) -> CodeIR:
    """Build a full Python CodeIR from pre-parsed tree and pre-extracted metrics.

    Accepts pre-computed inputs so scan() avoids duplicate parsing.
    All Python enhancement flags are set to 'supported'.
    """
    lineno_idx = build_lineno_index(tree)
    string_set = _extract_non_docstring_strings(tree)

    if_count_adjusted = metrics.get("if_count", 0)
    guard_count = metrics.get("guard_clause_count", 0)

    return CodeIR(
        language="python",
        if_count_raw=if_count_adjusted + guard_count,
        if_count=if_count_adjusted,
        guard_clause_count=guard_count,
        loop_depth=metrics.get("loop_depth", 0),
        literal_count=metrics.get("literal_count", 0),
        string_set=string_set,
        string_linenos=lineno_idx["strings"],
        import_set=set(metrics.get("import_list", [])),
        call_set=set(metrics.get("call_list", [])),
        call_linenos=lineno_idx["calls"],
        mccabe_complexity=metrics.get("mccabe_complexity", 1),
        non_trivial_binop_count=metrics.get("non_trivial_binop_count", 0),
        max_set_literal_size=metrics.get("max_set_literal_size", 0),
        max_dict_literal_size=metrics.get("max_dict_literal_size", 0),
        comprehension_count=metrics.get("comprehension_count", 0),
        functional_call_count=metrics.get("functional_call_count", 0),
        per_function=_build_per_function(metrics),
        enumeration_analysis=metrics.get("enumeration_analysis", []) or [],
        dangerous_call_events=[],  # populated by scan() when needed
        enhancements=_PYTHON_ENHANCEMENTS,
    )


def metrics_to_stub_ir(metrics: dict, language: str = "python") -> CodeIR:
    """Convert a metrics dict to a CodeIR for non-Python or stub paths.

    Used by scan_multilang() and scan_standalone() where only a metrics dict
    is available (no Python AST tree). String sets and lineno maps are empty;
    the enhancement flags reflect the target language.
    """
    if language == "python":
        # Standalone Python path: enhancements still supported but no tree
        enh = _PYTHON_ENHANCEMENTS
    elif language == "javascript":
        enh = _JS_ENHANCEMENTS
    elif language == "typescript":
        enh = _TS_ENHANCEMENTS
    else:
        enh = EnhancementFlags()  # all not_applicable

    if_count_adjusted = metrics.get("if_count", 0)
    guard_count = metrics.get("guard_clause_count", 0)

    return CodeIR(
        language=language,
        if_count_raw=if_count_adjusted + guard_count,
        if_count=if_count_adjusted,
        guard_clause_count=guard_count,
        loop_depth=metrics.get("loop_depth", 0),
        literal_count=metrics.get("literal_count", 0),
        string_set=set(),
        string_linenos={},
        import_set=set(metrics.get("import_list", [])),
        call_set=set(metrics.get("call_list", [])),
        call_linenos={},
        mccabe_complexity=metrics.get("mccabe_complexity", 1),
        non_trivial_binop_count=metrics.get("non_trivial_binop_count", 0),
        max_set_literal_size=metrics.get("max_set_literal_size", 0),
        max_dict_literal_size=metrics.get("max_dict_literal_size", 0),
        comprehension_count=metrics.get("comprehension_count", 0),
        functional_call_count=metrics.get("functional_call_count", 0),
        per_function=_build_per_function(metrics),
        enumeration_analysis=metrics.get("enumeration_analysis", []) or [],
        dangerous_call_events=metrics.get("dangerous_call_events", []),
        enhancements=enh,
    )


def empty_ir(language: str = "python") -> CodeIR:
    """Return an IR with all neutral values (mirrors _EMPTY_METRICS in scan()).

    Used as orig_ir in scan_standalone() where no baseline exists.
    """
    if language == "python":
        enh = _PYTHON_ENHANCEMENTS
    elif language == "javascript":
        enh = _JS_ENHANCEMENTS
    elif language == "typescript":
        enh = _TS_ENHANCEMENTS
    else:
        enh = EnhancementFlags()
    return CodeIR(language=language, enhancements=enh)
