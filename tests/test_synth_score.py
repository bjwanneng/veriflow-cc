"""Tests for synth_score.py — yosys stat parsing + quick synth."""

import shutil
import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from synth_score import parse_synth_report  # noqa: E402


# Realistic yosys `stat` tail (cell-type breakdown), shaped like real reports.
_SAMPLE = """
   8310 wires
  12517 wire bits
   476 public wires
  4587 public wire bits
    48 ports
   384 port bits
    - memories
    - memory bits
    - processes
  10158 cells
     66   $_ANDNOT_
   2370   $_AND_
   1024   $_DFFE_PP_
   1029   $_MUX_
   3451   $_NAND_
    200   $_SDFFE_PP0P_
    851   $_SDFF_PP0_
     5 submodules
"""


def test_parse_total_cells():
    r = parse_synth_report(_SAMPLE)
    assert r["cells"] == 10158


def test_parse_ff_count():
    # $_DFFE_PP_ (1024) + $_SDFFE_PP0P_ (200) + $_SDFF_PP0_ (851) = 2075
    r = parse_synth_report(_SAMPLE)
    assert r["ffs"] == 2075


def test_parse_mux_count():
    r = parse_synth_report(_SAMPLE)
    assert r["mux"] == 1029


def test_score_equals_cells():
    r = parse_synth_report(_SAMPLE)
    assert r["score"] == 10158


def test_parse_no_stats_is_zero():
    r = parse_synth_report("nothing useful here\n")
    assert r["cells"] == 0
    assert r["score"] == 0


def test_parse_number_of_cells_summary_form():
    # Some yosys builds print "Number of cells:" in the stats header.
    r = parse_synth_report("Number of cells: 42\n")
    assert r["cells"] == 42


def test_quick_synth_on_counter():
    """Integration: quick_synth the curated counter reference (skips w/o yosys)."""
    if shutil.which("yosys") is None:
        import pytest
        pytest.skip("yosys not installed")
    from synth_score import quick_synth
    import tempfile

    rtl = _SKILLS_DIR / "references" / "counter.v"
    with tempfile.TemporaryDirectory() as tmp:
        r = quick_synth(str(rtl), "counter", tmp)
    assert r.get("cells", 0) > 0, f"expected cells>0, got {r}"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except Exception as e:
                import traceback
                traceback.print_exc()
                raise
    print("All synth_score tests passed.")
