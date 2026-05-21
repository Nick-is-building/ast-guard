import pytest
import os
import json
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
    id1 = telemetry.calculate_scan_id("code1", "code2", salt)
    id2 = telemetry.calculate_scan_id("code1", "code2", salt)
    id3 = telemetry.calculate_scan_id("code1", "code3", salt)
    
    assert id1 == id2
    assert id1 != id3

def test_fingerprint_deterministic():
    metrics = {"if_count": 2, "loop_depth": 1, "call_list": ["os.system"]}
    fp1 = telemetry.calculate_fingerprint("import os\nos.system()", metrics)
    fp2 = telemetry.calculate_fingerprint("import os\nos.system()", metrics)
    assert fp1 == fp2

def test_log_scan_and_stats():
    orig_code = "print('hello')"
    gen_code = "print('hello optimized')"
    orig_metrics = {"if_count": 0, "loop_depth": 0, "literal_count": 1}
    gen_metrics = {"if_count": 0, "loop_depth": 0, "literal_count": 1}
    check_results = {"check_1_hardcoding": {"status": "CLEAN"}}
    transformations = [{"category": "Loop-zu-Comprehension"}]
    
    record = telemetry.log_scan(
        orig_code, gen_code, orig_metrics, gen_metrics, check_results, transformations, "strict", "CLEAN"
    )
    
    assert "scan_id" in record
    assert "metrics_fingerprint" in record
    assert record["verdict"] == "CLEAN"
    
    stats = telemetry.get_stats()
    assert stats["total_scans"] == 1
    assert stats["verdicts"]["CLEAN"] == 1
    assert stats["transformations"]["Loop-zu-Comprehension"] == 1

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
    telemetry.log_scan(orig_code, gen_code, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    
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

def test_sharing_prompt_multiples_of_100():
    orig_code = "print('hello')"
    gen_code = "print('hello optimized')"
    orig_metrics = {"if_count": 0, "loop_depth": 0}
    
    # 99 scans
    for _ in range(99):
        telemetry.log_scan(orig_code, gen_code, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is False
    
    # 100th scan
    telemetry.log_scan(orig_code, gen_code, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is True
    
    # Check that second call for 100 doesn't prompt again
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is False
    
    # Log up to 199 scans
    for _ in range(99):
        telemetry.log_scan(orig_code, gen_code, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is False
    
    # 200th scan
    telemetry.log_scan(orig_code, gen_code, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is True

    # 300th scan (should also work, as it's a multiple of 100)
    for _ in range(100):
        telemetry.log_scan(orig_code, gen_code, orig_metrics, orig_metrics, {}, [], "strict", "CLEAN")
    should_prompt, _ = telemetry.check_sharing_prompt()
    assert should_prompt is True
