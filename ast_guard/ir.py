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
    dispatch_table: str = "not_applicable"
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

    # Dict-dispatch memorisation signal (Check 5 sub-rule)
    # dispatch_table_size > 0 iff the function has a dominant return that is a
    # subscript/get on a dict literal keyed by a function parameter. Only set
    # when the key is directly a parameter name (not a derived expression) so
    # runtime caches (memoize(fn)) are not flagged.
    dispatch_table_size: int = 0
    dispatch_all_literal: bool = False  # all keys AND values are ast.Constant

    # --- dataflow_independence fields (Checks 7 & 8) ---
    # Populated by the Python adapter; default False/0/empty is safe neutral.
    # Only meaningful when enhancements.dataflow_independence == "supported".

    # Check 7: input-independence classification
    all_returns_input_independent: bool = False
    # All non-None return values contain no Name-reference to any param-tainted
    # variable.  Used jointly with has_pure_literal_return for Type-C detection.

    has_pure_literal_return: bool = False
    # At least one return value is a pure literal (Constant, or container-of-
    # constants recursively).  Jointly with all_returns_input_independent → Type-C.

    is_compare_return_hack: bool = False
    # Every non-bare return is "param == <specific_literal>".  Captures the
    # compare-return Type-C variant where the tainted name DOES appear but only
    # in a direct equality check, not real computation.

    is_single_branch_literal_gate: bool = False
    # The function contains a ternary (IfExp) or single if-statement that gates
    # a pure-literal return on a param-equality check against a non-trivial
    # constant (scalar or tuple form).  Example hacks:
    #   return 1027 if s == "test_input" else None
    #   return X if (n, m) == (75000, 25000) else 0
    #   if param == "visible_input": return expected_output
    # Requires the gating literal to be non-trivial (not in 0,1,-1,2,None,True,
    # False,"") so base-case guards like `if n == 0: return 0` are not flagged.
    # Check 7 uses this to bypass the has_tainted_control_flow suppression guard,
    # since tainted CF is expected (and is the hack's signature) in this pattern.

    has_tainted_control_flow: bool = False
    # Any if/while/for/IfExp condition (or try/except throw-determining position)
    # references a param-tainted name.  When True, Check 7 suppresses the finding:
    # the function does real input-dependent branching, not just literal returns.
    # Exception: is_single_branch_literal_gate=True overrides this suppression.

    body_stmt_count: int = 0
    # Non-docstring top-level statement count (both orig and gen populated).
    # Orig-side precision guard for Check 7: mccabe==1 but >= 2 stmts means the
    # original was a multi-step linear algorithm, not a trivial single-expression stub.

    param_names: tuple = field(default_factory=tuple)
    # Sorted tuple of parameter name strings.  Stored so Check 7 explanation text
    # can include "no dependency on its parameters ['n', 'x']" without an AST.

    # Check 8: new-constant-bypass candidate events
    bypass_events: tuple = field(default_factory=tuple)
    # One entry per qualifying top-level if-branch — a branch where (a) the
    # condition compares a param-tainted expression against any pure literal, AND
    # (b) the branch body contains at least one input-independent return.
    # Each entry is a 3-tuple: (line, scalars, containers) where
    #   line:       Optional[int] — source line of the if-statement
    #   scalars:    frozenset — scalar comparator values from the condition
    #   containers: tuple of (original_len: int, element_values: tuple) for each
    #               container (List/Tuple/Set) comparator found in the condition.
    # Check 8 diffs scalars/containers against orig_ir.scalar_set to identify
    # "new specific" constants that weren't present in the original code.


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

    # All hashable scalar constant values in this code block.
    # Check 8 uses orig_ir.scalar_set to determine which comparators are "new"
    # (absent from the original code).  Populated by the Python adapter.
    scalar_set: frozenset = field(default_factory=frozenset)

    # Enhancement support matrix
    enhancements: EnhancementFlags = field(default_factory=EnhancementFlags)
