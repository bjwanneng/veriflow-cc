"""Tests for iverilog_runner structured fail parsing and failure classifier."""

import sys
from pathlib import Path


_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-pipeline"
sys.path.insert(0, str(_SKILLS_DIR))

from iverilog_runner import _parse_fail_line, classify_failure  # noqa: E402


def test_parse_fail_line_structured():
    """Standard [FAIL] format with all 7 fields."""
    line = "[FAIL] test=hash_test vector=2 cycle=15 signal=data_out expected=0xABCD actual=0x1234 phase=negedge"
    result = _parse_fail_line(line)

    assert result["test"] == "hash_test"
    assert result["vector"] == 2
    assert result["cycle"] == 15
    assert result["signal"] == "data_out"
    assert result["expected"] == "0xABCD"
    assert result["actual"] == "0x1234"
    assert result["phase"] == "negedge"
    assert result["message"] == line


def test_parse_fail_line_legacy_fallback():
    """Legacy [FAIL] line without structured fields."""
    line = "[FAIL] Test 3: state expected IDLE got RUN"
    result = _parse_fail_line(line)

    assert result["test"] == "verilog_tb"
    assert result["message"] == line
    assert "vector" not in result
    assert "signal" not in result


def test_parse_fail_line_legacy_with_cycle():
    """Legacy [FAIL] line with cycle number."""
    line = "[FAIL] something went wrong cycle=5 error"
    result = _parse_fail_line(line)

    assert result["test"] == "verilog_tb"
    assert result["cycle"] == 5
    assert result["message"] == line


def test_classify_unknown_is_type_d():
    """x/z values indicate uninitialized register."""
    failures = [{
        "test": "t1", "signal": "data_out",
        "expected": "0xFF", "actual": "0xXXXX", "cycle": 10,
    }]
    result = classify_failure(failures)

    assert result[0]["classification"] == "D"
    assert "not initialized" in result[0]["reasoning"]


def test_classify_expected_zero_actual_nonzero_is_type_d():
    """Expected=0 but got non-zero indicates register not cleared."""
    failures = [{
        "test": "t1", "signal": "valid_out",
        "expected": "0x0", "actual": "0xFF", "cycle": 3,
    }]
    result = classify_failure(failures)

    assert result[0]["classification"] == "D"
    assert "not cleared" in result[0]["reasoning"]


def test_classify_timing_mismatch_is_type_b():
    """Value found at a different cycle in golden trace -> timing."""
    failures = [{
        "test": "t1", "signal": "hash_out",
        "expected": "0xABCD", "actual": "0x1234", "cycle": 5,
    }]
    golden = {
        3: {"hash_out": "0x1234"},
        4: {"hash_out": "0x5678"},
        5: {"hash_out": "0xABCD"},
    }
    result = classify_failure(failures, golden_cycles=golden)

    assert result[0]["classification"] == "B"
    assert "pipeline alignment" in result[0]["reasoning"]


def test_classify_computation_error_is_type_a():
    """No golden match and no init issue -> computation."""
    failures = [{
        "test": "t1", "signal": "hash_out",
        "expected": "0xABCD", "actual": "0x1234", "cycle": 5,
    }]
    result = classify_failure(failures, golden_cycles={})

    assert result[0]["classification"] == "A"
    assert "Computation" in result[0]["reasoning"]


def test_classify_no_golden_defaults_to_a():
    """Without golden trace, non-init failures default to Type A."""
    failures = [{
        "test": "t1", "signal": "data",
        "expected": "0x1", "actual": "0x2", "cycle": 3,
    }]
    result = classify_failure(failures)

    assert result[0]["classification"] == "A"
