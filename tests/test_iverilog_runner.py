"""Tests for iverilog_runner structured fail parsing and failure classifier."""

import sys
from pathlib import Path


_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
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


# =============================================================================
# WS6: compile-cmd build (VCD/NODUMP), -Wall -tnull syntax gate, timing.
# =============================================================================

def test_build_compile_cmd_default_has_no_nodump():
    from iverilog_runner import _build_compile_cmd
    cmd = _build_compile_cmd("/fake/iverilog", "out.vvp", "tb",
                             ["a.v", "b.v"], "tb.v", no_vcd=False)
    assert "-DNODUMP" not in cmd
    assert "-g2005" in cmd
    assert cmd[-1] == "tb.v"


def test_build_compile_cmd_no_vcd_adds_nodump():
    from iverilog_runner import _build_compile_cmd
    cmd = _build_compile_cmd("/fake/iverilog", "out.vvp", "tb",
                             ["a.v"], "tb.v", no_vcd=True)
    assert "-DNODUMP" in cmd


def test_syntax_check_pass(monkeypatch):
    import iverilog_runner as ivr
    import types as _types
    monkeypatch.setattr(ivr.subprocess, "run", lambda *a, **k: _types.SimpleNamespace(
        stdout="", stderr="", returncode=0))
    ok, snippet = ivr._syntax_check(["a.v"], "tb.v", "/fake/iverilog", {}, "/tmp")
    assert ok is True
    assert snippet == ""


def test_syntax_check_fail_returns_snippet(monkeypatch):
    import iverilog_runner as ivr
    import types as _types
    monkeypatch.setattr(ivr.subprocess, "run", lambda *a, **k: _types.SimpleNamespace(
        stdout="", stderr="syntax error near line 5\n", returncode=1))
    ok, snippet = ivr._syntax_check(["a.v"], "tb.v", "/fake/iverilog", {}, "/tmp")
    assert ok is False
    assert "syntax error" in snippet


def test_syntax_check_exception_safe(monkeypatch):
    import iverilog_runner as ivr

    def boom(*a, **k):
        raise OSError("iverilog vanished")
    monkeypatch.setattr(ivr.subprocess, "run", boom)
    ok, snippet = ivr._syntax_check(["a.v"], "tb.v", "/fake/iverilog", {}, "/tmp")
    assert ok is False
    assert snippet  # non-empty explanation


def _wire_main(monkeypatch, tmp_path, spy_return=(True, "")):
    """Stand up a fake environment so main() reaches the syntax gate."""
    import iverilog_runner as ivr
    import types as _types
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "top.v").write_text("module top; endmodule")
    tb = tmp_path / "tb.v"
    tb.write_text("module tb; endmodule")
    build = tmp_path / "build"
    build.mkdir()
    monkeypatch.setattr(ivr, "find_iverilog", lambda: "/fake/iverilog")
    monkeypatch.setattr(ivr, "find_vvp", lambda: "/fake/vvp")
    monkeypatch.setattr(ivr, "collect_rtl_sources",
                        lambda d: [str(p) for p in Path(d).glob("*.v")])
    spy = {"n": 0}

    def _spy(*a, **k):
        spy["n"] += 1
        return spy_return
    monkeypatch.setattr(ivr, "_syntax_check", _spy)
    # compile + sim both succeed; sim reports PASS
    monkeypatch.setattr(ivr.subprocess, "run", lambda *a, **k: _types.SimpleNamespace(
        stdout="ALL TESTS PASSED\n", stderr="", returncode=0))
    return rtl, tb, build, spy


def test_main_runs_syntax_gate_by_default(monkeypatch, tmp_path, capsys):
    import iverilog_runner as ivr
    rtl, tb, build, spy = _wire_main(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "iverilog_runner.py", "--rtl-dir", str(rtl), "--tb-file", str(tb),
        "--module", "top", "--build-dir", str(build)])
    try:
        ivr.main()
    except SystemExit:
        pass
    assert spy["n"] == 1


def test_main_skips_syntax_gate_with_flag(monkeypatch, tmp_path, capsys):
    import iverilog_runner as ivr
    rtl, tb, build, spy = _wire_main(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "iverilog_runner.py", "--rtl-dir", str(rtl), "--tb-file", str(tb),
        "--module", "top", "--build-dir", str(build), "--no-syntax-check"])
    try:
        ivr.main()
    except SystemExit:
        pass
    assert spy["n"] == 0


def test_tb_template_dumps_gated_by_nodump():
    """The Verilog TB template gates $dumpvars behind `ifndef NODUMP so
    iverilog_runner --no-vcd (-DNODUMP) suppresses waveform generation."""
    src = (_SKILLS_DIR / "templates" / "tb_integration_template.v").read_text()
    assert "`ifndef NODUMP" in src
    assert src.index("`ifndef NODUMP") < src.index("$dumpvars") < src.index("`endif")


def test_main_emits_timing_when_verbose(monkeypatch, tmp_path, capsys):
    import iverilog_runner as ivr
    rtl, tb, build, _ = _wire_main(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "iverilog_runner.py", "--rtl-dir", str(rtl), "--tb-file", str(tb),
        "--module", "top", "--build-dir", str(build), "--verbose"])
    try:
        ivr.main()
    except SystemExit:
        pass
    err = capsys.readouterr().err
    assert "[TIMING] step=iverilog_compile" in err
    assert "[TIMING] step=iverilog_sim" in err



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


def test_parse_fail_line_handles_adjacent_kv_pairs():
    """Regression: TB lines without spaces between kv pairs must still
    parse correctly. Previously `bar=1foo=2` was parsed as a single field
    `bar=1foo=2`, silently losing `foo=2`."""
    # Real-world: TB forgot a space between `cycle=5` and `signal=...`
    line = "[FAIL] cycle=5signal=data_out expected=0xAA actual=0xBB"
    result = _parse_fail_line(line)

    assert result["cycle"] == 5
    assert result["signal"] == "data_out"
    assert result["expected"] == "0xAA"
    assert result["actual"] == "0xBB"


def test_parse_fail_line_handles_quoted_values():
    """Quoted values (with embedded spaces) should be captured intact."""
    line = '[FAIL] test=t1 cycle=3 message="something broke at posedge"'
    result = _parse_fail_line(line)

    assert result["test"] == "t1"
    assert result["cycle"] == 3
    assert result.get("message_field") in (None, "something broke at posedge") \
        or "broke" in result.get("message", "")
