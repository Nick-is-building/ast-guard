"""Split assignment for generator output — calibration vs. eval."""

from __future__ import annotations

import hashlib
from typing import Literal

# The 6 check-coupled strategy categories (always calibration split).
COUPLED_CATEGORIES: frozenset[str] = frozenset({
    "hardcoded_outputs",
    "lookup_table",
    "eval_obfuscation",
    "forbidden_import",
    "enumeration",
    "complexity_collapse",
})

_OPEN_PREFIX = "open"
_COUPLED_PREFIX = "coupled"


def make_sample_id(key: str, *, is_open: bool) -> str:
    """
    Build a deterministic, collision-resistant sample_id from an arbitrary key.

    Format: '{prefix}/{sha256(key)[:16]}'
    The prefix encodes the split; the 16-char hash makes the ID compact and unique.

    Suggested key formats:
      coupled:  '{strategy_category}/{seed_id}'
      open:     'open/{variant_name}/{model_id}/{seed_id}'
      tn:       'tn/{seed_id}'
    """
    prefix = _OPEN_PREFIX if is_open else _COUPLED_PREFIX
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return f"{prefix}/{digest}"


def assign_split(sample_id: str) -> Literal["calibration", "eval"]:
    """
    Derive the calibration/eval split from the sample_id alone.

    Pure function — same input always returns the same output.
    sample_ids beginning with 'open/' map to 'eval'; all others map to 'calibration'.
    """
    if sample_id.startswith(f"{_OPEN_PREFIX}/"):
        return "eval"
    return "calibration"


def compute_prompt_hash(prompt_text: str) -> str:
    """Return a 12-character SHA-256 hex prefix of the full prompt text."""
    return hashlib.sha256(prompt_text.encode()).hexdigest()[:12]
