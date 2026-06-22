"""
Unit tests for eval/metrics.py on a synthetic mini-dataset.

Tests cover: PR-AUC, precision@recall, recall@precision, binary metrics,
and the global/breakdown structure of compute_metrics().
"""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.metrics import (
    _pr_auc,
    _precision_at_min_recall,
    _recall_at_min_precision,
    _binary_metrics,
    compute_metrics,
)
from eval.record import ScoredRecord


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_sr(
    record_id: str,
    label: str,
    sa_score: float,
    sa_binary: int,
    split: str = "dev",
    language: str = "python",
    hack_category: str = "hardcoded-test-cases",
    dataset: str = "test",
    sa_abstain: bool = False,
) -> ScoredRecord:
    return ScoredRecord(
        record_id=record_id,
        label=label,
        language=language,
        hack_category=hack_category,
        dataset=dataset,
        split=split,
        standalone_verdict="CRITICAL" if sa_binary == 1 else "CLEAN",
        standalone_binary=sa_binary,
        standalone_score=sa_score,
        standalone_abstain=sa_abstain,
        pair_verdict=None,
        pair_binary=None,
        pair_score=None,
        pair_abstain=None,
        standalone_raw={},
    )


# ── PR-AUC tests ──────────────────────────────────────────────────────────────

def test_pr_auc_perfect():
    # Perfect classifier: all hacks score 1.0, all benign 0.0 → AUC = 1.0
    labels = [1, 1, 1, 0, 0, 0]
    scores = [1.0, 0.9, 0.8, 0.2, 0.1, 0.0]
    auc = _pr_auc(labels, scores)
    assert auc == pytest.approx(1.0, abs=0.01)


def test_pr_auc_random():
    # Random classifier: AUC ≈ base rate
    labels = [1, 0, 1, 0, 1, 0]
    scores = [0.5] * 6
    auc = _pr_auc(labels, scores)
    # base rate = 0.5; trapezoidal on tied scores gives ≤ 1.0
    assert 0.0 <= auc <= 1.0


def test_pr_auc_no_positives():
    labels = [0, 0, 0]
    scores = [0.9, 0.5, 0.1]
    assert _pr_auc(labels, scores) == 0.0


def test_pr_auc_single_positive():
    labels = [1, 0, 0]
    scores = [1.0, 0.5, 0.0]
    auc = _pr_auc(labels, scores)
    assert auc == pytest.approx(1.0, abs=0.01)


# ── precision@recall / recall@precision ───────────────────────────────────────

def test_precision_at_recall_80():
    labels = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
    scores = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]
    # At threshold 0.5: TP=5, FP=0 → precision=1.0, recall=1.0
    p = _precision_at_min_recall(labels, scores, 0.80)
    assert p is not None
    assert p >= 0.8


def test_recall_at_precision_90():
    labels = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
    scores = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]
    r = _recall_at_min_precision(labels, scores, 0.90)
    assert r is not None
    assert r > 0.0


def test_precision_at_recall_no_positives():
    labels = [0, 0, 0]
    scores = [0.9, 0.5, 0.1]
    assert _precision_at_min_recall(labels, scores, 0.80) is None


# ── binary metrics ────────────────────────────────────────────────────────────

def test_binary_metrics_perfect():
    labels = [1, 1, 0, 0]
    preds  = [1, 1, 0, 0]
    m = _binary_metrics(labels, preds)
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["f1"] == 1.0
    assert m["confusion_matrix"] == {"tp": 2, "fp": 0, "tn": 2, "fn": 0}


def test_binary_metrics_all_false_positive():
    labels = [0, 0]
    preds  = [1, 1]
    m = _binary_metrics(labels, preds)
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0


def test_binary_metrics_no_predictions():
    labels = [1, 0]
    preds  = [0, 0]
    m = _binary_metrics(labels, preds)
    assert m["recall"] == 0.0
    # TP+FP = 0 → precision is 0.0 (no predictions made)
    assert m["precision"] == 0.0


# ── compute_metrics integration ───────────────────────────────────────────────

def _synthetic_dataset() -> list[ScoredRecord]:
    return [
        # dev hacks — detected
        _make_sr("h1", "hack", 0.9, 1),
        _make_sr("h2", "hack", 0.8, 1),
        _make_sr("h3", "hack", 0.7, 1),
        # dev hacks — missed
        _make_sr("h4", "hack", 0.2, 0),
        # dev benign — correctly clean
        _make_sr("b1", "benign", 0.1, 0, hack_category="honest-vs-honest"),
        _make_sr("b2", "benign", 0.05, 0, hack_category="honest-vs-honest"),
        # dev benign — false positive
        _make_sr("b3", "benign", 0.6, 1, hack_category="honest-vs-honest"),
        # abstain record (excluded from metrics)
        _make_sr("a1", "hack", 0.0, -1, sa_abstain=True),
        # held_out record (excluded from dev metrics)
        _make_sr("ho1", "hack", 0.9, 1, split="held_out"),
    ]


def test_compute_metrics_structure():
    records = _synthetic_dataset()
    m = compute_metrics(records, split="dev")

    assert "global" in m
    assert "by_language" in m
    assert "by_category" in m
    assert "by_syntactic_semantic" in m

    gm = m["global"]
    assert gm["n_total"] == 8   # 8 dev records (held_out excluded)
    assert gm["n_hack"] == 4    # 4 non-abstain hacks (h1–h4; h4 missed but still a hack)
    assert gm["n_abstain"] == 1
    assert 0.0 <= gm["pr_auc"] <= 1.0
    assert 0.0 <= gm["f1"] <= 1.0


def test_compute_metrics_held_out_excluded():
    records = _synthetic_dataset()
    m = compute_metrics(records, split="dev")
    # held_out record "ho1" must not appear in dev metrics
    gm = m["global"]
    assert gm["n_total"] == 8


def test_compute_metrics_abstain_excluded():
    records = _synthetic_dataset()
    m = compute_metrics(records, split="dev")
    gm = m["global"]
    assert gm["n_abstain"] == 1
    # non-abstain count = n_total - n_abstain = 7
    assert gm["n_hack"] + gm["n_benign"] == gm["n_total"] - gm["n_abstain"]


def test_compute_metrics_syntactic_semantic_split():
    records = _synthetic_dataset()
    m = compute_metrics(records, split="dev")
    ss = m["by_syntactic_semantic"]
    # hardcoded-test-cases → syntactic, honest-vs-honest → benign
    assert "syntactic" in ss
    assert "benign" in ss
    assert ss["syntactic"]["n_hack"] > 0
    # benign slice has no hack records — but n_hack counts label=="hack" which is 0
    assert ss["benign"]["n_hack"] == 0


def test_compute_metrics_by_language():
    records = _synthetic_dataset()
    m = compute_metrics(records, split="dev")
    assert "python" in m["by_language"]
    assert m["by_language"]["python"]["n_total"] == 8
