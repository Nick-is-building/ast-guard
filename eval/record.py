"""
Shared record types for the eval harness.

EvalRecord    — input to the scorer (code + label + provenance)
ScoredRecord  — output of the scorer (verdicts + graduated scores)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class EvalRecord:
    """A single sample to evaluate."""

    id: str
    language: str
    code: str                       # the generated/hack code to analyse
    label: Literal["hack", "benign"]
    original_code: Optional[str]    # when present, pair-mode is also run
    hack_category: str              # e.g. "hardcoded-test-cases"
    dataset: str                    # e.g. "school-of-hacks"
    split: Literal["dev", "held_out"]
    metadata: dict = field(default_factory=dict)


@dataclass
class ScoredRecord:
    """Scorer output for one EvalRecord."""

    record_id: str
    label: str                      # "hack" or "benign"
    language: str
    hack_category: str
    dataset: str
    split: str

    # ── standalone mode ──────────────────────────────────────────────────
    standalone_verdict: str         # "CRITICAL", "WARNING", "CLEAN", or "ABSTAIN"
    standalone_binary: int          # 1 = any hack flag, 0 = clean; -1 = abstain
    standalone_score: float         # graduated suspicion [0.0, 1.0]
    standalone_abstain: bool

    # ── pair mode (None when no original_code was provided) ──────────────
    pair_verdict: Optional[str]
    pair_binary: Optional[int]
    pair_score: Optional[float]
    pair_abstain: Optional[bool]

    # ── raw result dicts (excluded from CSV; available in-memory) ────────
    standalone_raw: dict = field(repr=False)
    pair_raw: Optional[dict] = field(default=None, repr=False)
