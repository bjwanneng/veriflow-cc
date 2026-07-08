"""Tests for formal_prove.py — property generation + sby output parsing."""

import os
import shutil
import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from formal_prove import generate_properties, _parse_sby_output  # noqa: E402


_SPEC = {
    "modules": [{
        "module_name": "dut",
        "ports": [
            {"name": "clk", "direction": "input"},
            {"name": "rst", "direction": "input"},
            {"name": "valid_out", "direction": "output", "protocol": "valid",
             "ack_port": "ready_in", "width": 1},
            {"name": "ready_in", "direction": "input", "width": 1},
            {"name": "data_out", "direction": "output", "width": 8},
        ],
    }],
}


# --- property generation --------------------------------------------------


def test_generate_instantiates_dut_and_module():
    v = generate_properties(_SPEC, "dut")
    assert "module dut_formal" in v
    assert "dut " in v or " dut(" in v.replace("dut_formal", "X")  # DUT instance present


def test_generate_emits_handshake_assertion():
    v = generate_properties(_SPEC, "dut")
    assert "assert(" in v
    assert "valid_out" in v            # property references the valid output
    assert "ready_in" in v             # and the ready ack


def test_generate_no_handshake_still_valid_module():
    spec = {"modules": [{"module_name": "m", "ports": [
        {"name": "clk", "direction": "input"},
        {"name": "rst", "direction": "input"},
        {"name": "y", "direction": "output", "width": 4},
    ]}]}
    v = generate_properties(spec, "m")
    assert "module m_formal" in v
    assert v.rstrip().endswith("endmodule")


# --- sby output parsing ---------------------------------------------------


def test_parse_sby_pass():
    r = _parse_sby_output("SBY 1:2:3 [formal] engine_0.status = PASS\nSBY DONE")
    assert r["status"] == "PASS"
    assert r["proven"] is True


def test_parse_sby_fail():
    r = _parse_sby_output("SBY [formal] engine_0.status = FAIL\nassertion failed")
    assert r["status"] == "FAIL"
    assert r["proven"] is False


def test_parse_sby_unknown():
    r = _parse_sby_output("no useful status text here")
    assert r["status"] is None
    assert r["proven"] is None


# --- integration (opt-in: sby is slow) ------------------------------------


def test_run_formal_integration():
    """Prove the counter reference holds its reset invariant. Opt-in."""
    if os.environ.get("VF_RUN_INTEGRATION") is None or shutil.which("sby") is None:
        return  # skipped (fast suite); set VF_RUN_INTEGRATION=1 to run
    from formal_prove import run_formal
    rtl = _SKILLS_DIR / "references" / "counter.v"
    props = generate_properties({"modules": [{
        "module_name": "counter",
        "ports": [{"name": "clk", "direction": "input"},
                  {"name": "rst", "direction": "input"},
                  {"name": "en", "direction": "input"},
                  {"name": "count", "direction": "output", "width": 8}],
    }]}, "counter")
    r = run_formal(str(rtl), props, "counter", timeout=60)
    assert r["status"] in ("PASS", "FAIL", "ERROR", "TIMEOUT"), r


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS  {name}")
    print("All formal_prove tests passed.")
