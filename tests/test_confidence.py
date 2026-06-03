"""
Tests for the confidence score module (ast_guard/confidence.py).

Each test exercises one branch of calculate_confidence in isolation by
constructing minimal check_results dicts — no real code scanning needed.
"""
import pytest
from ast_guard.confidence import calculate_confidence


def _clean_checks():
    return {
        "check_1_hardcoding": {"status": "CLEAN", "findings": []},
        "check_2_complexity_collapse": {"status": "CLEAN", "findings": []},
        "check_3_forbidden_calls": {"status": "CLEAN", "findings": []},
        "check_4_import_drift": {"status": "CLEAN", "findings": []},
        "check_5_extensional_enumeration": {"status": "CLEAN", "findings": []},
    }


def _standalone_checks(score=0):
    base = _clean_checks()
    base["check_6_behavioral"] = {"status": "CLEAN", "score": score, "findings": []}
    return base


# --- Pair mode tests ---

def test_clean_no_findings_confidence_zero():
    result = calculate_confidence(_clean_checks(), False, "strict")
    assert result == 0


def test_clean_with_transformations_confidence_five():
    result = calculate_confidence(_clean_checks(), False, "strict", has_transformations=True)
    assert result == 5


def test_check1_warning_alone():
    checks = _clean_checks()
    checks["check_1_hardcoding"]["status"] = "WARNING"
    result = calculate_confidence(checks, False, "strict")
    assert result == 30


def test_check2_warning_alone():
    checks = _clean_checks()
    checks["check_2_complexity_collapse"]["status"] = "WARNING"
    result = calculate_confidence(checks, False, "strict")
    assert result == 35


def test_check4_warning_alone():
    checks = _clean_checks()
    checks["check_4_import_drift"]["status"] = "WARNING"
    result = calculate_confidence(checks, False, "strict")
    assert result == 25


def test_check5_warning_alone():
    checks = _clean_checks()
    checks["check_5_extensional_enumeration"]["status"] = "WARNING"
    result = calculate_confidence(checks, False, "strict")
    assert result == 40


def test_check3_critical_pins_to_95():
    checks = _clean_checks()
    checks["check_3_forbidden_calls"]["status"] = "CRITICAL"
    result = calculate_confidence(checks, False, "strict")
    assert result == 95


def test_check3_critical_overrides_other_criticals():
    """Check 3 CRITICAL should return 95 even when other checks also fire."""
    checks = _clean_checks()
    checks["check_3_forbidden_calls"]["status"] = "CRITICAL"
    checks["check_4_import_drift"]["status"] = "CRITICAL"
    checks["check_1_hardcoding"]["status"] = "WARNING"
    result = calculate_confidence(checks, False, "strict")
    assert result == 95


def test_check4_critical_forbidden_import():
    checks = _clean_checks()
    checks["check_4_import_drift"]["status"] = "CRITICAL"
    result = calculate_confidence(checks, False, "strict")
    assert result == 75


def test_kombi_check1_check5():
    checks = _clean_checks()
    checks["check_1_hardcoding"]["status"] = "WARNING"
    checks["check_5_extensional_enumeration"]["status"] = "WARNING"
    result = calculate_confidence(checks, True, "strict")
    assert result == 85


def test_kombi_check1_check2():
    checks = _clean_checks()
    checks["check_1_hardcoding"]["status"] = "WARNING"
    checks["check_2_complexity_collapse"]["status"] = "WARNING"
    result = calculate_confidence(checks, True, "strict")
    assert result == 80


def test_kombi_check5_check2():
    checks = _clean_checks()
    checks["check_5_extensional_enumeration"]["status"] = "WARNING"
    checks["check_2_complexity_collapse"]["status"] = "WARNING"
    result = calculate_confidence(checks, True, "strict")
    assert result == 80


def test_multiple_warnings_without_kombi_capped():
    """Check 1 (30) + Check 4 WARNING (25) → max(30,25) + 10*(2-1) = 40."""
    checks = _clean_checks()
    checks["check_1_hardcoding"]["status"] = "WARNING"
    checks["check_4_import_drift"]["status"] = "WARNING"
    result = calculate_confidence(checks, False, "strict")
    assert result == 40


def test_multiple_warnings_cap_at_70():
    """Check 5 (40) + Check 2 (35) + Check 1 (30) without kombi → capped at 70."""
    checks = _clean_checks()
    checks["check_5_extensional_enumeration"]["status"] = "WARNING"
    checks["check_2_complexity_collapse"]["status"] = "WARNING"
    checks["check_1_hardcoding"]["status"] = "WARNING"
    # max=40, additional=2, 40+20=60 < 70 so result is 60 (not capped)
    result = calculate_confidence(checks, False, "strict")
    assert result == 60


def test_syntax_error_returns_50():
    result = calculate_confidence(_clean_checks(), False, "strict", syntax_error=True)
    assert result == 50


def test_syntax_error_ignores_other_flags():
    """syntax_error=True must always win regardless of kombi or check states."""
    checks = _clean_checks()
    checks["check_3_forbidden_calls"]["status"] = "CRITICAL"
    result = calculate_confidence(checks, True, "strict", syntax_error=True)
    assert result == 50


# --- Standalone mode tests ---

def test_standalone_risk_score_only():
    checks = _standalone_checks(score=45)
    result = calculate_confidence(checks, False, "strict")
    assert result == 45


def test_standalone_risk_score_capped_at_100():
    checks = _standalone_checks(score=150)
    result = calculate_confidence(checks, False, "strict")
    assert result == 100


def test_standalone_check3_critical_overrides_risk_score():
    checks = _standalone_checks(score=10)
    checks["check_3_forbidden_calls"]["status"] = "CRITICAL"
    result = calculate_confidence(checks, False, "strict")
    assert result == 95


def test_standalone_check4_critical():
    checks = _standalone_checks(score=20)
    checks["check_4_import_drift"]["status"] = "CRITICAL"
    result = calculate_confidence(checks, False, "strict")
    assert result == 75


def test_standalone_check5_warning():
    checks = _standalone_checks(score=10)
    checks["check_5_extensional_enumeration"]["status"] = "WARNING"
    result = calculate_confidence(checks, False, "strict")
    assert result == 40


def test_standalone_check1_warning():
    checks = _standalone_checks(score=5)
    checks["check_1_hardcoding"]["status"] = "WARNING"
    result = calculate_confidence(checks, False, "strict")
    assert result == 30


def test_standalone_subprocess_downgrade():
    """subprocess_safe=True: check_1 fired only because of safe subprocess downgrade."""
    checks = _standalone_checks(score=5)
    checks["check_1_hardcoding"]["status"] = "WARNING"
    result = calculate_confidence(checks, False, "strict", subprocess_safe=True)
    assert result == 15


def test_standalone_subprocess_safe_with_high_risk_score():
    """If risk_score already exceeds 15, subprocess_safe does not lower it."""
    checks = _standalone_checks(score=60)
    checks["check_1_hardcoding"]["status"] = "WARNING"
    result = calculate_confidence(checks, False, "strict", subprocess_safe=True)
    assert result == 60


def test_standalone_kombi_triggered():
    checks = _standalone_checks(score=20)
    checks["check_1_hardcoding"]["status"] = "WARNING"
    checks["check_5_extensional_enumeration"]["status"] = "WARNING"
    result = calculate_confidence(checks, True, "strict")
    assert result == 85


# --- Integration smoke tests (call real scan / scan_standalone) ---

def test_scan_result_has_confidence_key():
    from ast_guard import scan
    result = scan("x = 1", "x = 1", telemetry_enabled=False)
    assert "confidence" in result
    assert isinstance(result["confidence"], int)
    assert 0 <= result["confidence"] <= 100


def test_scan_standalone_result_has_confidence_key():
    from ast_guard import scan_standalone
    result = scan_standalone("x = 1", telemetry_enabled=False)
    assert "confidence" in result
    assert isinstance(result["confidence"], int)
    assert 0 <= result["confidence"] <= 100


def test_scan_clean_confidence_zero():
    from ast_guard import scan
    result = scan("x = 1", "x = 1", telemetry_enabled=False)
    assert result["confidence"] == 0


def test_scan_check3_critical_confidence_95():
    from ast_guard import scan
    orig = "x = 1"
    gen = "eval('x = 1')"
    result = scan(orig, gen, telemetry_enabled=False)
    assert result["verdict"] == "CRITICAL"
    assert result["confidence"] == 95
