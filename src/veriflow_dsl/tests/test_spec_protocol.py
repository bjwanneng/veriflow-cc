"""Tests for veriflow_spec protocol (v2): RegT, WireT, RegAssign, reg_next, decorators."""

import unittest

from veriflow_dsl._spec import (
    RegT, WireT, RegAssign,
    reg_next, mux, cat, slice_,
    vf_block, vf_fsm,
)


class TestRegT(unittest.TestCase):
    def test_creation(self):
        r = RegT(name="a_reg", width=32)
        self.assertEqual(r.name, "a_reg")
        self.assertEqual(r.width, 32)

    def test_default_width(self):
        r = RegT(name="flag")
        self.assertEqual(r.width, 32)

    def test_arith_with_reg(self):
        a = RegT("a_reg", 32)
        b = RegT("b_reg", 32)
        result = a + b
        self.assertIsInstance(result, WireT)
        self.assertEqual(result.width, 33)  # add: max+1

    def test_arith_with_int(self):
        a = RegT("a_reg", 32)
        result = a + 5
        self.assertIsInstance(result, WireT)

    def test_rarith_with_int(self):
        a = RegT("a_reg", 32)
        result = 5 + a
        self.assertIsInstance(result, WireT)

    def test_bitwise(self):
        a = RegT("a", 32)
        b = RegT("b", 32)
        self.assertIsInstance(a ^ b, WireT)
        self.assertIsInstance(a & b, WireT)
        self.assertIsInstance(a | b, WireT)

    def test_invert(self):
        a = RegT("a", 32)
        result = ~a
        self.assertIsInstance(result, WireT)
        self.assertEqual(result.width, 32)

    def test_slicing_int(self):
        a = RegT("a", 32)
        result = a[15]
        self.assertIsInstance(result, WireT)
        self.assertEqual(result.width, 1)

    def test_slicing_range(self):
        a = RegT("a", 32)
        result = a[15:8]
        self.assertIsInstance(result, WireT)
        self.assertEqual(result.width, 8)

    def test_bool_raises(self):
        a = RegT("a", 32)
        with self.assertRaises(TypeError):
            bool(a)


class TestWireT(unittest.TestCase):
    def test_creation(self):
        w = WireT(name="temp", width=32)
        self.assertEqual(w.name, "temp")
        self.assertEqual(w.width, 32)

    def test_arith_with_reg(self):
        w = WireT("w", 32)
        r = RegT("r", 32)
        self.assertIsInstance(w + r, WireT)

    def test_arith_with_int(self):
        w = WireT("w", 32)
        self.assertIsInstance(w + 3, WireT)

    def test_slicing(self):
        w = WireT("w", 32)
        result = w[7:0]
        self.assertIsInstance(result, WireT)
        self.assertEqual(result.width, 8)

    def test_bool_raises(self):
        w = WireT("w", 32)
        with self.assertRaises(TypeError):
            bool(w)


class TestRegAssign(unittest.TestCase):
    def test_creation_from_reg(self):
        a = RegT("a_reg", 32)
        val = WireT("next_a", 32)
        ra = RegAssign(target=a, next_value=val)
        self.assertIs(ra.target, a)
        self.assertIs(ra.next_value, val)
        self.assertIsNone(ra.enable)

    def test_creation_with_enable(self):
        a = RegT("a_reg", 32)
        val = WireT("next_a", 32)
        en = RegT("calc_en", 1)
        ra = RegAssign(target=a, next_value=val, enable=en)
        self.assertIs(ra.enable, en)

    def test_creation_with_wire_enable(self):
        a = RegT("a_reg", 32)
        val = WireT("next_a", 32)
        en = WireT("en", 1)
        ra = RegAssign(target=a, next_value=val, enable=en)
        self.assertIs(ra.enable, en)

    def test_target_must_be_RegT(self):
        w = WireT("w", 32)
        val = WireT("next_w", 32)
        with self.assertRaises(TypeError):
            RegAssign(target=w, next_value=val)


class TestRegNext(unittest.TestCase):
    def test_basic(self):
        a = RegT("a_reg", 32)
        val = WireT("next_a", 32)
        ra = reg_next(a, val)
        self.assertIsInstance(ra, RegAssign)
        self.assertIs(ra.target, a)
        self.assertIs(ra.next_value, val)

    def test_with_enable(self):
        a = RegT("a_reg", 32)
        val = WireT("next_a", 32)
        en = RegT("calc_en", 1)
        ra = reg_next(a, val, en=en)
        self.assertIs(ra.enable, en)

    def test_with_int_value(self):
        a = RegT("a_reg", 32)
        ra = reg_next(a, 42)
        self.assertEqual(ra.next_value, 42)

    def test_first_arg_must_be_RegT(self):
        w = WireT("w", 32)
        with self.assertRaises(TypeError):
            reg_next(w, 42)

    def test_reg_next_chain_raises(self):
        """Cannot pass a RegAssign as next_value."""
        a = RegT("a_reg", 32)
        b = RegT("b_reg", 32)
        ra = reg_next(b, 1)
        with self.assertRaises(TypeError):
            reg_next(a, ra)


class TestMux(unittest.TestCase):
    def test_reg_reg(self):
        sel = RegT("sel", 1)
        a = RegT("a", 32)
        b = RegT("b", 32)
        result = mux(sel, a, b)
        self.assertIsInstance(result, WireT)
        self.assertEqual(result.width, 32)

    def test_wire_reg(self):
        sel = WireT("sel", 1)
        a = WireT("a", 32)
        b = RegT("b", 32)
        result = mux(sel, a, b)
        self.assertIsInstance(result, WireT)

    def test_with_int(self):
        sel = RegT("sel", 1)
        a = RegT("a", 32)
        result = mux(sel, a, 0)
        self.assertIsInstance(result, WireT)

    def test_mismatched_widths(self):
        sel = RegT("sel", 1)
        a = RegT("a", 32)
        b = RegT("b", 16)
        result = mux(sel, a, b)
        self.assertEqual(result.width, 32)


class TestCat(unittest.TestCase):
    def test_two_regs(self):
        a = RegT("a", 16)
        b = RegT("b", 16)
        result = cat(a, b)
        self.assertIsInstance(result, WireT)
        self.assertEqual(result.width, 32)

    def test_reg_wire_int(self):
        a = RegT("a", 16)
        b = WireT("b", 8)
        result = cat(a, b, 0xFF)
        self.assertIsInstance(result, WireT)
        self.assertEqual(result.width, 32)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            cat()


class TestSlice(unittest.TestCase):
    def test_from_reg(self):
        a = RegT("a", 32)
        result = slice_(a, 15, 8)
        self.assertIsInstance(result, WireT)
        self.assertEqual(result.width, 8)

    def test_from_wire(self):
        a = WireT("a", 32)
        result = slice_(a, 7, 0)
        self.assertIsInstance(result, WireT)
        self.assertEqual(result.width, 8)


class TestVfBlock(unittest.TestCase):
    def test_sequential(self):
        @vf_block(type="sequential")
        def round_step(*, a_reg: RegT, calc_en: RegT) -> list[RegAssign]:
            return [reg_next(a_reg, a_reg + 1)]

        self.assertEqual(round_step._vf_block_type, "sequential")
        self.assertEqual(round_step._vf_block_name, "round_step")

    def test_combinational(self):
        @vf_block(type="combinational")
        def adder(*, a_reg: RegT, b_reg: RegT) -> WireT:
            return a_reg + b_reg

        self.assertEqual(adder._vf_block_type, "combinational")

    def test_registry(self):
        from veriflow_dsl._spec import _TIMING_MODEL_REGISTRY
        # Ensure both previously-defined functions were registered
        # (test_registry may run before test_sequential due to alphabetic ordering)
        self.assertIn("adder", _TIMING_MODEL_REGISTRY)


class TestVfFsm(unittest.TestCase):
    def test_fsm_decorator(self):
        @vf_fsm(states=["IDLE", "CALC", "DONE"], reset_state="IDLE")
        def ctrl(*, state: RegT, calc_en: RegT) -> list[RegAssign]:
            return [reg_next(state, state)]

        self.assertEqual(ctrl._vf_block_type, "fsm")
        self.assertEqual(ctrl._vf_fsm_states, ["IDLE", "CALC", "DONE"])
        self.assertEqual(ctrl._vf_fsm_reset, "IDLE")


class TestMixedExpression(unittest.TestCase):
    """End-to-end: a realistic SM3-like expression."""

    def test_sm3_round_expression(self):
        """a + b << 7  ->  WireT with correct width."""
        a = RegT("a_reg", 32)
        b = RegT("b_reg", 32)

        ss1 = a + b
        self.assertIsInstance(ss1, WireT)
        self.assertEqual(ss1.width, 33)

        shifted = ss1 << 7
        self.assertIsInstance(shifted, WireT)
        self.assertEqual(shifted.width, 33)

        # Mask down to 32 bits via slice
        masked = slice_(shifted, 31, 0)
        self.assertEqual(masked.width, 32)

        next_a = reg_next(a, masked)
        self.assertIsInstance(next_a, RegAssign)

    def test_hash_chain_update(self):
        """Chain: A, B, C = TT1, A, ROL(B, 9)  (SM3 style)."""
        A = RegT("A_reg", 32)
        B = RegT("B_reg", 32)
        C = RegT("C_reg", 32)
        TT1 = RegT("TT1", 32)

        # TT1 computed elsewhere
        return_vals = [
            reg_next(A, TT1),
            reg_next(B, A),
            reg_next(C, B << 9),
        ]

        self.assertEqual(len(return_vals), 3)
        self.assertIs(return_vals[0].target, A)
        self.assertEqual(return_vals[1].next_value.name, "A_reg")  # reads old A
        self.assertEqual(return_vals[2].next_value.name, "(B_reg << 9)")

    def test_mux_in_reg_next(self):
        """reg_next with mux: hold or update based on enable."""
        a = RegT("a_reg", 32)
        calc_en = RegT("calc_en", 1)
        new_val = RegT("new_val", 32)

        next_a = reg_next(a, mux(calc_en, new_val, a))
        self.assertIsInstance(next_a, RegAssign)
        self.assertEqual(next_a.next_value.name, "mux(calc_en, new_val, a_reg)")


if __name__ == "__main__":
    unittest.main()
