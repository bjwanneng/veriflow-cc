"""Unit tests for VeriFlow DSL trace comparison utilities."""

import sys
import os
import unittest


from veriflow_dsl._trace import diff_traces, TraceDiff


class TestDiffTraces(unittest.TestCase):
    """Test diff_traces() function."""

    def test_identical_traces(self):
        golden = [{"a": 0, "b": 1}, {"a": 1, "b": 2}]
        rtl = [{"a": 0, "b": 1}, {"a": 1, "b": 2}]
        result = diff_traces(golden, rtl)
        self.assertIsNone(result)

    def test_single_mismatch(self):
        golden = [{"a": 0, "b": 1}, {"a": 1, "b": 2}]
        rtl = [{"a": 0, "b": 1}, {"a": 1, "b": 99}]
        result = diff_traces(golden, rtl)
        self.assertIsNotNone(result)
        self.assertEqual(result.first_divergence_cycle, 1)
        self.assertEqual(result.first_divergence_signal, "b")
        self.assertEqual(result.expected, 2)
        self.assertEqual(result.actual, 99)
        self.assertEqual(result.total_mismatches, 1)

    def test_multiple_mismatches(self):
        golden = [{"a": 0}, {"a": 1}, {"a": 2}]
        rtl = [{"a": 0}, {"a": 9}, {"a": 8}]
        result = diff_traces(golden, rtl)
        self.assertIsNotNone(result)
        self.assertEqual(result.first_divergence_cycle, 1)
        self.assertEqual(result.total_mismatches, 2)

    def test_type_d_init_error(self):
        """actual=0, expected!=0 should classify as D (initialization)."""
        golden = [{"x": 5}]
        rtl = [{"x": 0}]
        result = diff_traces(golden, rtl)
        self.assertIsNotNone(result)
        self.assertEqual(result.classification, "D")
        self.assertEqual(result.first_divergence_signal, "x")
        self.assertEqual(result.expected, 5)
        self.assertEqual(result.actual, 0)

    def test_type_a_computation_error(self):
        """Mismatched non-zero values should classify as A."""
        golden = [{"x": 5}]
        rtl = [{"x": 3}]
        result = diff_traces(golden, rtl)
        self.assertIsNotNone(result)
        self.assertEqual(result.classification, "A")

    def test_type_b_timing_offset(self):
        """Value appears at wrong cycle should classify as B."""
        golden = [{"x": 0}, {"x": 5}, {"x": 5}]
        rtl = [{"x": 5}, {"x": 5}, {"x": 5}]  # x=5 arrives 1 cycle early
        result = diff_traces(golden, rtl)
        self.assertIsNotNone(result)
        # cycle 0: golden=0, rtl=5 → mismatch
        self.assertEqual(result.first_divergence_cycle, 0)
        # golden[1]["x"] == 5 == rtl[0]["x"] → timing offset detected → B_early
        self.assertEqual(result.classification, "B_early")

    def test_cycle_offset(self):
        """Skip golden cycles at start via cycle_offset."""
        golden = [{"x": 0}, {"x": 1}, {"x": 2}, {"x": 3}]
        rtl = [{"x": 2}, {"x": 3}]
        # With offset=2, golden[2] aligns with rtl[0]
        result = diff_traces(golden, rtl, cycle_offset=2)
        self.assertIsNone(result)  # should match

    def test_skip_signals(self):
        golden = [{"a": 0, "b": 99}, {"a": 1, "b": 99}]
        rtl = [{"a": 0, "b": 50}, {"a": 1, "b": 50}]
        result = diff_traces(golden, rtl, skip_signals={"b"})
        self.assertIsNone(result)  # b is skipped

    def test_different_lengths(self):
        """Comparison stops at the shorter trace."""
        golden = [{"x": 0}, {"x": 1}, {"x": 2}]
        rtl = [{"x": 0}]
        result = diff_traces(golden, rtl)
        self.assertIsNone(result)  # only 1 cycle compared, it matches

    def test_signal_not_in_rtl(self):
        """Golden signals missing from RTL are silently skipped."""
        golden = [{"a": 0, "b": 1}]
        rtl = [{"a": 0}]  # b is missing
        result = diff_traces(golden, rtl)
        self.assertIsNone(result)

    def test_empty_traces(self):
        result = diff_traces([], [])
        self.assertIsNone(result)


class TestTraceDiff(unittest.TestCase):
    """Test TraceDiff dataclass."""

    def test_construction(self):
        td = TraceDiff(
            first_divergence_cycle=5,
            first_divergence_signal="counter_reg",
            expected=10,
            actual=20,
            total_mismatches=3,
            classification="A",
        )
        self.assertEqual(td.first_divergence_cycle, 5)
        self.assertEqual(td.first_divergence_signal, "counter_reg")
        self.assertEqual(td.expected, 10)
        self.assertEqual(td.actual, 20)
        self.assertEqual(td.total_mismatches, 3)
        self.assertEqual(td.classification, "A")


class TestBugClassification(unittest.TestCase):
    """Test classification logic edge cases."""

    def _make_traces(self, golden_vals, rtl_vals):
        """Helper: build single-cycle traces."""
        golden = [{"val": v} for v in golden_vals]
        rtl = [{"val": v} for v in rtl_vals]
        return golden, rtl

    def test_zero_vs_nonzero_is_type_d(self):
        golden, rtl = self._make_traces([10], [0])
        result = diff_traces(golden, rtl)
        self.assertEqual(result.classification, "D")

    def test_nonzero_vs_different_nonzero_is_type_a(self):
        golden, rtl = self._make_traces([10], [20])
        result = diff_traces(golden, rtl)
        self.assertEqual(result.classification, "A")

    def test_timing_offset_detected(self):
        """Value 42 appears 1 cycle late."""
        golden = [{"val": 0}, {"val": 42}, {"val": 42}]
        rtl = [{"val": 0}, {"val": 0}, {"val": 42}]
        result = diff_traces(golden, rtl)
        self.assertIsNotNone(result)
        # cycle 1: golden=42, rtl=0
        # Type B check skipped (actual=0 would match trivially).
        # Type D: actual=0 && expected!=0 → initialization error.
        # Note: this could be a genuine timing offset (42 arrived 1 cycle late),
        # but without VCD x/z data we cannot distinguish. Falls to D as safest.
        self.assertEqual(result.classification, "D")

    def test_genuine_timing_offset_nonzero_values(self):
        """Timing offset with non-zero values (B detected correctly)."""
        golden = [{"val": 5}, {"val": 10}, {"val": 10}]
        rtl = [{"val": 10}, {"val": 10}, {"val": 10}]  # 10 arrives early
        result = diff_traces(golden, rtl)
        self.assertIsNotNone(result)
        self.assertEqual(result.classification, "B_early")
        self.assertEqual(result.expected, 5)
        self.assertEqual(result.actual, 10)


if __name__ == "__main__":
    unittest.main()
