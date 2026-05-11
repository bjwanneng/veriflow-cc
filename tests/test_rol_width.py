"""Test ROL width assertion — Bug Pattern: SM3 ROL on 34/36-bit instead of 32-bit."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from veriflow_dsl._types import Signal, Const, _ROL


def test_rol_width_matches_operand():
    """ROL width must match operand width."""
    sig32 = Signal(32, name="a")
    rol = sig32.rotate_left(5)
    assert rol.width == 32


def test_rol_width_mismatch_raises():
    """Operand wider than rotation width must raise."""
    sig34 = Signal(34, name="wide")
    # SM3 bug: 34-bit operand rotated as if 32-bit
    raised = False
    try:
        # Direct _ROL construction with wrong width
        bad = _ROL(sig34, Const(5), 32)
    except AssertionError as e:
        raised = True
        assert "width" in str(e).lower()
    assert raised, "Expected AssertionError for width mismatch"


def test_rotate_left_self_width():
    """rotate_left must inherit self.width as rotation width."""
    sig = Signal(32, name="x")
    rol = sig.rotate_left(7)
    assert rol._operand.width == 32
    assert rol._width == 32


def test_rotate_right_self_width():
    """rotate_right must inherit self.width as rotation width."""
    sig = Signal(32, name="y")
    ror = sig.rotate_right(3)
    assert ror._operand.width == 32
    assert ror._width == 32


if __name__ == "__main__":
    test_rol_width_matches_operand()
    print("[PASS] test_rol_width_matches_operand")

    test_rol_width_mismatch_raises()
    print("[PASS] test_rol_width_mismatch_raises")

    test_rotate_left_self_width()
    print("[PASS] test_rotate_left_self_width")

    test_rotate_right_self_width()
    print("[PASS] test_rotate_right_self_width")

    print("ALL ROL WIDTH TESTS PASSED")
