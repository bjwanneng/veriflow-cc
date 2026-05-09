"""Unit tests for VeriFlow DSL Layer 0: Data Types."""

import sys
import os
import unittest


from veriflow_dsl._types import Signal, Const, Cat, Mux, Value, Assignment, _mask, _ROL, _BinOp


class TestConst(unittest.TestCase):
    def test_basic(self):
        c = Const(42)
        self.assertEqual(c.value, 42)
        self.assertEqual(c.width, 6)  # 42 = 0b101010 -> 6 bits

    def test_explicit_width(self):
        c = Const(5, width=32)
        self.assertEqual(c.value, 5)
        self.assertEqual(c.width, 32)

    def test_zero(self):
        c = Const(0)
        self.assertEqual(c.value, 0)
        self.assertEqual(c.width, 1)

    def test_value_too_large(self):
        with self.assertRaises(ValueError):
            Const(256, width=8)  # 256 doesn't fit in 8 bits

    def test_eval(self):
        c = Const(100)
        self.assertEqual(c._eval({}), 100)


class TestSignal(unittest.TestCase):
    def test_basic(self):
        s = Signal(8, name="data")
        self.assertEqual(s.width, 8)
        self.assertEqual(s.name, "data")
        self.assertEqual(s.reset, 0)
        self.assertFalse(s.reset_less)

    def test_auto_name(self):
        s = Signal(1)
        self.assertTrue(s.name.startswith("sig_"))

    def test_reset_value(self):
        s = Signal(8, name="cnt", reset=5)
        self.assertEqual(s.reset, 5)

    def test_eq_creates_assignment(self):
        s = Signal(8, name="a")
        c = Const(42, width=8)
        asn = s.eq(c)
        self.assertIsInstance(asn, Assignment)
        self.assertIs(asn.target, s)
        self.assertIs(asn.value, c)

    def test_eval_from_inputs(self):
        s = Signal(8, name="x")
        self.assertEqual(s._eval({"x": 0xAB}), 0xAB)

    def test_eval_missing(self):
        s = Signal(8, name="x")
        with self.assertRaises(ValueError):
            s._eval({})


class TestOperators(unittest.TestCase):
    def setUp(self):
        self.a = Signal(8, name="a")
        self.b = Signal(8, name="b")

    def test_add(self):
        expr = self.a + self.b
        result = expr._eval({"a": 10, "b": 20})
        self.assertEqual(result, 30)

    def test_sub(self):
        expr = self.a - self.b
        result = expr._eval({"a": 30, "b": 10})
        self.assertEqual(result, 20)

    def test_and(self):
        expr = self.a & self.b
        result = expr._eval({"a": 0xFF, "b": 0x0F})
        self.assertEqual(result, 0x0F)

    def test_or(self):
        expr = self.a | self.b
        result = expr._eval({"a": 0xF0, "b": 0x0F})
        self.assertEqual(result, 0xFF)

    def test_xor(self):
        expr = self.a ^ self.b
        result = expr._eval({"a": 0xFF, "b": 0x0F})
        self.assertEqual(result, 0xF0)

    def test_invert(self):
        expr = ~self.a
        result = expr._eval({"a": 0xF0})
        self.assertEqual(result, 0x0F)  # 8-bit inverted

    def test_shift_left(self):
        expr = self.a << Const(2, 8)
        result = expr._eval({"a": 5})
        self.assertEqual(result, 20)

    def test_shift_right(self):
        expr = self.a >> Const(2, 8)
        result = expr._eval({"a": 20})
        self.assertEqual(result, 5)

    def test_eq_compare(self):
        expr = self.a == self.b
        self.assertEqual(expr._eval({"a": 5, "b": 5}), 1)
        self.assertEqual(expr._eval({"a": 5, "b": 6}), 0)

    def test_lt_compare(self):
        expr = self.a < self.b
        self.assertEqual(expr._eval({"a": 3, "b": 5}), 1)
        self.assertEqual(expr._eval({"a": 5, "b": 3}), 0)

    def test_int_coercion(self):
        expr = self.a + 10
        result = expr._eval({"a": 5})
        self.assertEqual(result, 15)


class TestSlicing(unittest.TestCase):
    def test_single_bit(self):
        s = Signal(8, name="data")
        expr = s[3]
        result = expr._eval({"data": 0b1000})
        self.assertEqual(result, 1)

    def test_slice(self):
        s = Signal(8, name="data")
        expr = s[7:4]
        result = expr._eval({"data": 0xAB})
        self.assertEqual(result, 0xA)

    def test_slice_width(self):
        s = Signal(8, name="data")
        expr = s[7:4]
        self.assertEqual(expr.width, 4)


class TestCat(unittest.TestCase):
    def test_basic(self):
        a = Const(0xA, 4)
        b = Const(0xB, 4)
        cat = Cat(a, b)
        self.assertEqual(cat.width, 8)
        self.assertEqual(cat._eval({}), 0xAB)

    def test_mixed_widths(self):
        a = Const(0x1, 1)
        b = Const(0xFF, 8)
        cat = Cat(a, b)
        self.assertEqual(cat.width, 9)
        self.assertEqual(cat._eval({}), 0x1FF)


class TestMux(unittest.TestCase):
    def test_true(self):
        sel = Signal(1, name="sel")
        t = Const(10, 8)
        f = Const(20, 8)
        expr = Mux(sel, t, f)
        self.assertEqual(expr._eval({"sel": 1}), 10)

    def test_false(self):
        sel = Signal(1, name="sel")
        t = Const(10, 8)
        f = Const(20, 8)
        expr = Mux(sel, t, f)
        self.assertEqual(expr._eval({"sel": 0}), 20)


class TestROL(unittest.TestCase):
    def test_const_rotate(self):
        s = Signal(8, name="val")
        expr = s.rotate_left(3)
        # ROL(0b10110001, 3) = 0b10001101 = 0x8D
        # Wait: 0b10110001 = 0xB1
        # ROL(0xB1, 3): shift left 3 = 0x588, shift right 5 = 0x05
        # (0xB1 << 3) | (0xB1 >> 5) = 0x588 | 0x05 = 0x58D & 0xFF = 0x8D
        result = expr._eval({"val": 0xB1})
        self.assertEqual(result, 0x8D)

    def test_zero_rotate(self):
        s = Signal(8, name="val")
        expr = s.rotate_left(0)
        result = expr._eval({"val": 0xAB})
        self.assertEqual(result, 0xAB)

    def test_full_rotate(self):
        s = Signal(8, name="val")
        expr = s.rotate_left(8)
        result = expr._eval({"val": 0xAB})
        self.assertEqual(result, 0xAB)


class TestEqFallback(unittest.TestCase):
    """Test that __eq__/__ne__ fallback for non-Value types."""

    def test_eq_with_none(self):
        s = Signal(8, name="a")
        # Should return NotImplemented, Python then uses identity
        result = s.__eq__(None)
        self.assertEqual(result, NotImplemented)

    def test_eq_with_string(self):
        s = Signal(8, name="a")
        result = s.__eq__("hello")
        self.assertEqual(result, NotImplemented)

    def test_ne_with_none(self):
        s = Signal(8, name="a")
        result = s.__ne__(None)
        self.assertEqual(result, NotImplemented)

    def test_eq_with_int_still_returns_binop(self):
        s = Signal(8, name="a")
        result = s == 5
        self.assertIsInstance(result, _BinOp)

    def test_eq_with_signal_still_returns_binop(self):
        a = Signal(8, name="a")
        b = Signal(8, name="b")
        result = a == b
        self.assertIsInstance(result, _BinOp)

    def test_in_operator_with_list(self):
        a = Signal(8, name="a")
        b = Signal(8, name="b")
        lst = [a, b]
        # Should not crash; identity-based membership
        self.assertIn(a, lst)
        # Different Signal object with same name — should not be found
        # Use explicit loop to avoid triggering __eq__ → __bool__
        other = Signal(8, name="a")
        found = any(other is item for item in lst)
        self.assertFalse(found)

    def test_dict_key_lookup(self):
        a = Signal(8, name="a")
        d = {a: 42}
        # Identity-based lookup should work
        self.assertEqual(d[a], 42)


if __name__ == "__main__":
    unittest.main()
