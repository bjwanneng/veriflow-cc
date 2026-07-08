"""Tests for reference_kb.py — module-type classification + snippet retrieval."""

import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from reference_kb import classify_module, retrieve_references  # noqa: E402


def _ports(*names):
    return [{"name": n} for n in names]


# --- classification -------------------------------------------------------


def test_classify_handshake_valid_ready():
    mod = {"module_name": "dut", "ports": [
        {"name": "valid_in", "protocol": "valid", "ack_port": "ready_out"},
        {"name": "ready_out", "protocol": "ready"},
        {"name": "data_in"}, {"name": "data_out"},
    ]}
    assert classify_module(mod) == "handshake_valid_ready"


def test_classify_fifo():
    mod = {"module_name": "fifo", "parameters": [{"name": "DEPTH"}],
           "ports": _ports("clk", "rst", "wr_en", "rd_en", "full", "empty",
                           "data_in", "data_out")}
    assert classify_module(mod) == "fifo"


def test_classify_fsm_from_cycle_timing():
    mod = {"module_name": "ctrl",
           "cycle_timing": [{"state": "IDLE"}, {"state": "RUN"}, {"state": "DONE"}],
           "ports": _ports("clk", "rst", "start", "done")}
    assert classify_module(mod) == "fsm"


def test_classify_arbiter():
    mod = {"module_name": "arb",
           "ports": _ports("clk", "rst", "req", "grant")}
    assert classify_module(mod) == "arbiter"


def test_classify_counter():
    mod = {"module_name": "cnt", "ports": _ports("clk", "rst", "en", "count")}
    assert classify_module(mod) == "counter"


def test_classify_generic_fallback():
    mod = {"module_name": "x", "ports": _ports("a", "b", "y")}
    assert classify_module(mod) == "generic"


# --- retrieval ------------------------------------------------------------


def test_retrieve_returns_matching_snippet_with_code():
    mod = {"module_name": "dut", "ports": [
        {"name": "valid_in", "protocol": "valid", "ack_port": "ready_out"},
        {"name": "ready_out"}, {"name": "data_in"}, {"name": "data_out"}]}
    refs = retrieve_references(mod)
    assert len(refs) >= 1
    top = refs[0]
    assert top["type"] == "handshake_valid_ready"
    assert "code" in top and "module" in top["code"]


def test_retrieve_generic_returns_something():
    mod = {"module_name": "x", "ports": _ports("a", "b")}
    refs = retrieve_references(mod)
    assert isinstance(refs, list)


def test_retrieve_includes_self_improve_learned_reference():
    """A promoted *_learned_*.v of the matching type must be retrievable."""
    import tempfile
    import reference_kb
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "handshake_valid_ready.v").write_text("module base; endmodule\n")
        (d / "handshake_valid_ready_learned_1.v").write_text("module learned; endmodule\n")
        orig = reference_kb._REFERENCES_DIR
        reference_kb._REFERENCES_DIR = d
        try:
            mod = {"module_name": "dut", "ports": [
                {"name": "valid_in", "protocol": "valid", "ack_port": "ready_out"},
                {"name": "ready_out"}]}
            refs = retrieve_references(mod, top_k=5)
            names = [r["name"] for r in refs]
            assert "handshake_valid_ready_learned_1" in names
        finally:
            reference_kb._REFERENCES_DIR = orig


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("All reference_kb tests passed.")
