"""Tests for Stage 7 sim hook 3-layer verification logic.

Covers: empty log, PASS summary variants, FAIL detection, edge cases where
"fail" appears inside signal names or comments (should NOT trigger layer 2).
"""

import os
import tempfile


def write_log(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def sim_hook_check(log_path, vvp_path=None):
    """Python reimplementation of the 3-layer bash hook for testing.

    Returns (passed: bool, reason: str)
    """
    # Layer 0: compiled binary must exist
    if vvp_path is not None and not os.path.exists(vvp_path):
        return False, "FAIL — tb.vvp not found"

    # Layer 1: sim.log must exist and be non-empty
    if not os.path.exists(log_path):
        return False, "FAIL — sim.log missing"
    if os.path.getsize(log_path) == 0:
        return False, "FAIL — sim.log is empty"

    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Layer 2: count explicit test failures ([FAIL] or FAILED: prefix)
    import re
    fail_pattern = re.compile(r'^\s*\[FAIL\]|^FAILED:', re.MULTILINE)
    content = "".join(lines)
    fail_count = len(fail_pattern.findall(content))
    if fail_count > 0:
        return False, f"FAIL — {fail_count} test assertion(s) failed"

    # Layer 3: must find explicit PASS summary
    pass_pattern = re.compile(r'ALL TESTS PASSED|All tests passed|all tests passed', re.IGNORECASE)
    if pass_pattern.search(content):
        return True, "PASS"

    return False, "FAIL — no PASS summary found"


# ── Layer 1 tests ──────────────────────────────────────────────────────────

def test_missing_log():
    result, reason = sim_hook_check("/nonexistent/path/sim.log")
    assert result is False, "Missing log should fail"
    assert "missing" in reason

def test_empty_log():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        path = f.name
    try:
        result, reason = sim_hook_check(path)
        assert result is False, "Empty log should fail"
        assert "empty" in reason
    finally:
        os.unlink(path)

# ── Layer 2 tests ──────────────────────────────────────────────────────────

def test_explicit_fail_line():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as f:
        f.write("[FAIL] Test case 3: expected 0xFF got 0x00\nALL TESTS PASSED\n")
        path = f.name
    try:
        result, reason = sim_hook_check(path)
        assert result is False, "[FAIL] line should trigger layer 2"
        assert "assertion" in reason
    finally:
        os.unlink(path)

def test_failed_prefix_line():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as f:
        f.write("FAILED: 2 assertion(s) failed\nALL TESTS PASSED\n")
        path = f.name
    try:
        result, reason = sim_hook_check(path)
        assert result is False, "FAILED: prefix should trigger layer 2"
    finally:
        os.unlink(path)

def test_fail_in_signal_name_not_triggered():
    """'fail_flag' in signal name or comment must NOT trigger layer 2."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as f:
        f.write("// checking fail_flag behavior\n")
        f.write("signal fail_counter driven low\n")
        f.write("Testing FAIL scenario: signal name contains fail\n")
        f.write("ALL TESTS PASSED\n")
        path = f.name
    try:
        result, reason = sim_hook_check(path)
        assert result is True, f"'fail' in signal/comment should not trigger: {reason}"
    finally:
        os.unlink(path)

def test_fail_in_indented_comment_not_triggered():
    """Indented comment with 'fail' substring must NOT trigger."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as f:
        f.write("    // This tests failure recovery path\n")
        f.write("    checking: no-fail behavior\n")
        f.write("ALL TESTS PASSED\n")
        path = f.name
    try:
        result, reason = sim_hook_check(path)
        assert result is True, f"Comment with 'fail' substring should not trigger: {reason}"
    finally:
        os.unlink(path)

def test_fail_bracket_triggered():
    """[FAIL] even with leading spaces should trigger layer 2."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as f:
        f.write("    [FAIL] Expected 8'hAB, got 8'h00\n")
        f.write("ALL TESTS PASSED\n")
        path = f.name
    try:
        result, reason = sim_hook_check(path)
        assert result is False, "Indented [FAIL] should still trigger"
    finally:
        os.unlink(path)

# ── Layer 3 tests ──────────────────────────────────────────────────────────

def test_no_pass_summary():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as f:
        f.write("Test 1: OK\nTest 2: OK\n")
        path = f.name
    try:
        result, reason = sim_hook_check(path)
        assert result is False, "Missing PASS summary should fail"
        assert "PASS summary" in reason
    finally:
        os.unlink(path)

def test_pass_summary_variants():
    """All accepted PASS summary strings."""
    variants = [
        "ALL TESTS PASSED",
        "All tests passed",
        "all tests passed",
    ]
    for summary in variants:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as f:
            f.write(f"Test 1: OK\n{summary}\n")
            path = f.name
        try:
            result, reason = sim_hook_check(path)
            assert result is True, f"Summary '{summary}' should pass: {reason}"
        finally:
            os.unlink(path)

# ── Happy path ─────────────────────────────────────────────────────────────

def test_clean_pass():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as f:
        f.write("VCD info: dumpfile sim.vcd opened for output.\n")
        f.write("Test 1 [reset]: PASS\n")
        f.write("Test 2 [basic]: PASS\n")
        f.write("ALL TESTS PASSED\n")
        path = f.name
    try:
        result, reason = sim_hook_check(path)
        assert result is True, f"Clean log should pass: {reason}"
    finally:
        os.unlink(path)

def test_multiple_failures_counted():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as f:
        f.write("[FAIL] Test 1\n[FAIL] Test 2\n[FAIL] Test 3\n")
        path = f.name
    try:
        result, reason = sim_hook_check(path)
        assert result is False
        assert "3" in reason
    finally:
        os.unlink(path)


if __name__ == "__main__":
    tests = [
        test_missing_log,
        test_empty_log,
        test_explicit_fail_line,
        test_failed_prefix_line,
        test_fail_in_signal_name_not_triggered,
        test_fail_in_indented_comment_not_triggered,
        test_fail_bracket_triggered,
        test_no_pass_summary,
        test_pass_summary_variants,
        test_clean_pass,
        test_multiple_failures_counted,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} tests passed")
    if failed:
        raise SystemExit(1)
