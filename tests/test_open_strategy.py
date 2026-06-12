"""Tests for the open hack generation strategy in generator/hack_strategies.py."""

from __future__ import annotations

import pytest

from generator.hack_strategies import (
    DEFAULT_OPEN_MODELS,
    OPEN_HACK_STRATEGY,
    OPEN_PROMPT_VARIANTS,
    HackStrategy,
    OpenHackStrategy,
)


# ---------------------------------------------------------------------------
# OpenHackStrategy structure
# ---------------------------------------------------------------------------

def test_open_strategy_has_no_ast_guard_checks():
    assert not hasattr(OPEN_HACK_STRATEGY, "ast_guard_checks")


def test_open_strategy_is_distinct_type():
    assert isinstance(OPEN_HACK_STRATEGY, OpenHackStrategy)
    assert not isinstance(OPEN_HACK_STRATEGY, HackStrategy)


def test_open_strategy_name():
    assert OPEN_HACK_STRATEGY.name == "open"


def test_minimum_prompt_variants():
    assert len(OPEN_PROMPT_VARIANTS) >= 3, (
        f"Expected at least 3 prompt variants, got {len(OPEN_PROMPT_VARIANTS)}"
    )


def test_prompt_variants_have_name_and_text():
    for item in OPEN_PROMPT_VARIANTS:
        name, text = item
        assert isinstance(name, str) and name
        assert isinstance(text, str) and text


def test_prompt_variant_names_are_unique():
    names = [name for name, _ in OPEN_PROMPT_VARIANTS]
    assert len(names) == len(set(names)), "Prompt variant names must be unique"


def test_minimum_open_models():
    assert len(DEFAULT_OPEN_MODELS) >= 2, (
        f"Expected at least 2 open models, got {len(DEFAULT_OPEN_MODELS)}"
    )


def test_open_strategy_models_match_default():
    assert set(OPEN_HACK_STRATEGY.models) == set(DEFAULT_OPEN_MODELS)


def test_open_strategy_variants_match_module_list():
    strategy_variants = set(OPEN_HACK_STRATEGY.prompt_variants)
    module_variants = set(tuple(v) for v in OPEN_PROMPT_VARIANTS)
    assert strategy_variants == module_variants


# ---------------------------------------------------------------------------
# No structural hints in system prompt or variant instructions
# ---------------------------------------------------------------------------

# Check names that must not appear (case-insensitive)
_FORBIDDEN_CHECK_NAMES = {
    "hardcoding",
    "complexity",
    "enumeration",
    "behavioral",
}

# Structural pattern words that would implicitly prescribe an approach
_FORBIDDEN_STRUCTURAL_HINTS = {
    "lookup",
    "table",
    "dict",
    "elif",
    "hardcode",
    "if/elif",
    "enumerate",
}

_ALL_FORBIDDEN = _FORBIDDEN_CHECK_NAMES | _FORBIDDEN_STRUCTURAL_HINTS


def _contains_forbidden(text: str) -> list[str]:
    lower = text.lower()
    return [word for word in _ALL_FORBIDDEN if word in lower]


def test_system_prompt_no_structural_hints():
    hits = _contains_forbidden(OPEN_HACK_STRATEGY.system_prompt)
    assert not hits, (
        f"System prompt contains forbidden terms {hits!r}. "
        "The open mode must not prescribe structural patterns."
    )


@pytest.mark.parametrize("variant", OPEN_PROMPT_VARIANTS, ids=[v[0] for v in OPEN_PROMPT_VARIANTS])
def test_prompt_variant_no_structural_hints(variant):
    name, text = variant
    hits = _contains_forbidden(text)
    assert not hits, (
        f"Prompt variant {name!r} contains forbidden terms {hits!r}. "
        "Open-mode prompts must not suggest structural patterns."
    )


# ---------------------------------------------------------------------------
# Coupled strategies remain unchanged
# ---------------------------------------------------------------------------

def test_coupled_strategies_still_have_ast_guard_checks():
    from generator.hack_strategies import all_strategies
    for strategy in all_strategies():
        assert hasattr(strategy, "ast_guard_checks"), (
            f"Coupled strategy {strategy.category!r} lost its ast_guard_checks field"
        )
        assert len(strategy.ast_guard_checks) > 0


def test_six_coupled_strategies_registered():
    from generator.hack_strategies import all_strategies
    assert len(all_strategies()) == 6
