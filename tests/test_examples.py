"""Regression tests that pin each examples/ pair to its real ast-guard verdict.

These tests load the fixture files directly so that any future change to
examples/ or ast_guard/ that alters a verdict is caught immediately.
"""

import os
import pytest
from ast_guard import scan

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "examples")


def _load(name):
    orig = open(os.path.join(EXAMPLES_DIR, f"{name}_original.py")).read()
    gen = open(os.path.join(EXAMPLES_DIR, f"{name}_generated.py")).read()
    return orig, gen


def test_hardcoding_is_critical():
    orig, gen = _load("hardcoding")
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    assert result["verdict"] == "CRITICAL"
    assert result["checks"]["check_1_hardcoding"]["status"] == "WARNING"
    assert result["checks"]["check_5_extensional_enumeration"]["status"] == "WARNING"


def test_optimization_is_clean():
    orig, gen = _load("optimization")
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    assert result["verdict"] == "CLEAN"


def test_forbidden_calls_is_critical():
    orig, gen = _load("forbidden_calls")
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    assert result["verdict"] == "CRITICAL"
    assert result["checks"]["check_3_forbidden_calls"]["status"] == "CRITICAL"


def test_complexity_collapse_is_critical():
    orig, gen = _load("complexity_collapse")
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    assert result["verdict"] == "CRITICAL"
    assert result["checks"]["check_1_hardcoding"]["status"] == "WARNING"
    assert result["checks"]["check_5_extensional_enumeration"]["status"] == "WARNING"


def test_import_drift_is_critical():
    orig, gen = _load("import_drift")
    result = scan(orig, gen, mode="strict", telemetry_enabled=False)
    assert result["verdict"] == "CRITICAL"
    assert result["checks"]["check_4_import_drift"]["status"] == "CRITICAL"
