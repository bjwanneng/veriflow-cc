"""Unit tests for VeriFlow DSL Verilog emitter."""

import sys
import os
import unittest


from veriflow_dsl._types import Signal, Const
from veriflow_dsl._module import Module
from veriflow_dsl._emitter import VerilogEmitter


class TestEmitterBasic(unittest.TestCase):
    """Test basic Verilog emission."""

    def test_simple_wire(self):
        m = Module("passthrough")
        inp = Signal(8, name="data_in")
        out = Signal(8, name="data_out")
        m.add_input(inp)
        m.add_output(out)
        m.add_signal(out)
        m.d.comb += out.eq(inp)

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        # Must contain module declaration
        self.assertIn("module passthrough", code)
        self.assertIn("input  wire [7:0] data_in", code)
        self.assertIn("output wire [7:0] data_out", code)
        self.assertIn("endmodule", code)

    def test_counter(self):
        from veriflow_dsl._types import Mux
        m = Module("counter")
        cnt = Signal(8, name="cnt", reset=0)
        en = Signal(1, name="en")
        m.add_input(en)
        m.add_output(cnt)
        m.add_signal(cnt)
        m.d.sync += cnt.eq(Mux(en, cnt + Const(1, 8), cnt))

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        # Must contain sequential block with reset
        self.assertIn("always @(posedge clk)", code)
        self.assertIn("if (rst)", code)
        self.assertIn("cnt_reg", code)

    def test_timing_contract(self):
        m = Module("test")
        inp = Signal(8, name="a")
        out = Signal(8, name="result")
        m.add_input(inp)
        m.add_output(out)
        m.add_signal(out)
        m.d.comb += out.eq(inp ^ Const(0xFF, 8))

        emitter = VerilogEmitter()
        contract = emitter.emit_timing_contract(m)

        self.assertIn("result", contract["golden_to_port"])
        self.assertEqual(contract["port_widths"]["result"], 8)
        self.assertEqual(contract["input_ports"]["a"], 8)
        self.assertEqual(contract["signals"]["result"]["timing"], "wire")


class TestEmitterHeader(unittest.TestCase):
    """Test header and formatting."""

    def test_header_includes_timescale(self):
        m = Module("test")
        s = Signal(1, name="dummy")
        m.add_signal(s)

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        self.assertIn("`timescale 1ns / 1ps", code)
        self.assertIn("`default_nettype none", code)
        self.assertIn("`resetall", code)


class TestEmitterMixedDomain(unittest.TestCase):
    """Test modules with both comb and sync assignments."""

    def test_mixed_comb_sync(self):
        """Module with both combinational and sequential logic."""
        from veriflow_dsl._types import Mux
        m = Module("mixed")
        inp = Signal(8, name="data_in")
        cnt = Signal(8, name="cnt", reset=0)
        out = Signal(8, name="out")
        m.add_input(inp)
        m.add_signal(cnt)
        m.add_output(cnt)
        m.add_output(out)
        m.add_signal(out)
        m.d.sync += cnt.eq(cnt + Const(1, 8))
        m.d.comb += out.eq(cnt + inp)

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        # Must have both blocks
        self.assertIn("always @*", code)
        self.assertIn("always @(posedge clk)", code)
        # cnt is sync → _reg
        self.assertIn("cnt_reg", code)
        # out is comb → _next
        self.assertIn("out_next", code)
        # Output wire assignments
        self.assertIn("assign cnt = cnt_reg", code)
        self.assertIn("assign out = out_next", code)

    def test_next_reg_naming_correctness(self):
        """Verify _next/_reg naming follows timing domain rules."""
        m = Module("naming")
        a = Signal(8, name="a")
        wire_out = Signal(8, name="wire_out")
        reg_out = Signal(8, name="reg_out")
        m.add_input(a)
        m.add_output(wire_out)
        m.add_signal(wire_out)
        m.add_output(reg_out)
        m.add_signal(reg_out)
        m.d.comb += wire_out.eq(a + Const(1, 8))
        m.d.sync += reg_out.eq(a)

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        # wire_out: comb → _next suffix in always @*
        self.assertIn("wire_out_next = ", code)
        self.assertIn("assign wire_out = wire_out_next", code)

        # reg_out: sync → _reg suffix in always @(posedge clk)
        self.assertIn("reg_out_reg <= ", code)
        self.assertIn("assign reg_out = reg_out_reg", code)

    def test_comb_reads_sync_signal(self):
        """Comb output reads from a registered signal — must use _reg."""
        m = Module("comb_reads_sync")
        cnt = Signal(8, name="cnt", reset=0)
        out = Signal(8, name="out")
        m.add_output(cnt)
        m.add_signal(cnt)
        m.add_output(out)
        m.add_signal(out)
        m.d.sync += cnt.eq(cnt + Const(1, 8))
        m.d.comb += out.eq(cnt)  # comb reads sync signal

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        # In comb block, cnt should be renamed to cnt_reg
        # Find "out_next = cnt_reg" in the always @* block
        self.assertIn("cnt_reg", code)
        # The comb assignment should use cnt_reg
        self.assertIn("out_next = cnt_reg", code)


class TestEmitterBarrelShifter(unittest.TestCase):
    """Test variable rotation barrel shifter generation."""

    def test_variable_rotation_emits_barrel_shifter(self):
        """Variable rotation should produce barrel shifter, not variable part-select."""
        m = Module("rot_test")
        data = Signal(8, name="data")
        shift = Signal(3, name="shift")
        out = Signal(8, name="out")
        m.add_input(data)
        m.add_input(shift)
        m.add_output(out)
        m.add_signal(out)
        m.d.comb += out.eq(data.rotate_left(shift))

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        # Should contain barrel shifter
        self.assertIn("_rol_", code)
        self.assertIn("always @(*)", code)
        # Barrel shifter stages should use conditional rotation with constant indices
        # (legal in Verilog-2005), not variable part-select like data[shift-:8]
        self.assertNotIn("-:", code)  # Verilog-2005 does not have indexed part-select

    def test_barrel_shifter_uses_correct_signal_names(self):
        """Barrel shifter input must match signal's timing domain."""
        # sync domain signal used in variable rotation
        m = Module("rot_sync")
        data = Signal(8, name="data", reset=0)
        shift = Signal(3, name="shift")
        out = Signal(8, name="out")
        m.add_input(shift)
        m.add_output(data)
        m.add_signal(data)
        m.add_output(out)
        m.add_signal(out)
        m.d.sync += data.eq(data + Const(1, 8))
        m.d.comb += out.eq(data.rotate_left(shift))

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        # Barrel shifter should reference data_reg (sync domain)
        self.assertIn("data_reg", code)
        # Find barrel shifter section and check input is data_reg
        lines = code.split("\n")
        barrel_lines = [l for l in lines if "_rol_" in l and "data" in l.lower()]
        # At least one barrel shifter line should reference data_reg
        has_data_reg_in_barrel = any("data_reg" in l for l in barrel_lines)
        self.assertTrue(has_data_reg_in_barrel,
                        f"Barrel shifter should use data_reg but got: {barrel_lines}")


if __name__ == "__main__":
    unittest.main()
