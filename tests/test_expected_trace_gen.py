"""Tests for expected_trace_gen.py — markdown trace generation from golden_model.py."""

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
_SCRIPT = _SKILLS_DIR / "analysis" / "expected_trace_gen.py"


def _write_golden(tmp: Path, body: str) -> Path:
    """Write a synthetic golden_model.py and return its path."""
    p = tmp / "golden_model.py"
    p.write_text(textwrap.dedent(body))
    return p


def test_compute_interface():
    """Interface 1: gm.compute(inputs, trace=True) + TEST_VECTORS."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_golden(tmp, """
            TEST_VECTORS = [{"inputs": {"x": 1}}]
            def compute(inputs, trace=False):
                return [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        """)
        out = tmp / "trace.md"
        result = subprocess.run(
            [sys.executable, str(_SCRIPT),
             "--golden", str(tmp / "golden_model.py"),
             "--cycles", "8",
             "--output", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert out.exists()
        content = out.read_text()
        assert "## Golden Model Expected Trace" in content
        assert "| 0 | a=1 b=2 |" in content
        assert "| 1 | a=3 b=4 |" in content


def test_run_interface():
    """Interface 2: gm.run(index) -> list of dicts."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_golden(tmp, """
            def run(idx=0):
                return [{"sig": 42}]
        """)
        out = tmp / "trace.md"
        result = subprocess.run(
            [sys.executable, str(_SCRIPT),
             "--golden", str(tmp / "golden_model.py"),
             "--cycles", "4",
             "--output", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "| 0 | sig=0x2a |" in out.read_text()


def test_cycle_cap():
    """Generator respects --cycles cap even when trace is longer."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_golden(tmp, """
            def run(idx=0):
                return [{"x": i} for i in range(100)]
        """)
        out = tmp / "trace.md"
        subprocess.run(
            [sys.executable, str(_SCRIPT),
             "--golden", str(tmp / "golden_model.py"),
             "--cycles", "3",
             "--output", str(out)],
            check=True, capture_output=True, text=True,
        )
        rows = [l for l in out.read_text().splitlines() if l.startswith("| ")]
        # 1 column-header row + 3 data rows (the `|---:|---|` separator
        # has no space after the `|`, so it doesn't match).
        assert len(rows) == 4


def test_unrecognized_interface_exits_cleanly():
    """Golden with neither compute, run, nor simulate should not crash."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_golden(tmp, "# empty module")
        out = tmp / "trace.md"
        result = subprocess.run(
            [sys.executable, str(_SCRIPT),
             "--golden", str(tmp / "golden_model.py"),
             "--cycles", "4",
             "--output", str(out)],
            capture_output=True, text=True,
        )
        # Should exit cleanly with a warning, not raise
        assert result.returncode == 0
        assert not out.exists()
        assert "could not generate" in result.stdout.lower()


def test_markdown_escapes_pipes():
    """Pipe characters in values must not break the markdown table."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_golden(tmp, """
            def run(idx=0):
                return [{"note": "a|b"}]
        """)
        out = tmp / "trace.md"
        subprocess.run(
            [sys.executable, str(_SCRIPT),
             "--golden", str(tmp / "golden_model.py"),
             "--cycles", "1",
             "--output", str(out)],
            check=True, capture_output=True, text=True,
        )
        # The pipe in "a|b" should be escaped as "a\|b"
        assert "a\\|b" in out.read_text()


def test_strip_reg_suffix_matches_vcd2table_convention():
    """_reg stripping must match vcd2table._strip_reg: strip single-_ register
    suffixes but preserve double-underscore names like 'state__reg'.

    Regression: expected_trace_gen stripped unconditionally, so 'state__reg'
    became 'state_' while vcd2table kept it — the same signal resolved
    differently between the two tools.
    """
    sys.path.insert(0, str(_SKILLS_DIR))
    from expected_trace_gen import _strip_reg_suffix  # noqa: E402

    assert _strip_reg_suffix("foo_reg") == "foo"
    assert _strip_reg_suffix("foo__reg") == "foo__reg"  # preserved, not mangled
    assert _strip_reg_suffix("data_out") == "data_out"
    assert _strip_reg_suffix("config") == "config"


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
