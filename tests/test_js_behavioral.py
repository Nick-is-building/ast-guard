"""
Tests for ast_guard.lang_javascript_behavioral.

Covers true-positive (TP) and true-negative (TN) cases for each signal.
No tree-sitter extras required — the module uses only the metrics dict and regex.
"""

import pytest
from ast_guard.lang_javascript_behavioral import score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metrics(**kwargs) -> dict:
    base = {"dangerous_calls": [], "call_list": [], "dangerous_imports": []}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Stage 3A signals
# ---------------------------------------------------------------------------

class TestEvalDynamic:
    def test_tp_eval_call(self):
        result = score("eval(userInput);", _metrics(dangerous_calls=["eval"], call_list=["eval"]))
        assert result["severity"] == "CRITICAL"
        assert any(f["pattern"] == "eval_dynamic" for f in result["findings"])

    def test_tp_function_constructor(self):
        result = score("const fn = Function('return 1')()", _metrics())
        assert any(f["pattern"] == "eval_dynamic" for f in result["findings"])
        assert result["severity"] == "CRITICAL"

    def test_tn_no_eval(self):
        result = score("const x = 1;\nconsole.log(x);\n", _metrics())
        assert not any(f["pattern"] == "eval_dynamic" for f in result["findings"])


class TestProcessTermination:
    def test_tp_process_exit(self):
        result = score("process.exit(0);", _metrics(call_list=["process.exit"]))
        assert result["severity"] == "CRITICAL"
        assert any(f["pattern"] == "process_termination" for f in result["findings"])

    def test_tn_no_process_exit(self):
        result = score("console.log('done');\n", _metrics(call_list=["console.log"]))
        assert not any(f["pattern"] == "process_termination" for f in result["findings"])


class TestSubprocessShell:
    def test_tp_exec_sync(self):
        result = score(
            "const { execSync } = require('child_process');\nexecSync('ls');",
            _metrics(dangerous_calls=["execSync"], call_list=["require", "execSync"],
                     dangerous_imports=["child_process"]),
        )
        assert any(f["pattern"] == "subprocess_shell" for f in result["findings"])

    def test_tp_spawn(self):
        result = score(
            "spawn('sh', ['-c', cmd]);",
            _metrics(dangerous_calls=["spawn"], call_list=["spawn"]),
        )
        assert any(f["pattern"] == "subprocess_shell" for f in result["findings"])

    def test_tn_console_log(self):
        result = score("console.log('hello');", _metrics(call_list=["console.log"]))
        assert not any(f["pattern"] == "subprocess_shell" for f in result["findings"])


class TestDangerousImport:
    def test_tp_child_process(self):
        result = score(
            "const cp = require('child_process');",
            _metrics(call_list=["require"], dangerous_imports=["child_process"]),
        )
        assert any(f["pattern"] == "dangerous_import" for f in result["findings"])

    def test_tn_safe_import(self):
        result = score(
            "const path = require('path');",
            _metrics(call_list=["require"]),
        )
        assert not any(f["pattern"] == "dangerous_import" for f in result["findings"])


# ---------------------------------------------------------------------------
# Stage 3B signals
# ---------------------------------------------------------------------------

class TestTestFileWrite:
    def test_tp_write_to_score_path(self):
        result = score(
            "fs.writeFileSync('/tmp/score_output.json', data);",
            _metrics(call_list=["fs.writeFileSync"], dangerous_imports=["fs"]),
        )
        assert any(f["pattern"] == "test_file_write" for f in result["findings"])

    def test_tn_no_fs_import(self):
        # Even if the path matches, no fs import → no finding.
        result = score(
            "console.log('/tmp/score_output.json');",
            _metrics(call_list=["console.log"]),
        )
        assert not any(f["pattern"] == "test_file_write" for f in result["findings"])

    def test_tn_fs_write_normal_path(self):
        result = score(
            "fs.writeFileSync('/tmp/output.json', data);",
            _metrics(call_list=["fs.writeFileSync"], dangerous_imports=["fs"]),
        )
        assert not any(f["pattern"] == "test_file_write" for f in result["findings"])


class TestEnvironMutation:
    def test_tp_process_env_mutation(self):
        result = score("process.env.SECRET = 'hacked';", _metrics())
        assert any(f["pattern"] == "environ_mutation" for f in result["findings"])

    def test_tp_lowercase_env_var(self):
        # env var names are matched case-insensitively in the regex
        result = score("process.env.DEBUG = '1';", _metrics())
        assert any(f["pattern"] == "environ_mutation" for f in result["findings"])

    def test_tn_reading_env(self):
        result = score("const val = process.env.HOME;", _metrics())
        assert not any(f["pattern"] == "environ_mutation" for f in result["findings"])


class TestModuleCacheManipulation:
    def test_tp_require_cache(self):
        result = score("delete require.cache[require.resolve('./mod')];", _metrics())
        assert result["severity"] == "CRITICAL"
        assert any(f["pattern"] == "module_cache_manipulation" for f in result["findings"])

    def test_tn_no_require_cache(self):
        result = score("const mod = require('./mod');\nmod.doStuff();\n", _metrics(call_list=["require"]))
        assert not any(f["pattern"] == "module_cache_manipulation" for f in result["findings"])


# ---------------------------------------------------------------------------
# Severity aggregation
# ---------------------------------------------------------------------------

class TestSeverityAggregation:
    def test_single_critical_dominates(self):
        # eval alone = +70 → CRITICAL
        result = score("eval(x);", _metrics(dangerous_calls=["eval"], call_list=["eval"]))
        assert result["severity"] == "CRITICAL"

    def test_multiple_moderate_accumulate(self):
        # subprocess_shell (+30) + dangerous_import (+30) = 60 → WARNING
        result = score(
            "const cp = require('child_process');\nexecSync('ls');",
            _metrics(dangerous_calls=["execSync"], call_list=["require", "execSync"],
                     dangerous_imports=["child_process"]),
        )
        assert result["severity"] == "WARNING"

    def test_clean_handler(self):
        code = (
            "function handleRequest(req, res) {\n"
            "    const name = req.params.name;\n"
            "    res.json({ greeting: 'Hello ' + name });\n"
            "}\n"
        )
        result = score(code, _metrics(call_list=["res.json"]))
        assert result["severity"] == "CLEAN"
        assert result["score"] == 0
