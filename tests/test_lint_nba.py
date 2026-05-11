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


class TestL3SpecModuleExtraction(unittest.TestCase):
    """L3: main() must extract the correct module from top-level spec.json."""

    def _write_spec(self, tmpdir, spec_dict):
        spec_path = os.path.join(tmpdir, "spec.json")
        import json
        with open(spec_path, "w") as f:
            json.dump(spec_dict, f)
        return spec_path

    def test_extracts_module_from_top_level_dict(self):
        """Top-level spec.json with modules list — main() must extract the matching module."""
        import tempfile, subprocess
        rtl_src = """
module good_counter(
    input  wire clk,
    input  wire rst,
    input  wire en,
    output reg [7:0] count
);
    always @(posedge clk) count <= count + 1;
endmodule
"""
        spec = {
            "design_name": "test",
            "modules": [
                {
                    "module_name": "good_counter",
                    "module_type": "leaf",
                    "ports": [
                        {"name": "clk", "direction": "input", "width": 1},
                        {"name": "rst", "direction": "input", "width": 1},
                        {"name": "en", "direction": "input", "width": 1},
                        {"name": "count", "direction": "output", "width": 8},
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            rtl_path = os.path.join(td, "good_counter.v")
            with open(rtl_path, "w") as f:
                f.write(rtl_src)
            spec_path = self._write_spec(td, spec)
            result = subprocess.run(
                [sys.executable, "-m", "veriflow_dsl.lint_nba", rtl_path, spec_path],
                capture_output=True, text=True,
                cwd=os.path.join(os.path.dirname(__file__), "..", "src"),
            )
            self.assertEqual(result.returncode, 0, f"Expected exit 0 but got {result.returncode}: {result.stdout}\nstderr: {result.stderr}")
            self.assertNotIn("L3_port_align", result.stdout, "Should have no L3 errors when spec module is correctly extracted")

    def test_extracts_module_by_module_name_key(self):
        """Module matching should use module_name (not name)."""
        import tempfile, subprocess
        rtl_src = """
module my_mod(input wire clk, output reg [3:0] out);
    always @(posedge clk) out <= 0;
endmodule
"""
        spec = {
            "design_name": "test",
            "modules": [
                {
                    "module_name": "my_mod",
                    "ports": [
                        {"name": "clk", "direction": "input", "width": 1},
                        {"name": "out", "direction": "output", "width": 4},
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            rtl_path = os.path.join(td, "my_mod.v")
            with open(rtl_path, "w") as f:
                f.write(rtl_src)
            spec_path = self._write_spec(td, spec)
            result = subprocess.run(
                [sys.executable, "-m", "veriflow_dsl.lint_nba", rtl_path, spec_path],
                capture_output=True, text=True,
                cwd=os.path.join(os.path.dirname(__file__), "..", "src"),
            )
            self.assertEqual(result.returncode, 0, f"Expected exit 0 but got {result.returncode}: {result.stdout}\nstderr: {result.stderr}")
            self.assertNotIn("L3_port_align", result.stdout)

    def test_detects_missing_port_from_top_level_spec(self):
        """Top-level spec.json — missing port in RTL should produce L3 error."""
        import tempfile, subprocess
        rtl_src = """
module my_mod(input wire clk);
endmodule
"""
        spec = {
            "design_name": "test",
            "modules": [
                {
                    "module_name": "my_mod",
                    "ports": [
                        {"name": "clk", "direction": "input", "width": 1},
                        {"name": "data", "direction": "input", "width": 8},
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            rtl_path = os.path.join(td, "my_mod.v")
            with open(rtl_path, "w") as f:
                f.write(rtl_src)
            spec_path = self._write_spec(td, spec)
            result = subprocess.run(
                [sys.executable, "-m", "veriflow_dsl.lint_nba", rtl_path, spec_path, "--json"],
                capture_output=True, text=True,
                cwd=os.path.join(os.path.dirname(__file__), "..", "src"),
            )
            self.assertNotEqual(result.returncode, 0, "Should fail when port is missing")
            import json
            errors = json.loads(result.stdout)
            l3 = [e for e in errors if e["rule"] == "L3_port_align"]
            self.assertGreaterEqual(len(l3), 1, "Should report L3 error for missing 'data' port")

    def test_list_format_with_module_name(self):
        """spec.json as a list of module dicts — should match by module_name."""
        import tempfile, subprocess
        rtl_src = """
module foo(input wire a, output reg b);
    always @(*) b <= a;
endmodule
"""
        spec = [
            {
                "module_name": "foo",
                "ports": [
                    {"name": "a", "direction": "input", "width": 1},
                    {"name": "b", "direction": "output", "width": 1},
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as td:
            rtl_path = os.path.join(td, "foo.v")
            with open(rtl_path, "w") as f:
                f.write(rtl_src)
            spec_path = self._write_spec(td, spec)
            result = subprocess.run(
                [sys.executable, "-m", "veriflow_dsl.lint_nba", rtl_path, spec_path],
                capture_output=True, text=True,
                cwd=os.path.join(os.path.dirname(__file__), "..", "src"),
            )
            self.assertEqual(result.returncode, 0, f"Expected exit 0 but got {result.returncode}: {result.stdout}\nstderr: {result.stderr}")
            self.assertNotIn("L3_port_align", result.stdout)


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
