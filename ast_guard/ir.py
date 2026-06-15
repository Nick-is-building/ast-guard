"""
Code Intermediate Representation (IR) for ast-guard.

Language-agnostic typed containers populated by language-specific adapters
(ir_python.py; later ir_javascript.py, ir_bash.py) and consumed by check
functions. Core fields are mandatory and have neutral defaults so adapters
can omit fields they cannot compute without breaking check logic.

Enhancement flags signal which optional analysis features are available for
a given language. Checks gate language-specific code on these flags so the
same check function degrades gracefully on any language.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = ["EnhancementFlags", "FunctionIR", "DangerousCallEvent", "CodeIR"]


@dataclass
class EnhancementFlags:
    """Per-language feature-support matrix.

    Each field is one of:
      "supported"      — fully implemented, check may rely on it
      "partial"        — best-effort, check may use it with caveats
      "not_applicable" — language has no equivalent; neutral value applies

    Default: all not_applicable (safe neutral baseline for any language).
    """
    guard_clause_exemption: str = "not_applicable"
    docstring_exclusion: str = "not_applicable"
    alias_resolution: str = "not_applicable"
    anti_obfuscation_deep: str = "not_applicable"
    taint_analysis: str = "not_applicable"
    match_case_enumeration: str = "not_applicable"
    dataflow_independence: str = "not_applicable"
    intent_mismatch: str = "not_applicable"
    normalized_tree: str = "not_applicable"  # reserved for TED


@dataclass
class FunctionIR:
    """Per-function metrics from a single named function definition.

    identity uses dot-notation for qualified names (ClassName.method_name).
    Neutral values (0) let Check 2/5 skip functions with no data.
    """
    identity: str
    mccabe: int = 1
    total_ifs: int = 0
    enumeration_ifs: int = 0
    loop_count: int = 0
    param_count: int = 0
    return_count: int = 0
    line: Optional[int] = None
    normalized_node_seq: Optional[list] = None  # reserved for TED


@dataclass
class DangerousCallEvent:
    """Pre-flagged structural dangerous call pattern from the language registry.

    call_name is the resolved flat name (e.g. "subprocess.run") used for
    diff-based deduplication between orig and gen events.
    """
    pattern_id: str
    call_name: str
    severity: str  # "CRITICAL" | "WARNING"
    line: Optional[int] = None
    detail: Optional[str] = None


@dataclass
class CodeIR:
    """Language-agnostic intermediate representation for one code block.

    All collection fields default to empty, all numeric fields to neutral
    values (0 or 1) so checks can compare orig vs gen without special-casing
    missing data. The language field identifies the adapter that built this IR.
    """
    language: str = "python"

    # Conditional branches
    if_count_raw: int = 0       # all conditional branch nodes, unfiltered
    if_count: int = 0           # guard-adjusted when supported; else == raw
    guard_clause_count: int = 0  # raw - adjusted (informational)

    # Loop nesting
    loop_depth: int = 0

    # Literals
    literal_count: int = 0
    string_set: set = field(default_factory=set)
    string_linenos: dict = field(default_factory=dict)  # value -> first lineno

    # Imports and calls (flat dot-string sets)
    import_set: set = field(default_factory=set)
    call_set: set = field(default_factory=set)
    call_linenos: dict = field(default_factory=dict)  # name -> first lineno

    # Complexity and arithmetic signals
    mccabe_complexity: int = 1       # file-level; Check 2 fallback
    non_trivial_binop_count: int = 0

    # Allowlist-guard signals
    max_set_literal_size: int = 0
    max_dict_literal_size: int = 0

    # Comprehension / functional signals (for allowlist)
    comprehension_count: int = 0
    functional_call_count: int = 0

    # Per-function metrics (qualified names, for Check 2)
    per_function: list = field(default_factory=list)  # list[FunctionIR]

    # Check 5 enumeration data (bare names, preserves existing format)
    enumeration_analysis: list = field(default_factory=list)  # list[dict]

    # Pre-flagged dangerous call patterns (portable core of Check 3)
    dangerous_call_events: list = field(default_factory=list)  # list[DangerousCallEvent]

    # Enhancement support matrix
    enhancements: EnhancementFlags = field(default_factory=EnhancementFlags)
