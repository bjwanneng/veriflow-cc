"""Tests for yosys_equiv.py — Yosys-based formal equivalence checker.

Tests script generation, output parsing, and graceful fallback when
Yosys is not installed.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src" / "claude_skills" / "vf-rtl"))


class TestScriptGeneration(unittest.TestCase):
    """The Yosys script contains correct read_verilog and equiv commands."""

    def test_script_contains_read_verilog(self):
        from yosys_equiv import _build_yosys_script
        script = _build_yosys_script("ref.v", "impl.v", "my_module")
        self.assertIn("read_verilog -defer ref.v", script)
        self.assertIn("read_verilog -defer impl.v", script)

    def test_script_contains_equiv_commands(self):
        from yosys_equiv import _build_yosys_script
        script = _build_yosys_script("ref.v", "impl.v", "my_module")
        self.assertIn("equiv_make ref_top impl_top equiv", script)
        self.assertIn("equiv_simple", script)
        self.assertIn("equiv_status -assert", script)

    def test_script_uses_different_top_names(self):
        """If ref and impl have different top names, equiv_make must map them."""
        from yosys_equiv import _build_yosys_script
        script = _build_yosys_script("ref.v", "impl.v", "ref_top", "impl_top")
        self.assertIn("equiv_make ref_top impl_top", script)


class TestOutputParsing(unittest.TestCase):
    """Parsing Yosys equiv_status output."""

    def test_parse_pass(self):
        from yosys_equiv import _parse_equiv_output
        output = """
        Equivalence successfully proved!
        Found 0 unproven $equiv cells.
        """
        result = _parse_equiv_output(output)
        self.assertTrue(result["equivalent"])
        self.assertEqual(len(result["unproven"]), 0)

    def test_parse_fail(self):
        from yosys_equiv import _parse_equiv_output
        output = """
        Found 2 unproven $equiv cells:
        gold.y != gate.y
        gold.x != gate.x
        """
        result = _parse_equiv_output(output)
        self.assertFalse(result["equivalent"])
        self.assertGreaterEqual(len(result["unproven"]), 1)

    def test_parse_no_output(self):
        from yosys_equiv import _parse_equiv_output
        result = _parse_equiv_output("")
        self.assertIsNone(result["equivalent"])


class TestCLIArgs(unittest.TestCase):
    """Command-line interface validation."""

    def test_missing_yosys_graceful(self):
        """If yosys is not in PATH, return a dict with yosys_available=False."""
        from yosys_equiv import check_equivalence
        result = check_equivalence(
            ref_path="/dev/null",
            impl_path="/dev/null",
            top_name="test",
            yosys_bin="/nonexistent/yosys",
        )
        self.assertFalse(result["yosys_available"])


if __name__ == "__main__":
    unittest.main()
