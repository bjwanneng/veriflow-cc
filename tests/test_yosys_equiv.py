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
        self.assertIn('read_verilog "ref.v"', script)
        self.assertIn('read_verilog "impl.v"', script)

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


class TestSameNameCollision(unittest.TestCase):
    """Both files defining the same module name must not poison each other.

    Regression for I9: the script uses `rename {top} ref_top` then
    `read_verilog impl` then `rename {top} impl_top`. If either
    rename silently failed or only renamed one of two same-named modules,
    the equiv check would compare a design against itself and trivially pass.
    Originally the script used `read_verilog -defer`, but deferred modules
    are stored as `$abstract\\name` and the rename pass can't find them.
    """

    @classmethod
    def setUpClass(cls):
        import shutil
        if shutil.which("yosys") is None:
            raise unittest.SkipTest("yosys not on PATH")

    def test_same_module_name_distinguished(self):
        """Two non-equivalent modules with the same name must report FAIL."""
        from yosys_equiv import check_equivalence

        ref_src = """
        module adder(input [3:0] a, input [3:0] b, output [3:0] y);
            assign y = a + b;
        endmodule
        """
        impl_src = """
        module adder(input [3:0] a, input [3:0] b, output [3:0] y);
            assign y = a - b;
        endmodule
        """

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ref_p = tmp_path / "ref.v"
            impl_p = tmp_path / "impl.v"
            ref_p.write_text(ref_src)
            impl_p.write_text(impl_src)

            result = check_equivalence(
                ref_path=str(ref_p),
                impl_path=str(impl_p),
                top_name="adder",
                timeout=60,
            )

            # If rename failed silently the two designs would collapse into
            # one and equiv would trivially pass. We assert FAIL to prove
            # the script kept them separated.
            self.assertTrue(result["yosys_available"])
            self.assertEqual(
                result["equivalent"], False,
                f"Expected FAIL for non-equivalent same-named modules. "
                f"Got equivalent={result['equivalent']}. Raw:\n{result.get('raw', '')[-500:]}"
            )

    def test_same_module_name_actually_equivalent(self):
        """Two equivalent modules with the same name must report PASS."""
        from yosys_equiv import check_equivalence

        src = """
        module mux2(input s, input [3:0] a, input [3:0] b, output [3:0] y);
            assign y = s ? a : b;
        endmodule
        """
        src_alt = """
        module mux2(input s, input [3:0] a, input [3:0] b, output [3:0] y);
            assign y = ({4{s}} & a) | ({4{~s}} & b);
        endmodule
        """

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ref_p = tmp_path / "ref.v"
            impl_p = tmp_path / "impl.v"
            ref_p.write_text(src)
            impl_p.write_text(src_alt)

            result = check_equivalence(
                ref_path=str(ref_p),
                impl_path=str(impl_p),
                top_name="mux2",
                timeout=60,
            )

            self.assertTrue(result["yosys_available"])
            self.assertEqual(
                result["equivalent"], True,
                f"Expected PASS. Got equivalent={result['equivalent']}. "
                f"Raw:\n{result.get('raw', '')[-500:]}"
            )


if __name__ == "__main__":
    unittest.main()
