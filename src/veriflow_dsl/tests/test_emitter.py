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


class TestEmitterTemporaries(unittest.TestCase):
    """Test intermediate wire generation for complex expressions."""

    def test_complex_rol_emits_temp_wire(self):
        """Constant rotation on a non-trivial expression needs a temp wire."""
        m = Module("rol_temp")
        a = Signal(32, name="a")
        b = Signal(32, name="b")
        out = Signal(32, name="out")
        m.add_input(a)
        m.add_input(b)
        m.add_output(out)
        m.add_signal(out)
        # ROL on a binop expression — Verilog-2005 forbids part-select on expr
        m.d.comb += out.eq((a + b).rotate_left(7))

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        # Must emit a temp wire and assign the expression to it
        self.assertIn("wire [32:0] _vf_tmp_0", code)
        self.assertIn("assign _vf_tmp_0 = (a + b)", code)
        # Rotation must use the temp wire, not the expression directly
        # 33-bit operand rotated by 7: {operand[25:0], operand[32:26]}
        self.assertIn("{_vf_tmp_0[25:0], _vf_tmp_0[32:26]}", code)

    def test_dedup_same_expr_reuses_temp(self):
        """Same complex expression used twice should reuse one temp wire."""
        m = Module("rol_dedup")
        a = Signal(32, name="a")
        out1 = Signal(32, name="out1")
        out2 = Signal(32, name="out2")
        m.add_input(a)
        m.add_output(out1)
        m.add_signal(out1)
        m.add_output(out2)
        m.add_signal(out2)
        expr = a + Const(1, 32)
        m.d.comb += out1.eq(expr.rotate_left(3))
        m.d.comb += out2.eq(expr.rotate_left(5))

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        # Only one temp wire for the shared expression
        # decl(1) + assign(1) + two rotations each using it twice(4) = 6
        self.assertEqual(code.count("_vf_tmp_0"), 6)
        self.assertNotIn("_vf_tmp_1", code)

    def test_slice_on_complex_expr_emits_temp(self):
        """Part-select on a non-trivial expression needs a temp wire."""
        m = Module("slice_temp")
        a = Signal(16, name="a")
        b = Signal(16, name="b")
        out = Signal(8, name="out")
        m.add_input(a)
        m.add_input(b)
        m.add_output(out)
        m.add_signal(out)
        m.d.comb += out.eq((a + b)[7:0])

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        self.assertIn("wire [16:0] _vf_tmp_0", code)
        self.assertIn("assign _vf_tmp_0 = (a + b)", code)
        self.assertIn("_vf_tmp_0[7:0]", code)

    def test_simple_signal_no_temp(self):
        """Rotation on a simple signal should NOT emit a temp wire."""
        m = Module("rol_simple")
        a = Signal(32, name="a")
        out = Signal(32, name="out")
        m.add_input(a)
        m.add_output(out)
        m.add_signal(out)
        m.d.comb += out.eq(a.rotate_left(7))

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        self.assertNotIn("_vf_tmp", code)
        # 32-bit operand rotated by 7: {a[24:0], a[31:25]}
        self.assertIn("{a[24:0], a[31:25]}", code)

    def test_no_temp_wire_name_collision_across_blocks(self):
        """Comb and seq blocks with temp wires must use distinct names."""
        from veriflow_dsl._types import Mux
        m = Module("collision_test")
        a = Signal(16, name="a")
        cnt = Signal(16, name="cnt", reset=0)
        out = Signal(16, name="out")
        m.add_input(a)
        m.add_signal(cnt)
        m.add_output(cnt)
        m.add_output(out)
        m.add_signal(out)
        # Comb block: temp wire for (a + Const) under slice
        m.d.comb += out.eq((a + Const(1, 16))[7:0])
        # Seq block: temp wire for (cnt + Const) under rotation
        m.d.sync += cnt.eq((cnt + Const(1, 16)).rotate_left(3))

        emitter = VerilogEmitter()
        code = emitter.emit(m)

        # Collect all _vf_tmp_N names
        import re
        tmp_names = set(re.findall(r'_vf_tmp_\d+', code))
        # Each name should appear in exactly one wire declaration
        decl_lines = [l for l in code.split("\n") if l.strip().startswith("wire ") and "_vf_tmp_" in l]
        decl_names = [re.search(r'(_vf_tmp_\d+)', l).group(1) for l in decl_lines]
        # No duplicate declarations
        self.assertEqual(len(decl_names), len(set(decl_names)),
                         f"Duplicate wire declarations: {decl_names}")
        # Both blocks contributed temp wires
        self.assertGreaterEqual(len(decl_names), 2)


if __name__ == "__main__":
    unittest.main()
