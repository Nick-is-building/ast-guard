"""
Tests for destructive OS/shutil call detection in standalone mode (Check 6)
and __import__ detection via standalone Check 3.
"""
import pytest
from ast_guard import scan_standalone


# ---------------------------------------------------------------------------
# CRITICAL tier: arbitrary command execution / process kill (+70)
# ---------------------------------------------------------------------------

def test_os_system_is_critical():
    code = 'import os\nos.system("cmd")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result
    assert result["confidence"] >= 70


def test_os_popen_is_critical():
    code = 'import os\nos.popen("cmd")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result
    assert result["confidence"] >= 70


def test_os_kill_is_critical():
    code = "import os\nos.kill(1, 9)\n"
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result
    assert result["confidence"] >= 70


# ---------------------------------------------------------------------------
# HIGH tier: destructive filesystem operations (+50)
# ---------------------------------------------------------------------------

def test_os_remove_is_flagged():
    code = 'import os\nos.remove("/f")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] in ("WARNING", "CRITICAL"), result
    assert result["confidence"] >= 50


def test_shutil_rmtree_is_flagged():
    code = 'import shutil\nshutil.rmtree("/d")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] in ("WARNING", "CRITICAL"), result
    assert result["confidence"] >= 50


def test_os_chmod_is_flagged():
    code = 'import os\nos.chmod("/f", 0o777)\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] in ("WARNING", "CRITICAL"), result
    assert result["confidence"] >= 50


# ---------------------------------------------------------------------------
# Excluded calls: non-destructive, must stay CLEAN
# ---------------------------------------------------------------------------

def test_os_makedirs_is_clean():
    code = 'import os\nos.makedirs("/d")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result


def test_shutil_copy_is_clean():
    code = 'import shutil\nshutil.copy("a", "b")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result


# ---------------------------------------------------------------------------
# __import__ bypass — Check 3
# ---------------------------------------------------------------------------

def test_dunder_import_is_critical():
    code = '__import__("os")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result
    c3 = result["checks"]["check_3_forbidden_calls"]
    assert c3["status"] == "CRITICAL", c3


# ---------------------------------------------------------------------------
# Mixed: safe call alongside dangerous call
# ---------------------------------------------------------------------------

def test_safe_and_dangerous_together():
    code = (
        "import os\n"
        "p = os.path.join('/tmp', 'out')\n"
        "os.remove(p)\n"
    )
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] in ("WARNING", "CRITICAL"), result
    c6 = result["checks"]["check_6_behavioral"]
    findings = c6.get("findings", [])
    desctructive_flagged = any("destructive" in f["explanation"].lower() or "os.remove" in f["explanation"] for f in findings)
    assert desctructive_flagged, findings
