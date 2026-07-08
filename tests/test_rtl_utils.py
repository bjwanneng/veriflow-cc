"""Tests for rtl_utils.py — shared RTL pipeline utilities."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from rtl_utils import find_executable, collect_rtl_sources


# ── find_executable ──────────────────────────────────────────────────


def test_find_executable_known_binary():
    """Should find 'python3' or 'python' on any system."""
    result = find_executable(["python3", "python"])
    assert result, "Expected to find python3 or python on PATH"
    assert "python" in result.lower()


def test_find_executable_nonexistent():
    """Should return empty string for a binary that does not exist."""
    result = find_executable(["no_such_binary_xyz_12345"])
    assert result == ""


def test_find_executable_eda_bin_fallback(tmp_path):
    """Should find binary in EDA_BIN directory."""
    import os
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "mytool").write_text("#!/bin/sh\necho ok\n")
    (fake_bin / "mytool").chmod(0o755)
    old = os.environ.get("EDA_BIN", "")
    try:
        os.environ["EDA_BIN"] = str(fake_bin)
        # shutil.which may not find it since it's not on PATH,
        # but find_executable checks EDA_BIN first
        result = find_executable(["mytool"])
        assert str(fake_bin) in result
    finally:
        if old:
            os.environ["EDA_BIN"] = old
        else:
            os.environ.pop("EDA_BIN", None)


# ── collect_rtl_sources ──────────────────────────────────────────────


def test_collect_rtl_sources_finds_verilog(tmp_path):
    """Should find .v files in the given directory."""
    rtl_dir = tmp_path / "rtl"
    rtl_dir.mkdir()
    (rtl_dir / "top.v").write_text("module top; endmodule")
    (rtl_dir / "sub.v").write_text("module sub; endmodule")
    sources = collect_rtl_sources(rtl_dir)
    assert len(sources) == 2
    assert any("top.v" in s for s in sources)
    assert any("sub.v" in s for s in sources)


def test_collect_rtl_sources_empty_dir_exits(tmp_path):
    """Should exit with code 2 if no .v files found."""
    rtl_dir = tmp_path / "rtl"
    rtl_dir.mkdir()
    result = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, '{_SKILLS_DIR}/core'); "
         f"from rtl_utils import collect_rtl_sources; "
         f"from pathlib import Path; "
         f"collect_rtl_sources(Path('{rtl_dir}'))"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "No .v files" in result.stdout


# ── _get_arg empty value ─────────────────────────────────────────────


def test_state_get_arg_empty_value_returns_none():
    """--flag= should return empty string, not None."""
    from state import _get_arg
    result = _get_arg(["--hook="], "hook")
    # After fix, empty value after = should be treated as empty string
    # (the old behavior returned "" which is fine, but we verify it's not None)
    assert result == ""


def test_state_get_arg_with_value():
    """--flag=value should return value."""
    from state import _get_arg
    assert _get_arg(["--hook=test -f foo"], "hook") == "test -f foo"


def test_state_get_arg_separate_value():
    """--flag value should return value."""
    from state import _get_arg
    assert _get_arg(["--hook", "test -f foo"], "hook") == "test -f foo"


# ── VCD parser max time steps ────────────────────────────────────────


def test_vcd_parser_max_time_steps():
    """VCD parser should reject files exceeding max_time_steps."""
    from vcd2table import VCDParser
    import io

    # Generate a VCD with many time steps
    lines = [
        "$timescale 1ns $end",
        "$scope module top $end",
        "$var wire 1 ! clk $end",
        "$upscope $end",
        "$enddefinitions $end",
    ]
    # 10 time steps
    for i in range(10):
        lines.append(f"#{i * 10}")
        lines.append("1!")

    vcd_content = "\n".join(lines) + "\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".vcd", delete=False) as f:
        f.write(vcd_content)
        f.flush()
        vcd_path = f.name

    try:
        # Should work with default limit
        parser = VCDParser(max_time_steps=100)
        parser.parse(vcd_path)
        assert len(parser.changes) > 0

        # Should raise with very low limit
        import pytest
        parser2 = VCDParser(max_time_steps=5)
        with pytest.raises(ValueError, match="too many time steps"):
            parser2.parse(vcd_path)
    finally:
        Path(vcd_path).unlink()


# ── DIVERGENCE_SEARCH_WINDOW shared constant ─────────────────────────


def test_divergence_search_window_is_single_source_of_truth():
    """Regression for I6: WINDOW used to live in timing_diagnostic and was
    imported via try/except by iverilog_runner. Both must now read the same
    constant from rtl_utils so they cannot drift apart."""
    import rtl_utils
    import timing_diagnostic
    import iverilog_runner

    assert hasattr(rtl_utils, "DIVERGENCE_SEARCH_WINDOW")
    assert rtl_utils.DIVERGENCE_SEARCH_WINDOW == timing_diagnostic.WINDOW
    assert rtl_utils.DIVERGENCE_SEARCH_WINDOW == iverilog_runner._DIVERGENCE_SEARCH_WINDOW


if __name__ == "__main__":
    import traceback
    passed = 0
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {name}: {e}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
