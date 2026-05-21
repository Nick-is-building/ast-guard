import pytest
import os
import subprocess
import json
import shutil
from ast_guard import scan

def test_integration_clean_transformation():
    orig_code = """
def process(data):
    res = []
    for x in data:
        res.append(x * 2)
    return res
"""
    # Optimized using list comprehension (legitimate)
    gen_code = """
def process(data):
    return [x * 2 for x in data]
"""
    result = scan(orig_code, gen_code, mode="strict")
    assert result["verdict"] == "CLEAN"
    assert len(result["transformations"]) > 0
    assert result["checks"]["check_2_complexity_collapse"]["status"] == "CLEAN"

def test_integration_hardcoding_and_complexity_collapse():
    # Original: high complexity but zero literals!
    orig_code_kombi = """
def check_values(lst):
    for x in lst:
        if x == lst:
            pass
        elif x == lst:
            pass
        elif x == lst:
            pass
        elif x == lst:
            pass
        elif x == lst:
            pass
        elif x == lst:
            pass
        elif x == lst:
            pass
        elif x == lst:
            pass
        elif x == lst:
            pass
"""
    # Generated: low complexity and introduces 15 new literals
    gen_code_kombi = """
def check_values(lst):
    table = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
"""
    result = scan(orig_code_kombi, gen_code_kombi, mode="strict")
    # Both check 1 (literals) and check 2 (collapse) should trigger, resulting in CRITICAL
    assert result["checks"]["check_1_hardcoding"]["status"] == "WARNING"
    assert result["checks"]["check_2_complexity_collapse"]["status"] == "WARNING"
    assert result["verdict"] == "CRITICAL"

def test_cli_execution_standard_vs_strict():
    orig_file = "/tmp/orig_test_cli.py"
    gen_file = "/tmp/gen_test_cli.py"
    
    with open(orig_file, "w") as f:
        f.write("x = 1\n")
    with open(gen_file, "w") as f:
        # Trigger Check 3 (critical)
        f.write("eval('1+1')\n")
        
    # Running standard mode: should output CRITICAL and exit 1
    cmd = ["python3", "-m", "ast_guard.cli", "check", orig_file, gen_file, "--mode", "standard"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1
    assert "Verdict: \033[91m\033[1mCRITICAL" in res.stdout or "CRITICAL" in res.stdout
    
    # Running audit mode: should exit 0 even if verdict is CRITICAL
    cmd_audit = ["python3", "-m", "ast_guard.cli", "check", orig_file, gen_file, "--mode", "audit"]
    res_audit = subprocess.run(cmd_audit, capture_output=True, text=True)
    assert res_audit.returncode == 0
    
    # Cleanup
    if os.path.exists(orig_file):
        os.remove(orig_file)
    if os.path.exists(gen_file):
        os.remove(gen_file)
