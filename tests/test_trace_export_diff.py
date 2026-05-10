"""Tests for trace_export diff mode.

Diff mode compresses long traces by omitting repeated values:
  - First row always shows full values.
  - Subsequent rows show '"' (same as previous) when a signal hasn't changed.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import unittest
from veriflow_dsl import Module, Signal, Const
from veriflow_dsl.trace_export import export_trace


def _build_counter8():
    """8-bit counter with enable."""
    m = Module("counter8")
    cnt = Signal(8, name="cnt", reset=0)
    en = Signal(1, name="en")
    m.add_input(en)
    m.add_output(cnt)
    m.add_signal(cnt)
    m.d.sync += cnt.eq(
        __import__("veriflow_dsl._types", fromlist=["Mux"]).Mux(en, cnt + Const(1, 8), cnt)
    )
    return m


class TestTraceExportDiffMode(unittest.TestCase):
    """export_trace(..., mode='diff') compresses stable signals."""

    def test_diff_mode_returns_string(self):
        m = _build_counter8()
        md = export_trace(m, cycles=4, inputs=[{"en": 0}] * 4, mode="diff")
        self.assertIsInstance(md, str)
        self.assertGreater(len(md), 0)

    def test_diff_mode_omits_unchanged(self):
        """cnt stays 0 when en=0 — diff mode should show '"' after first row."""
        m = _build_counter8()
        md = export_trace(m, cycles=4, inputs=[{"en": 0}] * 4, mode="diff")
        table_lines = [ln for ln in md.splitlines() if ln.startswith("|")]
        data_rows = table_lines[2:]  # skip header + separator
        self.assertGreaterEqual(len(data_rows), 2)
        # First data row has full values
        self.assertIn("0x00", data_rows[0])
        # Second row should use '"' for unchanged cnt
        # (en is also 0 every cycle, so it may also be '"')
        self.assertIn('"', data_rows[1])

    def test_diff_mode_shows_changes(self):
        """When cnt increments, the new value appears."""
        m = _build_counter8()
        md = export_trace(m, cycles=4, inputs=[{"en": 1}] * 4, mode="diff")
        table_lines = [ln for ln in md.splitlines() if ln.startswith("|")]
        data_rows = table_lines[2:]
        # Cycle 0: cnt=0x00, cycle 1: cnt=0x01, cycle 2: cnt=0x02 ...
        # Since it changes every cycle, no '"' should appear for cnt column.
        # Find the cnt column index
        headers = [h.strip() for h in table_lines[0].split("|")]
        try:
            cnt_idx = headers.index("cnt")
        except ValueError:
            self.fail("'cnt' not found in table headers")

        for row in data_rows[1:]:
            cells = [c.strip() for c in row.split("|")]
            if cnt_idx < len(cells):
                self.assertNotEqual(
                    cells[cnt_idx], '"',
                    f"cnt should show new value, not '\"' in row: {row}"
                )

    def test_diff_mode_meta_notes_compression(self):
        """Diff mode should mention the compression convention in meta block."""
        m = _build_counter8()
        md = export_trace(m, cycles=2, inputs=[{"en": 0}] * 2, mode="diff")
        meta_block = md.split("|", 1)[0]
        self.assertIn('"', meta_block)  # mention of "same as previous" notation

    def test_full_mode_unchanged(self):
        """Full mode (default) never uses '"'."""
        m = _build_counter8()
        md = export_trace(m, cycles=4, inputs=[{"en": 0}] * 4, mode="full")
        self.assertNotIn('"', md)

    def test_invalid_mode_raises(self):
        m = _build_counter8()
        with self.assertRaises(ValueError):
            export_trace(m, cycles=2, inputs=[{"en": 0}] * 2, mode="invalid")


if __name__ == "__main__":
    unittest.main()
