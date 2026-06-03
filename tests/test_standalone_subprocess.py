"""
Tests for standalone subprocess-import downgrade logic.

When every subprocess call in the file is structurally safe (literal list,
no shell=True), scan_standalone should suppress the subprocess import from
Check 4 silently.  If no other check fires the verdict must be CLEAN.
"""
import pytest
from ast_guard import scan_standalone


# --- safe patterns -----------------------------------------------------------

def test_safe_run_with_list():
    code = "import subprocess\nsubprocess.run(['ls', '-la'])\n"
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert result["checks"]["check_4_import_drift"]["status"] != "CRITICAL"


def test_no_calls_at_all():
    code = "import subprocess\n"
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert result["checks"]["check_4_import_drift"]["status"] != "CRITICAL"


def test_from_import_safe():
    code = "from subprocess import run\nrun(['echo', 'hi'])\n"
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert result["checks"]["check_4_import_drift"]["status"] != "CRITICAL"


def test_all_safe_functions():
    code = (
        "import subprocess\n"
        "subprocess.run(['ls'])\n"
        "subprocess.call(['echo', 'hi'])\n"
        "subprocess.check_call(['true'])\n"
        "subprocess.check_output(['date'])\n"
    )
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CLEAN", result
    assert result["checks"]["check_4_import_drift"]["status"] != "CRITICAL"


# --- unsafe patterns ---------------------------------------------------------

def test_shell_true_is_critical():
    code = "import subprocess\nsubprocess.run(['ls'], shell=True)\n"
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result


def test_variable_arg_is_critical():
    code = "import subprocess\ncmd_var = ['ls']\nsubprocess.run(cmd_var)\n"
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result


def test_mixed_safe_and_shell_true_is_critical():
    code = (
        "import subprocess\n"
        "subprocess.run(['ls'])\n"
        "subprocess.run(['rm', '-rf'], shell=True)\n"
    )
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result


def test_no_args_is_critical():
    # subprocess.run() with no positional args is not a recognisable safe call.
    code = "import subprocess\nsubprocess.run()\n"
    result = scan_standalone(code, mode="strict")
    assert result["verdict"] == "CRITICAL", result


# --- alias edge-case (conservative: keep CRITICAL) ---------------------------

def test_aliased_import_stays_critical():
    code = "import subprocess as sp\nsp.run(['ls'])\n"
    result = scan_standalone(code, mode="strict")
    # We cannot track calls through the alias, so the conservative path fires.
    assert result["verdict"] == "CRITICAL", result
