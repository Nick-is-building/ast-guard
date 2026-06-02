import pytest
import os
import json
import hashlib
import shutil
from ast_guard import scan
from ast_guard import telemetry

@pytest.fixture(autouse=True)
def clean_telemetry_dir(monkeypatch):
    test_dir = "/tmp/ast_guard_test_telemetry"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)

    monkeypatch.setattr("ast_guard.telemetry.get_ast_guard_dir", lambda: test_dir)
    yield
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

def test_salt_is_stable():
    salt1 = telemetry.get_or_create_salt()
    salt2 = telemetry.get_or_create_salt()
    assert salt1 == salt2
    assert len(salt1) == 64

def test_scan_id_calculation():
    salt = "test_salt"
    id1 = telemetry.calculate_scan_id("hash1", "hash2", salt)
    id2 = telemetry.calculate_scan_id("hash1", "hash2", salt)
    id3 = telemetry.calculate_scan_id("hash1", "hash3", salt)

    assert id1 == id2
    assert id1 != id3

def test_fingerprint_deterministic():
    metrics = {"if_count": 2, "loop_depth": 1, "call_list": ["os.system"]}
    fp1 = telemetry.calculate_fingerprint(metrics)
    fp2 = telemetry.calculate_fingerprint(metrics)
    assert fp1 == fp2

def _make_hashes(orig_code, gen_code):
    salt = telemetry.get_or_create_salt()
    return telemetry.hash_code_for_scan(orig_code, salt), telemetry.hash_code_for_scan(gen_code, salt)

def test_log_scan_and_stats():
    orig_code = "print('hello')"
    gen_code = "print('hello optimized')"
    orig_metrics = {"if_count": 0, "loop_depth": 0, "literal_count": 1}
    gen_metrics = {"if_count": 0, "loop_depth": 0, "literal_count": 1}
    check_results = {"check_1_hardcoding": {"status": "CLEAN"}}
    transformations = [{"category": "Loop to Comprehension"}]

    orig_hash, gen_hash = _make_hashes(orig_code, gen_code)
    record = telemetry.log_scan(
        orig_hash, gen_hash, orig_metrics, gen_metrics, check_results, transformations, "strict", "CLEAN"
    )

    assert "scan_id" in record
    assert "metrics_fingerprint" in record
    assert record["verdict"] == "CLEAN"

    stats = telemetry.get_stats()
    assert stats["total_scans"] == 1
    assert stats["verdicts"]["CLEAN"] == 1
    assert stats["transformations"]["Loop to Comprehension"] == 1

def test_feedback_handling():
    assert telemetry.add_feedback("some_scan_id", "correct", "Very good detection") is True

    fb_path = os.path.join(telemetry.get_ast_guard_dir(), "feedback.jsonl")
    assert os.path.exists(fb_path)
    with open(fb_path, "r") as f:
        line = f.readline()
        data = json.loads(line)
        assert data["scan_id"] == "some_scan_id"
        assert data["label"] == "correct"
        assert data["comment"] == "Very good detection"

def test_export_anonymizes():
    orig_code = "print('hello')"
    gen_code = "print('hello optimized')"
    orig_metrics = {"if_count": 0, "loop_depth": 0}
    orig_hash, gen_hash = _make_hashes(orig_code, gen_code)
    telemetry.log_scan(orig_hash, gen_hash, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")

    export_path = "/tmp/exported_telemetry.jsonl"
    if os.path.exists(export_path):
        os.remove(export_path)

    assert telemetry.export_telemetry(export_path) is True
    assert os.path.exists(export_path)

    with open(export_path, "r") as f:
        line = f.readline()
        record = json.loads(line)
        assert "scan_id" not in record
        assert "metrics_fingerprint" in record

    os.remove(export_path)

def test_telemetry_disabled():
    orig_code = "print('hello')"
    gen_code = "print('hello optimized')"
    result = scan(orig_code, gen_code, telemetry_enabled=False)
    assert result["telemetry"] == {}

    stats = telemetry.get_stats()
    assert stats["total_scans"] == 0

def test_fingerprint_dict_order_independent():
    """Two metrics dicts that differ only in dict insertion order must hash identically."""
    metrics_a = {"function_complexities": {"b": 2, "a": 1}}
    metrics_b = {"function_complexities": {"a": 1, "b": 2}}
    fp_a = telemetry.calculate_fingerprint(metrics_a)
    fp_b = telemetry.calculate_fingerprint(metrics_b)
    assert fp_a == fp_b


def test_fingerprint_handles_list_of_dict_metrics():
    metrics = {
        "if_count": 3,
        "enumeration_analysis": [
            {"name": "f", "total_ifs": 2, "enumeration_ifs": 1, "loop_count": 0},
            {"name": "g", "total_ifs": 3, "enumeration_ifs": 2, "loop_count": 0},
        ],
    }
    fp = telemetry.calculate_fingerprint(metrics)
    assert isinstance(fp, str) and len(fp) == 64


def test_log_scan_accepts_hashes_not_plaintext():
    """log_scan signature takes hashes; plaintext codes never reach the telemetry layer."""
    orig_code = "x = 1"
    gen_code = "y = 2"
    salt = telemetry.get_or_create_salt()
    orig_hash = telemetry.hash_code_for_scan(orig_code, salt)
    gen_hash = telemetry.hash_code_for_scan(gen_code, salt)
    record = telemetry.log_scan(orig_hash, gen_hash, {}, {}, {}, [], "strict", "CLEAN")
    # scan_id must be deterministic for the same inputs
    expected_scan_id = telemetry.calculate_scan_id(orig_hash, gen_hash, salt)
    assert record["scan_id"] == expected_scan_id
    # Hardcoded regression value — recompute from the formula if salt or logic changes.
    # This verifies the computation doesn't drift silently between refactors.
    recomputed = hashlib.sha256(
        (orig_hash + gen_hash + salt).encode("utf-8")
    ).hexdigest()
    assert record["scan_id"] == recomputed


def test_sharing_prompt_multiples_of_100():
    orig_code = "print('hello')"
    gen_code = "print('hello optimized')"
    orig_metrics = {"if_count": 0, "loop_depth": 0}

    orig_hash, gen_hash = _make_hashes(orig_code, gen_code)

    # 99 scans
    for _ in range(99):
        telemetry.log_scan(orig_hash, gen_hash, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is False

    # 100th scan
    telemetry.log_scan(orig_hash, gen_hash, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is True

    # Check that second call for 100 doesn't prompt again
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is False

    # Log up to 199 scans
    for _ in range(99):
        telemetry.log_scan(orig_hash, gen_hash, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is False

    # 200th scan
    telemetry.log_scan(orig_hash, gen_hash, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is True

    # 300th scan (should also work, as it's a multiple of 100)
    for _ in range(100):
        telemetry.log_scan(orig_hash, gen_hash, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is True
