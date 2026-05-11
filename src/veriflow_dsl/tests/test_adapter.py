"""Tests for veriflow_spec adapter: timing_model -> DSL Module.

Covers the end-to-end path from @vf_block functions to Verilog emission.
"""

import unittest
import os
import tempfile

from veriflow_dsl._types import Signal
from veriflow_dsl._module import Module
from veriflow_dsl._emitter import VerilogEmitter
from veriflow_dsl._adapter import from_timing_model
from veriflow_dsl._spec import RegT, WireT, RegAssign, vf_block, reg_next, mux, cat


class TestFromTimingModel(unittest.TestCase):
    """Test from_timing_model adapter for sequential blocks."""

    def test_counter(self):
        @vf_block(type="sequential")
        def counter(
            *,
            count_reg: RegT = RegT("count_reg", 8),
            en: RegT = RegT("en", 1),
        ) -> list[RegAssign]:
            return [reg_next(count_reg, mux(en, count_reg + 1, count_reg))]

        m = from_timing_model(counter)
        self.assertIsInstance(m, Module)
        self.assertEqual(m.name, "counter")

        # count_reg should be output (updated by reg_next)
        port_names = [p.name for p in m.ports()]
        self.assertIn("count_reg", port_names)
        self.assertIn("en", port_names)

        # Emitter must produce valid Verilog
        code = VerilogEmitter().emit(m)
        self.assertIn("module counter", code)
        self.assertIn("output wire [7:0] count_reg", code)
        self.assertIn("input", code)
        self.assertIn("en", code)
        self.assertIn("always @(posedge clk)", code)
        self.assertIn("count_reg_reg", code)
        self.assertIn("assign count_reg = count_reg_reg", code)

    def test_two_registers(self):
        @vf_block(type="sequential")
        def shift(
            *,
            a_reg: RegT = RegT("a_reg", 32),
            b_reg: RegT = RegT("b_reg", 32),
        ) -> list[RegAssign]:
            return [
                reg_next(a_reg, b_reg),
                reg_next(b_reg, a_reg),
            ]

        m = from_timing_model(shift)
        code = VerilogEmitter().emit(m)

        # Both a_reg and b_reg should be outputs (both are targets)
        self.assertIn("output wire [31:0] a_reg", code)
        self.assertIn("output wire [31:0] b_reg", code)
        self.assertIn("a_reg_reg <= b_reg_reg", code)
        self.assertIn("b_reg_reg <= a_reg_reg", code)

    def test_input_only_reg(self):
        """A RegT that is NOT a reg_next target should be an input."""
        @vf_block(type="sequential")
        def passthrough(
            *,
            data: RegT = RegT("data", 8),
            sel: RegT = RegT("sel", 1),
            out_reg: RegT = RegT("out_reg", 8),
        ) -> list[RegAssign]:
            return [reg_next(out_reg, mux(sel, data, out_reg))]

        m = from_timing_model(passthrough)
        code = VerilogEmitter().emit(m)

        # data and sel are inputs (read-only)
        self.assertIn("input  wire [7:0] data", code)
        self.assertIn("input  wire sel", code)
        # out_reg is output (target)
        self.assertIn("output wire [7:0] out_reg", code)

    def test_with_enable(self):
        @vf_block(type="sequential")
        def gated_counter(
            *,
            count: RegT = RegT("count", 4),
            load_en: RegT = RegT("load_en", 1),
            load_val: RegT = RegT("load_val", 4),
        ) -> list[RegAssign]:
            return [reg_next(count, load_val, en=load_en)]

        m = from_timing_model(gated_counter)
        code = VerilogEmitter().emit(m)

        self.assertIn("output wire [3:0] count", code)
        self.assertIn("load_en", code)
        self.assertIn("load_val", code)

    def test_iverilog_compiles(self):
        """Verify emitted Verilog passes iverilog syntax check."""
        @vf_block(type="sequential")
        def simple(*, a: RegT = RegT("a", 4)) -> list[RegAssign]:
            return [reg_next(a, a + 1)]

        m = from_timing_model(simple)
        code = VerilogEmitter().emit(m)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".v", delete=False) as f:
            f.write(code)
            v_path = f.name

        try:
            import subprocess
            result = subprocess.run(
                ["iverilog", "-g2005", "-o", v_path + ".vvp", v_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, f"iverilog failed: {result.stderr}")
        except FileNotFoundError:
            self.skipTest("iverilog not installed")
        finally:
            os.unlink(v_path)
            if os.path.exists(v_path + ".vvp"):
                os.unlink(v_path + ".vvp")


class TestAdapterErrors(unittest.TestCase):
    def test_undecorated_function(self):
        def bad(*, a: RegT = RegT("a")) -> list[RegAssign]:
            return [reg_next(a, a)]

        with self.assertRaises(TypeError):
            from_timing_model(bad)

    def test_combinational_block_supported(self):
        @vf_block(type="combinational")
        def adder(*, a: RegT = RegT("a", 8), b: RegT = RegT("b", 8)) -> WireT:
            return a + b

        m = from_timing_model(adder)
        self.assertEqual(m.name, "adder")
        # Should have two input ports and one output port
        ports = m.ports()
        port_names = {p.name for p in ports}
        self.assertIn("a", port_names)
        self.assertIn("b", port_names)
        self.assertIn("adder_out", port_names)


if __name__ == "__main__":
    unittest.main()
