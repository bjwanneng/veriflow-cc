"""Unit tests for VeriFlow DSL Layer 1: Module and Domain."""

import sys
import os
import unittest


from veriflow_dsl._types import Signal, Const
from veriflow_dsl._module import Module, Domain, DomainCollection


class TestDomain(unittest.TestCase):
    def test_comb_domain(self):
        d = Domain("comb")
        self.assertEqual(d.name, "comb")
        self.assertEqual(len(d.assignments), 0)

    def test_sync_domain(self):
        d = Domain("sync")
        self.assertEqual(d.name, "sync")

    def test_invalid_name(self):
        with self.assertRaises(ValueError):
            Domain("invalid")

    def test_iadd_single(self):
        d = Domain("comb")
        s = Signal(8, name="out")
        d += s.eq(Const(42, 8))
        self.assertEqual(len(d.assignments), 1)

    def test_iadd_list(self):
        d = Domain("sync")
        a = Signal(8, name="a")
        b = Signal(8, name="b")
        d += [a.eq(Const(1, 8)), b.eq(Const(2, 8))]
        self.assertEqual(len(d.assignments), 2)


class TestDomainCollection(unittest.TestCase):
    def test_properties(self):
        dc = DomainCollection()
        self.assertIsInstance(dc.comb, Domain)
        self.assertIsInstance(dc.sync, Domain)

    def test_separate_domains(self):
        dc = DomainCollection()
        self.assertIsNot(dc.comb, dc.sync)


class TestModule(unittest.TestCase):
    def test_basic_construction(self):
        m = Module("test_mod")
        self.assertEqual(m.name, "test_mod")

    def test_add_input(self):
        m = Module("test")
        s = Signal(8, name="data_in")
        m.add_input(s)
        ports = m.ports()
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0].name, "data_in")
        self.assertEqual(ports[0].direction, "input")

    def test_add_output(self):
        m = Module("test")
        s = Signal(8, name="data_out")
        m.add_output(s)
        ports = m.ports()
        self.assertEqual(ports[0].direction, "output")

    def test_analyze_comb_only(self):
        m = Module("test")
        a = Signal(8, name="a")
        out = Signal(8, name="out")
        m.add_input(a)
        m.add_output(out)
        m.add_signal(out)
        m.d.comb += out.eq(a + Const(1, 8))

        analysis = m.analyze()
        self.assertEqual(analysis["signals"]["out"]["timing"], "wire")

    def test_analyze_sync_only(self):
        m = Module("test")
        cnt = Signal(8, name="cnt", reset=0)
        m.add_signal(cnt)
        m.d.sync += cnt.eq(cnt + Const(1, 8))

        analysis = m.analyze()
        self.assertEqual(analysis["signals"]["cnt"]["timing"], "reg_next")

    def test_analyze_driver_conflict(self):
        m = Module("test")
        s = Signal(8, name="s")
        m.add_signal(s)
        m.d.comb += s.eq(Const(1, 8))
        m.d.sync += s.eq(Const(2, 8))

        with self.assertRaises(SyntaxError):
            m.analyze()

    def test_analyze_golden_to_port(self):
        m = Module("test")
        inp = Signal(8, name="data_in")
        out = Signal(8, name="data_out")
        m.add_input(inp)
        m.add_output(out)
        m.add_signal(out)
        m.d.comb += out.eq(inp)

        analysis = m.analyze()
        self.assertIn("data_out", analysis["golden_to_port"])
        self.assertEqual(analysis["port_widths"]["data_out"], 8)
        self.assertEqual(analysis["input_ports"]["data_in"], 8)

    def test_submodule(self):
        m = Module("top")
        sub = Module("sub_mod")
        m.add_submodule(sub, "u_sub")
        self.assertEqual(len(m.submodules), 1)
        self.assertEqual(m.submodules[0][0], "u_sub")


class TestModuleCaching(unittest.TestCase):
    """Test analyze() caching behavior."""

    def test_analyze_returns_same_object(self):
        m = Module("test")
        s = Signal(8, name="s")
        m.add_signal(s)
        m.d.comb += s.eq(Const(1, 8))
        a1 = m.analyze()
        a2 = m.analyze()
        self.assertIs(a1, a2)  # same object, cached

    def test_cache_invalidated_on_comb_assignment(self):
        m = Module("test")
        s = Signal(8, name="s")
        m.add_signal(s)
        m.d.comb += s.eq(Const(1, 8))
        a1 = m.analyze()
        # Add another signal and assignment
        s2 = Signal(8, name="s2")
        m.add_signal(s2)
        m.d.comb += s2.eq(Const(2, 8))
        a2 = m.analyze()
        self.assertIsNot(a1, a2)  # cache was invalidated
        self.assertEqual(len(a2["comb_assignments"]), 2)

    def test_cache_invalidated_on_sync_assignment(self):
        m = Module("test")
        s = Signal(8, name="s")
        s2 = Signal(8, name="s2")
        m.add_signal(s)
        m.add_signal(s2)
        m.d.sync += s.eq(Const(1, 8))
        a1 = m.analyze()
        # Adding to sync invalidates cache
        m.d.sync += s2.eq(Const(2, 8))
        self.assertIsNone(m._analysis_cache)
        a2 = m.analyze()
        self.assertEqual(len(a2["sync_assignments"]), 2)

    def test_invalidate_analysis(self):
        m = Module("test")
        s = Signal(8, name="s")
        m.add_signal(s)
        m.d.comb += s.eq(Const(1, 8))
        a1 = m.analyze()
        m.invalidate_analysis()
        self.assertIsNone(m._analysis_cache)
        a2 = m.analyze()
        self.assertIsNot(a1, a2)


if __name__ == "__main__":
    unittest.main()
