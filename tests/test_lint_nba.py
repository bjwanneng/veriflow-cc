"""Tests for NBA Lint Hook (lint_nba.py)."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veriflow_dsl.lint_nba import (
    lint_module_v,
    _check_seq_only_nba,
    _check_port_alignment,
    _extract_verilog_ports,
)


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestL1SeqOnlyNba(unittest.TestCase):
    """L1: Sequential blocks must use NBA only."""

    def test_catches_blocking_assignment(self):
        """bad_nba_blocking.v has '=' in always @(posedge clk)."""
        with open(os.path.join(FIXTURES, "bad_nba_blocking.v")) as f:
            src = f.read()
        errors = _check_seq_only_nba(src)

        l1_errors = [e for e in errors if e.rule == "L1_seq_only_nba"]
        self.assertGreaterEqual(len(l1_errors), 1, "Should catch at least 1 blocking assignment")

    def test_ignores_combinational_block(self):
        """good_fsm.v uses '=' in always @* — that is allowed."""
        with open(os.path.join(FIXTURES, "good_fsm.v")) as f:
            src = f.read()
        errors = _check_seq_only_nba(src)

        l1_errors = [e for e in errors if e.rule == "L1_seq_only_nba"]
        self.assertEqual(len(l1_errors), 0, "Combinational block '=' should not be flagged")

    def test_ignores_comparison_operators(self):
        """Comparison operators ==, !=, >=, <= should not trigger L1."""
        src = """
module test;
reg a;
always @(posedge clk) begin
    if (a == 1)
        a <= 0;
    if (a != 0)
        a <= 1;
    if (a >= 2)
        a <= 2;
    if (a <= 3)
        a <= 3;
end
endmodule
"""
        errors = _check_seq_only_nba(src)
        l1_errors = [e for e in errors if e.rule == "L1_seq_only_nba"]
        self.assertEqual(len(l1_errors), 0)

    def test_ignores_comments(self):
        """Comments containing '=' should not trigger L1."""
        src = """
module test;
reg a;
always @(posedge clk) begin
    // a = 0; this is a comment
    /* another comment: a = b */
    a <= 1;
end
endmodule
"""
        errors = _check_seq_only_nba(src)
        l1_errors = [e for e in errors if e.rule == "L1_seq_only_nba"]
        self.assertEqual(len(l1_errors), 0)

    def test_ignores_string_literals(self):
        """String literals containing 'begin' / 'end' should not affect depth."""
        src = """
module test;
reg a;
always @(posedge clk) begin
    $display("begin end");
    a <= 1;
end
endmodule
"""
        errors = _check_seq_only_nba(src)
        l1_errors = [e for e in errors if e.rule == "L1_seq_only_nba"]
        self.assertEqual(len(l1_errors), 0)

    def test_catches_compound_blocking(self):
        """+= -= *= in sequential block should be flagged."""
        src = """
module test;
reg [7:0] a;
always @(posedge clk) begin
    a += 1;
end
endmodule
"""
        errors = _check_seq_only_nba(src)
        l1_errors = [e for e in errors if e.rule == "L1_seq_only_nba"]
        self.assertEqual(len(l1_errors), 1)
        self.assertIn("+=", l1_errors[0].message)

    def test_good_counter_passes(self):
        """good_counter.v uses only <= in sequential block."""
        with open(os.path.join(FIXTURES, "good_counter.v")) as f:
            src = f.read()
        errors = _check_seq_only_nba(src)
        l1_errors = [e for e in errors if e.rule == "L1_seq_only_nba"]
        self.assertEqual(len(l1_errors), 0)


class TestL3PortAlignment(unittest.TestCase):
    """L3: Ports must match spec."""

    def test_extract_ports(self):
        """_extract_verilog_ports parses port declarations correctly."""
        src = """
module test(
    input  wire [7:0] data,
    input  wire       en,
    output wire [3:0] result
);
endmodule
"""
        ports = _extract_verilog_ports(src)
        self.assertEqual(ports["data"], {"direction": "input", "width": 8})
        self.assertEqual(ports["en"], {"direction": "input", "width": 1})
        self.assertEqual(ports["result"], {"direction": "output", "width": 4})

    def test_catches_width_mismatch(self):
        """bad_nba_mixed_ports.v has count[3:0] but spec expects [7:0]."""
        with open(os.path.join(FIXTURES, "bad_nba_mixed_ports.v")) as f:
            src = f.read()
        spec = {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst", "direction": "input", "width": 1},
                {"name": "en", "direction": "input", "width": 1},
                {"name": "count", "direction": "output", "width": 8},
            ]
        }
        errors = _check_port_alignment(src, spec)

        l3_errors = [e for e in errors if e.rule == "L3_port_align"]
        width_errors = [e for e in l3_errors if "width" in e.message]
        self.assertEqual(len(width_errors), 1, "Should catch width mismatch on 'count'")
        self.assertIn("count", width_errors[0].message)

    def test_catches_missing_port(self):
        """Spec has a port that RTL is missing."""
        src = """
module test(
    input  wire clk,
    output wire [7:0] count
);
endmodule
"""
        spec = {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst", "direction": "input", "width": 1},
                {"name": "count", "direction": "output", "width": 8},
            ]
        }
        errors = _check_port_alignment(src, spec)

        missing = [e for e in errors if "Missing" in e.message]
        self.assertEqual(len(missing), 1)
        self.assertIn("rst", missing[0].message)

    def test_catches_extra_port(self):
        """RTL has a port that spec doesn't know about."""
        src = """
module test(
    input  wire clk,
    input  wire rst,
    input  wire extra,
    output wire [7:0] count
);
endmodule
"""
        spec = {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst", "direction": "input", "width": 1},
                {"name": "count", "direction": "output", "width": 8},
            ]
        }
        errors = _check_port_alignment(src, spec)

        extra = [e for e in errors if "Extra" in e.message]
        self.assertEqual(len(extra), 1)
        self.assertIn("extra", extra[0].message)

    def test_catches_direction_mismatch(self):
        """Port direction differs between RTL and spec."""
        src = """
module test(
    input  wire clk,
    input  wire count
);
endmodule
"""
        spec = {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "count", "direction": "output", "width": 1},
            ]
        }
        errors = _check_port_alignment(src, spec)

        dir_errors = [e for e in errors if "direction" in e.message]
        self.assertEqual(len(dir_errors), 1)

    def test_good_counter_passes(self):
        """good_counter.v ports match the spec."""
        with open(os.path.join(FIXTURES, "good_counter.v")) as f:
            src = f.read()
        spec = {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst", "direction": "input", "width": 1},
                {"name": "en", "direction": "input", "width": 1},
                {"name": "count", "direction": "output", "width": 8},
            ]
        }
        errors = _check_port_alignment(src, spec)
        self.assertEqual(len(errors), 0)


class TestIntegration(unittest.TestCase):
    """End-to-end lint_module_v tests."""

    def test_bad_nba_blocking_fails_l1(self):
        path = os.path.join(FIXTURES, "bad_nba_blocking.v")
        errors = lint_module_v(path)
        l1 = [e for e in errors if e.rule == "L1_seq_only_nba"]
        self.assertGreaterEqual(len(l1), 1)

    def test_bad_ports_fails_l3(self):
        path = os.path.join(FIXTURES, "bad_nba_mixed_ports.v")
        spec = {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst", "direction": "input", "width": 1},
                {"name": "en", "direction": "input", "width": 1},
                {"name": "count", "direction": "output", "width": 8},
            ]
        }
        errors = lint_module_v(path, spec)
        l3 = [e for e in errors if e.rule == "L3_port_align"]
        self.assertGreaterEqual(len(l3), 1)

    def test_good_counter_passes(self):
        path = os.path.join(FIXTURES, "good_counter.v")
        spec = {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst", "direction": "input", "width": 1},
                {"name": "en", "direction": "input", "width": 1},
                {"name": "count", "direction": "output", "width": 8},
            ]
        }
        errors = lint_module_v(path, spec)
        self.assertEqual(len(errors), 0)

    def test_good_fsm_passes(self):
        path = os.path.join(FIXTURES, "good_fsm.v")
        spec = {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst", "direction": "input", "width": 1},
                {"name": "start", "direction": "input", "width": 1},
                {"name": "state", "direction": "output", "width": 2},
                {"name": "done", "direction": "output", "width": 1},
            ]
        }
        errors = lint_module_v(path, spec)
        self.assertEqual(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
