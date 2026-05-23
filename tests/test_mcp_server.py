"""Tests for ast-guard MCP server tools."""

import pytest

try:
    from ast_guard.mcp_server import ast_guard_scan, ast_guard_feedback
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


@pytest.mark.skipif(not MCP_AVAILABLE, reason="mcp package not installed")
class TestAstGuardMCPScan:
    """Tests for the ast_guard_scan MCP tool."""

    def test_clean_code_returns_clean(self):
        original = "def add(a, b):\n    return a + b\n"
        generated = "def add(a, b):\n    return a + b\n"
        result = ast_guard_scan(original, generated)
        assert result["verdict"] == "CLEAN"

    def test_hardcoding_detected(self):
        original = "def fib(n):\n    if n <= 1:\n        return n\n    return fib(n-1) + fib(n-2)\n"
        generated = (
            "def fib(n):\n"
            "    if n == 0: return 0\n"
            "    if n == 1: return 1\n"
            "    if n == 2: return 1\n"
            "    if n == 3: return 2\n"
            "    if n == 4: return 3\n"
            "    if n == 5: return 5\n"
            "    if n == 6: return 8\n"
            "    if n == 7: return 13\n"
            "    if n == 8: return 21\n"
            "    if n == 9: return 34\n"
            "    if n == 10: return 55\n"
            "    return fib(n-1) + fib(n-2)\n"
        )
        result = ast_guard_scan(original, generated)
        assert result["verdict"] in ("WARNING", "CRITICAL")

    def test_forbidden_call_detected(self):
        original = "def process(data):\n    return sorted(data)\n"
        generated = "def process(data):\n    exec('import os; os.system(\"rm -rf /\")')\n    return sorted(data)\n"
        result = ast_guard_scan(original, generated)
        assert result["verdict"] == "CRITICAL"

    def test_invalid_mode_returns_error(self):
        result = ast_guard_scan("x = 1", "x = 1", mode="invalid")
        assert "error" in result

    def test_all_modes_accepted(self):
        code = "x = 1\n"
        for mode in ("strict", "standard", "audit"):
            result = ast_guard_scan(code, code, mode=mode)
            assert result["verdict"] == "CLEAN"

    def test_result_contains_expected_keys(self):
        result = ast_guard_scan("x = 1\n", "x = 1\n")
        assert "verdict" in result
        assert "checks" in result


@pytest.mark.skipif(not MCP_AVAILABLE, reason="mcp package not installed")
class TestAstGuardMCPFeedback:
    """Tests for the ast_guard_feedback MCP tool."""

    def test_invalid_label_returns_error(self):
        result = ast_guard_feedback("some-scan-id", "invalid_label")
        assert "error" in result

    def test_valid_labels_accepted(self):
        for label in ("true_positive", "false_positive", "true_negative", "false_negative"):
            result = ast_guard_feedback("test-scan-id", label)
            assert "error" in result or result.get("status") == "ok"
