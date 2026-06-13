"""Tests for generator/split.py — determinism and split assignment."""

from __future__ import annotations

import pytest

from generator.split import (
    COUPLED_CATEGORIES,
    assign_split,
    compute_prompt_hash,
    make_sample_id,
)


# ---------------------------------------------------------------------------
# make_sample_id
# ---------------------------------------------------------------------------

def test_coupled_id_has_coupled_prefix():
    sid = make_sample_id("hardcoded_outputs/mbpp_1", is_open=False)
    assert sid.startswith("coupled/"), sid


def test_open_id_has_open_prefix():
    sid = make_sample_id("open/imperative/claude-sonnet-4-6/mbpp_1", is_open=True)
    assert sid.startswith("open/"), sid


def test_make_sample_id_deterministic():
    key = "hardcoded_outputs/mbpp_42"
    assert make_sample_id(key, is_open=False) == make_sample_id(key, is_open=False)


def test_make_sample_id_open_deterministic():
    key = "open/adversarial/claude-opus-4-7/humaneval_7"
    assert make_sample_id(key, is_open=True) == make_sample_id(key, is_open=True)


def test_make_sample_id_different_keys_produce_different_ids():
    a = make_sample_id("hardcoded_outputs/seed_1", is_open=False)
    b = make_sample_id("hardcoded_outputs/seed_2", is_open=False)
    assert a != b


def test_make_sample_id_open_vs_coupled_same_key_differ():
    key = "some_key/seed_99"
    coupled = make_sample_id(key, is_open=False)
    open_ = make_sample_id(key, is_open=True)
    assert coupled != open_
    assert coupled.startswith("coupled/")
    assert open_.startswith("open/")


def test_make_sample_id_length():
    sid = make_sample_id("foo/bar", is_open=False)
    # prefix (7 or 5 chars) + "/" + 16 hex chars
    parts = sid.split("/")
    assert len(parts) == 2
    assert len(parts[1]) == 16


# ---------------------------------------------------------------------------
# assign_split
# ---------------------------------------------------------------------------

def test_open_prefix_maps_to_eval():
    sid = make_sample_id("open/imperative/claude-sonnet-4-6/seed_1", is_open=True)
    assert assign_split(sid) == "eval"


def test_coupled_prefix_maps_to_calibration():
    sid = make_sample_id("hardcoded_outputs/seed_1", is_open=False)
    assert assign_split(sid) == "calibration"


def test_all_coupled_categories_map_to_calibration():
    for category in COUPLED_CATEGORIES:
        sid = make_sample_id(f"{category}/seed_99", is_open=False)
        assert assign_split(sid) == "calibration", f"failed for {category}"


def test_open_ids_always_map_to_eval():
    keys = [
        "open/imperative/claude-opus-4-7/mbpp_1",
        "open/adversarial/claude-sonnet-4-6/humaneval_3",
        "open/competitive/claude-haiku-4-5-20251001/apps_100",
    ]
    for key in keys:
        sid = make_sample_id(key, is_open=True)
        assert assign_split(sid) == "eval", f"failed for key={key}"


def test_no_crossover_1000_samples():
    # Same sample_id must never map to both splits (trivially true for a pure function,
    # but we verify no accidental overlap between coupled and open prefixes).
    coupled_ids = {
        make_sample_id(f"hardcoded_outputs/seed_{i}", is_open=False)
        for i in range(500)
    }
    open_ids = {
        make_sample_id(f"open/imperative/model/seed_{i}", is_open=True)
        for i in range(500)
    }
    assert coupled_ids.isdisjoint(open_ids)


def test_assign_split_pure_function():
    sid = "open/abc123def456abc1"
    for _ in range(100):
        assert assign_split(sid) == "eval"


def test_assign_split_unknown_prefix_is_calibration():
    # Anything that doesn't start with 'open/' goes to calibration.
    assert assign_split("coupled/abc") == "calibration"
    assert assign_split("tn/abc") == "calibration"
    assert assign_split("gen-mbpp_1-hardcoded-abcd1234") == "calibration"


# ---------------------------------------------------------------------------
# GeneratorLoader._infer_split — backward-compat fallback direction
# ---------------------------------------------------------------------------

def test_infer_split_unknown_category_goes_to_calibration():
    """Unknown category without split field must never silently go to eval."""
    from benchmarks.loaders.generator_loader import GeneratorLoader
    record = {"sample_id": "gen-old-format", "metadata": {}, "category": "totally_unknown"}
    assert GeneratorLoader._infer_split(record) == "calibration"


def test_infer_split_missing_category_goes_to_calibration():
    """Missing category key without split field must go to calibration."""
    from benchmarks.loaders.generator_loader import GeneratorLoader
    record = {"sample_id": "gen-old-format", "metadata": {}}
    assert GeneratorLoader._infer_split(record) == "calibration"


def test_infer_split_empty_category_goes_to_calibration():
    """Empty-string category without split field must go to calibration."""
    from benchmarks.loaders.generator_loader import GeneratorLoader
    record = {"sample_id": "gen-old-format", "metadata": {}, "category": ""}
    assert GeneratorLoader._infer_split(record) == "calibration"


def test_infer_split_explicit_eval_field_respected():
    """Explicit metadata.split='eval' must be respected."""
    from benchmarks.loaders.generator_loader import GeneratorLoader
    record = {"sample_id": "whatever", "metadata": {"split": "eval"}, "category": "unknown"}
    assert GeneratorLoader._infer_split(record) == "eval"


def test_infer_split_open_sample_id_goes_to_eval():
    """Old-style open sample without split field: sample_id prefix decides."""
    from benchmarks.loaders.generator_loader import GeneratorLoader
    record = {"sample_id": "open/abc123def456abc1", "metadata": {}, "category": "unknown"}
    assert GeneratorLoader._infer_split(record) == "eval"


def test_infer_split_invalid_split_value_raises():
    """Invalid metadata.split value must raise ValueError, not silently fall through."""
    from benchmarks.loaders.generator_loader import GeneratorLoader
    import pytest
    record = {"sample_id": "gen-x", "metadata": {"split": "train"}, "category": "hardcoded_outputs"}
    with pytest.raises(ValueError, match="Invalid metadata.split"):
        GeneratorLoader._infer_split(record)


# ---------------------------------------------------------------------------
# eval TN pairs land in eval split
# ---------------------------------------------------------------------------

def test_eval_tn_sample_id_goes_to_eval():
    """make_sample_id('eval-tn/...', is_open=True) must map to eval split."""
    sid = make_sample_id("eval-tn/mbpp-42", is_open=True)
    assert assign_split(sid) == "eval"


def test_eval_tn_distinct_from_calib_tn():
    """eval TN and calibration TN for the same seed must have different sample_ids."""
    calib = make_sample_id("tn/mbpp-42", is_open=False)
    eval_ = make_sample_id("eval-tn/mbpp-42", is_open=True)
    assert calib != eval_
    assert assign_split(calib) == "calibration"
    assert assign_split(eval_) == "eval"


def test_infer_split_eval_tn_record():
    """A record with split='eval' and label='clean' must load into eval."""
    from benchmarks.loaders.generator_loader import GeneratorLoader
    record = {
        "sample_id": make_sample_id("eval-tn/seed_1", is_open=True),
        "metadata": {"split": "eval", "label": "clean"},
        "category": "honest-vs-honest",
    }
    assert GeneratorLoader._infer_split(record) == "eval"


# ---------------------------------------------------------------------------
# open_yield counter
# ---------------------------------------------------------------------------

def test_open_yield_counter_structure():
    """GenerateStats.open_yield must track attempts and hacks per (model, variant)."""
    from generator.generate import GenerateStats
    stats = GenerateStats()
    key = ("claude-sonnet-4-6", "imperative")
    stats.open_yield[key] = {"attempts": 5, "hacks": 2}
    assert stats.open_yield[key]["attempts"] == 5
    assert stats.open_yield[key]["hacks"] == 2


def test_open_yield_independent_across_instances():
    """Each GenerateStats instance must have its own open_yield dict."""
    from generator.generate import GenerateStats
    a = GenerateStats()
    b = GenerateStats()
    a.open_yield[("m", "v")] = {"attempts": 1, "hacks": 1}
    assert ("m", "v") not in b.open_yield


def test_open_yield_appears_in_report():
    """report() must include the yield table when open_yield is populated."""
    from generator.generate import GenerateStats
    stats = GenerateStats()
    stats.open_yield[("claude-opus-4-7", "competitive")] = {"attempts": 10, "hacks": 3}
    report = stats.report()
    assert "competitive" in report
    assert "claude-opus-4-7" in report
    assert "30.0%" in report


# ---------------------------------------------------------------------------
# compute_prompt_hash
# ---------------------------------------------------------------------------

def test_compute_prompt_hash_deterministic():
    text = "Write a function that passes these tests."
    assert compute_prompt_hash(text) == compute_prompt_hash(text)


def test_compute_prompt_hash_length():
    h = compute_prompt_hash("some prompt text")
    assert len(h) == 12


def test_compute_prompt_hash_different_texts_differ():
    assert compute_prompt_hash("prompt A") != compute_prompt_hash("prompt B")


def test_compute_prompt_hash_hex():
    h = compute_prompt_hash("test")
    assert all(c in "0123456789abcdef" for c in h)
