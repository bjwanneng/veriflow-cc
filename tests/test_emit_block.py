"""Tests for VerilogEmitter.emit_block() — block-level partial emission.

Covers:
- Sequential block: always @* + always @(posedge clk)
- Combinational block: always @* + assign
- BEGIN/END EMIT markers
- ROL bit-slice correctness
- Enable mux generation
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from veriflow_dsl._spec import WireT, RegT, RegAssign, rotate_left
from veriflow_dsl import reg_next, mux, vf_block, VerilogEmitter


def test_sequential_block_has_markers():
    """emit_block wraps output in BEGIN/END EMIT markers."""
    @vf_block(type="sequential")
    def step(*, x: RegT = RegT("x", 8)) -> list[RegAssign]:
        return [reg_next(x, x)]

    frag = VerilogEmitter().emit_block(step)
    assert "// --- BEGIN EMIT: step (sequential) ---" in frag
    assert "// --- END EMIT: step ---" in frag


def test_sequential_block_has_always_posedge():
    """Sequential block emits always @(posedge clk)."""
    @vf_block(type="sequential")
    def step(*, x: RegT = RegT("x", 8)) -> list[RegAssign]:
        return [reg_next(x, x)]

    frag = VerilogEmitter().emit_block(step)
    assert "always @(posedge clk)" in frag
    assert "<=" in frag  # NBA assignment


def test_sequential_block_with_enable():
    """reg_next with enable produces mux."""
    @vf_block(type="sequential")
    def step(
        *, x: RegT = RegT("x", 8), en: RegT = RegT("en", 1),
    ) -> list[RegAssign]:
        return [reg_next(x, mux(en, x, x), en=en)]

    frag = VerilogEmitter().emit_block(step)
    assert "en" in frag
    assert "?" in frag  # ternary mux


def test_combinational_block_is_assign():
    """Combinational block emits assign (via always @*)."""
    @vf_block(type="combinational")
    def identity(x: WireT = WireT("x", 8)) -> WireT:
        return x

    frag = VerilogEmitter().emit_block(identity)
    assert "// --- BEGIN EMIT: identity (combinational) ---" in frag
    assert "always @*" in frag or "assign" in frag


def test_rol_bit_slice_width():
    """ROL(9) on 32-bit produces correct bit slices: [22:0] + [31:23]."""
    @vf_block(type="combinational")
    def p0(x: WireT = WireT("x", 32)) -> WireT:
        return x ^ rotate_left(x, 9) ^ rotate_left(x, 17)

    frag = VerilogEmitter().emit_block(p0)
    # ROL(x, 9): {x[22:0], x[31:23]} — 23 + 9 = 32
    assert "x[22:0]" in frag
    assert "x[31:23]" in frag
    # ROL(x, 17): {x[14:0], x[31:15]} — 15 + 17 = 32
    assert "x[14:0]" in frag
    assert "x[31:15]" in frag


def test_not_vf_block_raises():
    """Passing a non-@vf_block function raises TypeError."""
    def plain_func():
        return []

    try:
        VerilogEmitter().emit_block(plain_func)
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


def test_sequential_reset():
    """Sequential block includes synchronous reset."""
    @vf_block(type="sequential")
    def step(*, x: RegT = RegT("x", 8)) -> list[RegAssign]:
        return [reg_next(x, x)]

    frag = VerilogEmitter().emit_block(step)
    assert "if (rst)" in frag
    assert "8'd0" in frag


if __name__ == "__main__":
    test_sequential_block_has_markers()
    test_sequential_block_has_always_posedge()
    test_sequential_block_with_enable()
    test_combinational_block_is_assign()
    test_rol_bit_slice_width()
    test_not_vf_block_raises()
    test_sequential_reset()
    print("All emit_block tests passed.")
