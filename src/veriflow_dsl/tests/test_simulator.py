"""Unit tests for VeriFlow DSL simulator."""

import sys
import os
import unittest


from veriflow_dsl._types import Signal, Const
from veriflow_dsl._module import Module
from veriflow_dsl._simulator import CycleSimulator


class TestSimulatorBasic(unittest.TestCase):
    """Test basic simulation with a simple counter."""

    def _build_counter(self):
        from veriflow_dsl._types import Mux
        m = Module("counter")
        cnt = Signal(8, name="cnt", reset=0)
        en = Signal(1, name="en")
        m.add_signal(cnt)
        m.add_input(en)
        m.add_output(cnt)
        m.d.sync += cnt.eq(Mux(en, cnt + Const(1, 8), cnt))
        return m

    def test_reset(self):
        m = self._build_counter()
        sim = CycleSimulator(m)
        # After reset, cnt should be 0
        self.assertEqual(sim.state["cnt"], 0)

    def test_counter_increment(self):
        m = self._build_counter()
        sim = CycleSimulator(m)

        # Cycle 0: enable=1 -> cnt goes from 0 to 1 (visible next cycle)
        sim.set_input("en", 1)
        snap = sim.step()
        self.assertEqual(snap["cnt"], 0)  # Still 0 at cycle 0

        # Cycle 1: cnt=1 now visible
        sim.set_input("en", 1)
        snap = sim.step()
        self.assertEqual(snap["cnt"], 1)

        # Cycle 2: cnt=2
        sim.set_input("en", 1)
        snap = sim.step()
        self.assertEqual(snap["cnt"], 2)

    def test_counter_hold(self):
        m = self._build_counter()
        sim = CycleSimulator(m)

        # Increment twice: cnt goes 0 -> 1 -> 2
        sim.set_input("en", 1)
        sim.step()
        sim.set_input("en", 1)
        sim.step()
        self.assertEqual(sim.state["cnt"], 2)

        # Hold for 3 cycles (en=0)
        for _ in range(3):
            sim.set_input("en", 0)
            sim.step()

        self.assertEqual(sim.state["cnt"], 2)  # Still 2

    def test_run(self):
        m = self._build_counter()
        sim = CycleSimulator(m)
        inputs = [{"en": 1}] * 5
        trace = sim.run(5, inputs)
        self.assertEqual(len(trace), 5)
        self.assertEqual(trace[0]["cnt"], 0)
        self.assertEqual(trace[4]["cnt"], 4)


class TestSimulatorComb(unittest.TestCase):
    """Test combinational logic simulation."""

    def test_wire_output(self):
        m = Module("adder")
        a = Signal(8, name="a")
        b = Signal(8, name="b")
        out = Signal(8, name="out")
        m.add_input(a)
        m.add_input(b)
        m.add_output(out)
        m.add_signal(out)
        m.d.comb += out.eq(a + b)

        sim = CycleSimulator(m)
        sim.set_input("a", 10)
        sim.set_input("b", 20)
        snap = sim.step()

        # Combinational output should be visible in same cycle
        self.assertEqual(snap["out"], 30)


class TestSimulatorTrace(unittest.TestCase):
    """Test trace format compatibility."""

    def test_trace_format(self):
        from veriflow_dsl._types import Mux
        m = Module("simple")
        cnt = Signal(4, name="cnt", reset=0)
        m.add_signal(cnt)
        m.add_output(cnt)
        m.d.sync += cnt.eq(cnt + Const(1, 4))

        sim = CycleSimulator(m)
        trace = sim.run(4)

        # Verify format
        self.assertIsInstance(trace, list)
        for entry in trace:
            self.assertIsInstance(entry, dict)
            self.assertIn("cnt", entry)

        # Verify values
        self.assertEqual(trace[0]["cnt"], 0)
        self.assertEqual(trace[1]["cnt"], 1)
        self.assertEqual(trace[2]["cnt"], 2)
        self.assertEqual(trace[3]["cnt"], 3)


class TestSimulatorCrossDomain(unittest.TestCase):
    """Test comb→sync cross-domain interaction."""

    def test_comb_reads_sync(self):
        """Comb output reads from a sync signal — same-cycle snapshot sees
        old register value in comb output (correct NBA semantics)."""
        m = Module("cross_domain")
        cnt = Signal(8, name="cnt", reset=0)
        out = Signal(8, name="out")
        m.add_output(cnt)
        m.add_signal(cnt)
        m.add_output(out)
        m.add_signal(out)
        m.d.sync += cnt.eq(cnt + Const(1, 8))
        m.d.comb += out.eq(cnt)  # comb reads sync signal

        sim = CycleSimulator(m)
        trace = sim.run(4)

        # Cycle 0: cnt=0 (reset), out=0 (comb reads cnt=0)
        self.assertEqual(trace[0]["cnt"], 0)
        self.assertEqual(trace[0]["out"], 0)

        # Cycle 1: cnt=1 (sync updated), out=1 (comb reads cnt=1)
        self.assertEqual(trace[1]["cnt"], 1)
        self.assertEqual(trace[1]["out"], 1)

        # Cycle 2: cnt=2, out=2
        self.assertEqual(trace[2]["cnt"], 2)
        self.assertEqual(trace[2]["out"], 2)

    def test_comb_chain_convergence(self):
        """Multi-level comb chain: a → b → c should converge."""
        m = Module("chain")
        inp = Signal(8, name="inp")
        a = Signal(8, name="a")
        b = Signal(8, name="b")
        c = Signal(8, name="c")
        m.add_input(inp)
        m.add_signal(a)
        m.add_signal(b)
        m.add_signal(c)
        m.d.comb += a.eq(inp + Const(1, 8))
        m.d.comb += b.eq(a + Const(1, 8))
        m.d.comb += c.eq(b + Const(1, 8))

        sim = CycleSimulator(m)
        sim.set_input("inp", 10)
        snap = sim.step()

        # inp=10 → a=11 → b=12 → c=13
        self.assertEqual(snap["a"], 11)
        self.assertEqual(snap["b"], 12)
        self.assertEqual(snap["c"], 13)

    def test_sync_reads_comb(self):
        """Sync assignment reads from comb output — models Verilog semantics
        where always @(posedge clk) reads wires driven by always @*."""
        from veriflow_dsl._types import Mux
        m = Module("sync_reads_comb")
        inp = Signal(8, name="inp")
        doubled = Signal(8, name="doubled")
        result = Signal(8, name="result", reset=0)
        m.add_input(inp)
        m.add_signal(doubled)
        m.add_output(result)
        m.add_signal(result)
        m.d.comb += doubled.eq(inp * Const(2, 8))
        m.d.sync += result.eq(doubled)

        sim = CycleSimulator(m)

        # Cycle 0: inp=5, doubled=10 (comb), result=0 (reset)
        sim.set_input("inp", 5)
        snap = sim.step()
        self.assertEqual(snap["doubled"], 10)
        self.assertEqual(snap["result"], 0)

        # Cycle 1: result updated to 10 from previous cycle
        sim.set_input("inp", 3)
        snap = sim.step()
        self.assertEqual(snap["result"], 10)  # NBA from cycle 0
        self.assertEqual(snap["doubled"], 6)  # new comb value

        # Cycle 2: result updated to 6
        sim.set_input("inp", 0)
        snap = sim.step()
        self.assertEqual(snap["result"], 6)


if __name__ == "__main__":
    unittest.main()
