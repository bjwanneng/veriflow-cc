"""Tests for combinational logic lint rules (L8-L10).

L8: Latch detection — incomplete assignments in always @(*) infer latches.
L9: Combinational loop — assign statements referencing themselves.
L10: Undriven wire — wire declared but never assigned.
"""

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import unittest
from veriflow_dsl.lint_nba import lint_module_v, LintError


class TestL8LatchDetection(unittest.TestCase):
    """L8: Detect latches inferred from incomplete assignments."""

    def _lint(self, src: str) -> list[LintError]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".v", delete=False) as f:
            f.write(src)
            f.flush()
            return lint_module_v(f.name, None)

    def test_latch_inferred_from_missing_else(self):
        """always @(*) with if-without-else on output reg infers latch."""
        src = """\
module latch_test(
    input wire a,
    input wire b,
    output reg y
);
    always @(*) begin
        if (a)
            y = b;
    end
endmodule
"""
        errors = [e for e in self._lint(src) if e.rule == "L8_latch_detect"]
        self.assertGreaterEqual(len(errors), 1, "Expected latch warning for missing else")

    def test_no_latch_with_else(self):
        """Complete if/else in always @(*) is safe."""
        src = """\
module no_latch(
    input wire a,
    input wire b,
    output reg y
);
    always @(*) begin
        if (a)
            y = b;
        else
            y = 1'b0;
    end
endmodule
"""
        errors = [e for e in self._lint(src) if e.rule == "L8_latch_detect"]
        self.assertEqual(len(errors), 0)

    def test_no_latch_for_sequential_block(self):
        """Sequential blocks (posedge clk) are not checked for latch."""
        src = """\
module seq_block(
    input wire clk,
    input wire a,
    input wire b,
    output reg y
);
    always @(posedge clk) begin
        if (a)
            y <= b;
    end
endmodule
"""
        errors = [e for e in self._lint(src) if e.rule == "L8_latch_detect"]
        self.assertEqual(len(errors), 0)


class TestL9CombinationalLoop(unittest.TestCase):
    """L9: Detect self-referencing assign statements."""

    def _lint(self, src: str) -> list[LintError]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".v", delete=False) as f:
            f.write(src)
            f.flush()
            return lint_module_v(f.name, None)

    def test_self_reference_in_assign(self):
        """assign a = a + 1 is a combinational loop."""
        src = """\
module loop_test(
    input wire clk,
    output reg [3:0] a
);
    assign a = a + 1;
endmodule
"""
        errors = [e for e in self._lint(src) if e.rule == "L9_comb_loop"]
        self.assertGreaterEqual(len(errors), 1)

    def test_no_loop_for_different_signals(self):
        """assign a = b + 1 is fine."""
        src = """\
module no_loop(
    input wire [3:0] b,
    output wire [3:0] a
);
    assign a = b + 1;
endmodule
"""
        errors = [e for e in self._lint(src) if e.rule == "L9_comb_loop"]
        self.assertEqual(len(errors), 0)


class TestL10UndrivenWire(unittest.TestCase):
    """L10: Detect wire declared but never assigned."""

    def _lint(self, src: str) -> list[LintError]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".v", delete=False) as f:
            f.write(src)
            f.flush()
            return lint_module_v(f.name, None)

    def test_undriven_wire(self):
        """wire declared but no assign driving it."""
        src = """\
module undriven(
    input wire clk,
    output wire [7:0] out
);
    wire [7:0] internal;
    assign out = 8'd0;
endmodule
"""
        errors = [e for e in self._lint(src) if e.rule == "L10_undriven_wire"]
        self.assertGreaterEqual(len(errors), 1)
        self.assertIn("internal", errors[0].message)

    def test_driven_wire_ok(self):
        """wire with assign is fine."""
        src = """\
module driven(
    input wire [7:0] in,
    output wire [7:0] out
);
    wire [7:0] internal;
    assign internal = in;
    assign out = internal;
endmodule
"""
        errors = [e for e in self._lint(src) if e.rule == "L10_undriven_wire"]
        self.assertEqual(len(errors), 0)

    def test_input_wire_not_flagged(self):
        """Input ports are driven externally, should not be flagged."""
        src = """\
module input_ok(
    input wire [7:0] in,
    output wire [7:0] out
);
    assign out = in;
endmodule
"""
        errors = [e for e in self._lint(src) if e.rule == "L10_undriven_wire"]
        self.assertEqual(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
