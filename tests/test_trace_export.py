"""Tests for veriflow_dsl.trace_export — Markdown trace exporter.

Defines the contract that trace_export.py must satisfy:

  Library API:
    from veriflow_dsl.trace_export import export_trace, export_trace_for_block

  CLI:
    python -m veriflow_dsl.trace_export \
        --timing-model <path> --block <name> --cycles N \
        [--inputs inputs.json] --output trace.md

The exporter produces prompt-friendly markdown tables that anchor LLM
generation to concrete cycle-by-cycle signal values.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


# ---------------------------------------------------------------------------
# Module fixtures (pure DSL)
# ---------------------------------------------------------------------------

def _build_counter8():
    """8-bit counter with enable — for hex formatting tests."""
    from veriflow_dsl import Module, Signal, Const
    from veriflow_dsl._types import Mux
    m = Module("counter8")
    cnt = Signal(8, name="cnt", reset=0)
    en = Signal(1, name="en")
    m.add_input(en)
    m.add_output(cnt)
    m.add_signal(cnt)
    m.d.sync += cnt.eq(Mux(en, cnt + Const(1, 8), cnt))
    return m


def _build_counter4():
    """4-bit counter — for decimal formatting tests."""
    from veriflow_dsl import Module, Signal, Const
    m = Module("counter4")
    cnt = Signal(4, name="cnt", reset=0)
    m.add_output(cnt)
    m.add_signal(cnt)
    m.d.sync += cnt.eq(cnt + Const(1, 4))
    return m


def _build_flag1():
    """Single-bit toggle — for binary formatting tests."""
    from veriflow_dsl import Module, Signal, Const
    m = Module("flag1")
    flag = Signal(1, name="flag", reset=0)
    m.add_output(flag)
    m.add_signal(flag)
    m.d.sync += flag.eq(flag ^ Const(1, 1))
    return m


# ---------------------------------------------------------------------------
# Tests: export_trace (library API)
# ---------------------------------------------------------------------------

class TestExportTraceBasic(unittest.TestCase):
    """export_trace(module, cycles, inputs) must return a markdown string."""

    def test_returns_string(self):
        from veriflow_dsl.trace_export import export_trace
        m = _build_counter8()
        md = export_trace(m, cycles=4, inputs=[{"en": 1}] * 4)
        self.assertIsInstance(md, str)
        self.assertGreater(len(md), 0)

    def test_contains_module_name_in_header(self):
        from veriflow_dsl.trace_export import export_trace
        m = _build_counter8()
        md = export_trace(m, cycles=3, inputs=[{"en": 1}] * 3)
        # First non-empty line should be a markdown heading naming the module.
        first_heading = next(
            (ln for ln in md.splitlines() if ln.startswith("##")), ""
        )
        self.assertIn("counter8", first_heading)

    def test_contains_cycle_column_and_n_rows(self):
        from veriflow_dsl.trace_export import export_trace
        m = _build_counter8()
        md = export_trace(m, cycles=4, inputs=[{"en": 1}] * 4)

        # Markdown table: header row, separator row, then N data rows.
        table_lines = [ln for ln in md.splitlines() if ln.startswith("|")]
        self.assertGreaterEqual(len(table_lines), 4 + 2,
                                "Table needs header + separator + N data rows")
        self.assertIn("cycle", table_lines[0])

    def test_data_rows_match_simulator_values(self):
        """The exported values must match what CycleSimulator produces."""
        from veriflow_dsl.trace_export import export_trace
        m = _build_counter8()
        md = export_trace(m, cycles=4, inputs=[{"en": 1}] * 4)

        # Find data rows (after header + separator).
        table_lines = [ln for ln in md.splitlines() if ln.startswith("|")]
        data_rows = table_lines[2:]  # skip header + separator
        self.assertEqual(len(data_rows), 4)

        # Cycle 0 cnt=0, cycle 3 cnt=3 — this is the contract simulator gives.
        # Values are formatted (hex for 8-bit), so we look for 0x00 and 0x03.
        self.assertIn("0x00", data_rows[0])
        self.assertIn("0x03", data_rows[3])


class TestExportTraceFormatting(unittest.TestCase):
    """Width-based formatting rules:
       1 bit       → 0 / 1 (no prefix)
       2-7 bit     → decimal
       >= 8 bit    → hex (0x...)
    """

    def test_wide_signal_uses_hex(self):
        from veriflow_dsl.trace_export import export_trace
        m = _build_counter8()
        md = export_trace(m, cycles=2, inputs=[{"en": 1}] * 2)
        # 8-bit cnt at cycle 0 → "0x00"
        self.assertRegex(md, r"\b0x00\b")

    def test_narrow_signal_uses_decimal(self):
        from veriflow_dsl.trace_export import export_trace
        m = _build_counter4()
        md = export_trace(m, cycles=4, inputs=None)
        # 4-bit cnt at cycle 3 → "3", and NO "0x03"
        self.assertNotRegex(md, r"0x0?3\b")
        # Decimal "3" appears in the body
        body = "\n".join(ln for ln in md.splitlines() if ln.startswith("|"))
        self.assertIn(" 3 ", body)

    def test_single_bit_signal_no_prefix(self):
        from veriflow_dsl.trace_export import export_trace
        m = _build_flag1()
        md = export_trace(m, cycles=4, inputs=None)
        # Should not contain "0x" since the only signal is 1 bit
        self.assertNotIn("0x", md)
        # Should contain "1" data values
        body = "\n".join(ln for ln in md.splitlines() if ln.startswith("|"))
        # cycle 0: flag=0, cycle 1: flag=1 (toggled from reset)
        self.assertRegex(body, r"\|\s*0\s*\|")  # at least one 0 cell
        self.assertRegex(body, r"\|\s*1\s*\|")  # at least one 1 cell


class TestExportTraceMeta(unittest.TestCase):
    """The header should declare signal widths so prompts can reference them."""

    def test_meta_lists_register_names_with_widths(self):
        from veriflow_dsl.trace_export import export_trace
        m = _build_counter8()
        md = export_trace(m, cycles=2, inputs=[{"en": 1}] * 2)
        # Look for a metadata bullet listing cnt's width.
        # Accept either "cnt[8]" or "cnt<8>" or "cnt: 8" formats — implementation choice.
        self.assertRegex(md, r"cnt\s*[\[<:]\s*8\s*[\]>]?")

    def test_meta_lists_input_names(self):
        from veriflow_dsl.trace_export import export_trace
        m = _build_counter8()
        md = export_trace(m, cycles=2, inputs=[{"en": 1}] * 2)
        # 'en' (1-bit input) should appear somewhere in the meta block.
        meta_block = md.split("|", 1)[0]  # everything before the first table row
        self.assertIn("en", meta_block)

    def test_meta_lists_comb_wire_outputs(self):
        """Comb-driven outputs (e.g. barrel-shifter result) must appear in
        the meta block too — otherwise the LLM cannot tell their width."""
        from veriflow_dsl import Module, Signal
        from veriflow_dsl.trace_export import export_trace

        m = Module("adder_comb")
        a = Signal(16, name="a")
        b = Signal(16, name="b")
        out = Signal(16, name="out")
        m.add_input(a)
        m.add_input(b)
        m.add_output(out)
        m.add_signal(out)
        m.d.comb += out.eq(a + b)

        md = export_trace(m, cycles=1, inputs=[{"a": 1, "b": 2}])
        meta_block = md.split("|", 1)[0]
        # 'out' is a comb-driven output, must show its width in meta
        self.assertRegex(meta_block, r"out\s*\[\s*16\s*\]")


# ---------------------------------------------------------------------------
# Tests: export_trace_for_block (timing_model convenience)
# ---------------------------------------------------------------------------

class TestExportTraceForBlock(unittest.TestCase):
    """export_trace_for_block(func, cycles, inputs) should adapt @vf_block
    functions and route through CycleSimulator."""

    def test_runs_on_anchor_fsm_4state(self):
        from veriflow_dsl.trace_export import export_trace_for_block
        # Load the actual anchor module so we exercise the exact path
        # SKILL.md will use (timing_model.py → adapter → simulator → md).
        anchor_dir = REPO_ROOT / "src/claude_skills/vf-rtl/anchors/fsm_4state"
        sys.path.insert(0, str(anchor_dir))
        try:
            from timing_model import fsm_4state  # type: ignore
        finally:
            sys.path.remove(str(anchor_dir))

        md = export_trace_for_block(
            fsm_4state,
            cycles=5,
            inputs=[
                {"start": 1, "done_signal": 0},
                {"start": 0, "done_signal": 0},
                {"start": 0, "done_signal": 1},
                {"start": 0, "done_signal": 0},
                {"start": 0, "done_signal": 0},
            ],
        )
        self.assertIn("fsm_4state", md)
        self.assertIn("state_reg", md)
        # FSM transitions: cycle 0 state_reg=0, cycle 1 state_reg=1
        # 2-bit signal → decimal formatting
        table_lines = [ln for ln in md.splitlines() if ln.startswith("|")]
        data_rows = table_lines[2:]
        self.assertGreaterEqual(len(data_rows), 5)


# ---------------------------------------------------------------------------
# Tests: CLI
# ---------------------------------------------------------------------------

class TestTraceExportCLI(unittest.TestCase):
    """CLI must accept --timing-model + --block + --cycles + --output and
    write a markdown file. Used by SKILL.md and anchor regeneration."""

    def test_cli_writes_output_file(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "trace.md"
            inputs_path = Path(td) / "inputs.json"
            inputs_path.write_text(json.dumps([
                {"start": 1, "done_signal": 0},
                {"start": 0, "done_signal": 0},
                {"start": 0, "done_signal": 1},
            ]))

            anchor_tm = REPO_ROOT / "src/claude_skills/vf-rtl/anchors/fsm_4state/timing_model.py"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")

            result = subprocess.run(
                [
                    sys.executable, "-m", "veriflow_dsl.trace_export",
                    "--timing-model", str(anchor_tm),
                    "--block", "fsm_4state",
                    "--cycles", "3",
                    "--inputs", str(inputs_path),
                    "--output", str(out_path),
                ],
                capture_output=True, text=True, env=env, timeout=15,
            )
            self.assertEqual(result.returncode, 0,
                             f"CLI failed:\nstdout={result.stdout}\nstderr={result.stderr}")
            self.assertTrue(out_path.exists(), "Output file was not written")
            content = out_path.read_text()
            self.assertIn("fsm_4state", content)
            self.assertIn("|", content)  # has a table

    def test_cli_runs_without_inputs_file(self):
        """Modules with no input ports should not require --inputs."""
        with tempfile.TemporaryDirectory() as td:
            tm_path = Path(td) / "tm.py"
            tm_path.write_text(
                "from veriflow_dsl import RegT, RegAssign, reg_next, vf_block\n"
                "@vf_block(type='sequential')\n"
                "def free_run(*, cnt: RegT = RegT('cnt', 4)) -> list[RegAssign]:\n"
                "    return [reg_next(cnt, cnt + 1)]\n"
            )
            out_path = Path(td) / "trace.md"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")

            result = subprocess.run(
                [
                    sys.executable, "-m", "veriflow_dsl.trace_export",
                    "--timing-model", str(tm_path),
                    "--block", "free_run",
                    "--cycles", "4",
                    "--output", str(out_path),
                ],
                capture_output=True, text=True, env=env, timeout=15,
            )
            self.assertEqual(result.returncode, 0,
                             f"stdout={result.stdout}\nstderr={result.stderr}")
            content = out_path.read_text()
            # cnt is 4-bit → decimal in body
            self.assertIn("free_run", content)


if __name__ == "__main__":
    unittest.main()
