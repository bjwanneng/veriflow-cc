"""Tests for model_consistency_checker.py

Validates that timing_model.py and golden_model.py produce aligned traces
for the same inputs, and classifies mismatches correctly.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


# ---------------------------------------------------------------------------
# Helpers: write mock model files in a temp project dir
# ---------------------------------------------------------------------------

def _make_counter_timing_model(project_dir: Path, increment: int = 1) -> Path:
    """Write a counter timing_model.py that increments by *increment*."""
    tm = project_dir / "workspace" / "docs" / "timing_model.py"
    tm.parent.mkdir(parents=True, exist_ok=True)
    tm.write_text(
        f"""\
from veriflow_dsl import RegT, RegAssign, reg_next, mux, vf_block

@vf_block(type="sequential")
def counter(*, count_reg: RegT = RegT("count_reg", 8),
                  en: RegT = RegT("en", 1)) -> list[RegAssign]:
    return [reg_next(count_reg, mux(en, count_reg + {increment}, count_reg))]
"""
    )
    return tm


def _make_counter_golden_model(project_dir: Path, increment: int = 1) -> Path:
    """Write a matching golden_model.py.

    Records the count BEFORE increment so that cycle N matches the
    CycleSimulator snapshot (which captures register state BEFORE the
    NBA of the current cycle fires).
    """
    gm = project_dir / "workspace" / "docs" / "golden_model.py"
    gm.parent.mkdir(parents=True, exist_ok=True)
    gm.write_text(
        f"""\
def compute(inputs, trace=False):
    # Accept both {{"en": [...]}} (direct) and {{"en_sequence": [...]}} (legacy)
    en_seq = inputs.get("en")
    if en_seq is None:
        en_seq = inputs.get("en_sequence", [1, 1, 1, 0, 1])
    count = 0
    cycles = []
    for en in en_seq:
        if trace:
            cycles.append({{"count_reg": count}})
        if en:
            count = (count + {increment}) & 0xFF
    return cycles if trace else {{"count_reg": count}}


def run(test_vector_index=0):
    return compute({{}}, trace=True)
"""
    )
    return gm


def _make_counter_spec(project_dir: Path) -> Path:
    spec = project_dir / "workspace" / "docs" / "spec.json"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(
        json.dumps(
            {
                "modules": [
                    {
                        "module_name": "counter",
                        "ports": [
                            {"name": "clk", "direction": "input", "width": 1},
                            {"name": "rst", "direction": "input", "width": 1},
                            {"name": "en", "direction": "input", "width": 1},
                            {"name": "count_reg", "direction": "output", "width": 8},
                        ],
                        "timing_contract": {"pipeline_delay_cycles": 0},
                    }
                ]
            }
        )
    )
    return spec


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestModelConsistencyBasic(unittest.TestCase):
    """Checker correctly identifies matching and mismatching models."""

    def test_models_match(self):
        """When timing_model and golden_model agree, report passes."""
        from veriflow_dsl.model_consistency_checker import check_consistency

        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td)
            _make_counter_timing_model(project_dir, increment=1)
            _make_counter_golden_model(project_dir, increment=1)
            _make_counter_spec(project_dir)

            report = check_consistency(
                timing_model_path=project_dir / "workspace/docs/timing_model.py",
                golden_model_path=project_dir / "workspace/docs/golden_model.py",
                spec_path=project_dir / "workspace/docs/spec.json",
                block_name="counter",
                num_cycles=5,
            )
            self.assertTrue(report.passed, f"Expected pass, got: {report.errors}")
            self.assertEqual(len(report.errors), 0)

    def test_catches_algorithmic_mismatch(self):
        """Golden model computes +2 instead of +1 → algorithmic mismatch."""
        from veriflow_dsl.model_consistency_checker import check_consistency

        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td)
            _make_counter_timing_model(project_dir, increment=1)
            _make_counter_golden_model(project_dir, increment=2)  # mismatch
            _make_counter_spec(project_dir)

            report = check_consistency(
                timing_model_path=project_dir / "workspace/docs/timing_model.py",
                golden_model_path=project_dir / "workspace/docs/golden_model.py",
                spec_path=project_dir / "workspace/docs/spec.json",
                block_name="counter",
                num_cycles=5,
            )
            self.assertFalse(report.passed)
            algo_errs = [e for e in report.errors if e.category == "algorithmic"]
            self.assertGreaterEqual(
                len(algo_errs), 1,
                f"Expected algorithmic mismatch, got: {report.errors}",
            )

    def test_catches_missing_port(self):
        """Golden model omits a port declared in spec.json → missing_port error."""
        from veriflow_dsl.model_consistency_checker import check_consistency

        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td)
            _make_counter_timing_model(project_dir)
            gm = project_dir / "workspace/docs/golden_model.py"
            gm.parent.mkdir(parents=True, exist_ok=True)
            # Golden model forgets to include count_reg in trace
            gm.write_text(
                """\
def compute(inputs, trace=False):
    cycles = []
    for _ in range(5):
        if trace:
            cycles.append({"wrong_name": 0})
    return cycles if trace else {}

def run(test_vector_index=0):
    return compute({}, trace=True)
"""
            )
            _make_counter_spec(project_dir)

            report = check_consistency(
                timing_model_path=project_dir / "workspace/docs/timing_model.py",
                golden_model_path=project_dir / "workspace/docs/golden_model.py",
                spec_path=project_dir / "workspace/docs/spec.json",
                block_name="counter",
                num_cycles=5,
            )
            self.assertFalse(report.passed)
            port_errs = [e for e in report.errors if e.category == "missing_port"]
            self.assertGreaterEqual(len(port_errs), 1, f"Got: {report.errors}")

    def test_catches_timing_mismatch(self):
        """Golden model prepends an extra cycle → trace length mismatch (timing)."""
        from veriflow_dsl.model_consistency_checker import check_consistency

        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td)
            _make_counter_timing_model(project_dir)
            gm = project_dir / "workspace/docs/golden_model.py"
            gm.parent.mkdir(parents=True, exist_ok=True)
            # Golden model has an extra initial cycle (simulates 1-cycle offset)
            gm.write_text(
                """\
def compute(inputs, trace=False):
    en_seq = inputs.get("en")
    if en_seq is None:
        en_seq = inputs.get("en_sequence", [1, 1, 1, 0, 1])
    count = 0
    cycles = [{"count_reg": 0}]  # extra reset-like cycle
    for en in en_seq:
        if trace:
            cycles.append({"count_reg": count})
        if en:
            count = (count + 1) & 0xFF
    return cycles if trace else {"count_reg": count}

def run(test_vector_index=0):
    return compute({}, trace=True)
"""
            )
            _make_counter_spec(project_dir)

            report = check_consistency(
                timing_model_path=project_dir / "workspace/docs/timing_model.py",
                golden_model_path=project_dir / "workspace/docs/golden_model.py",
                spec_path=project_dir / "workspace/docs/spec.json",
                block_name="counter",
                num_cycles=5,
            )
            self.assertFalse(report.passed)
            timing_errs = [e for e in report.errors if e.category == "timing"]
            self.assertGreaterEqual(len(timing_errs), 1, f"Got: {report.errors}")


class TestModelConsistencyReportFormat(unittest.TestCase):
    """Report contains actionable fields for downstream prompt consumption."""

    def test_report_has_cycle_and_signal(self):
        from veriflow_dsl.model_consistency_checker import check_consistency

        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td)
            _make_counter_timing_model(project_dir, increment=1)
            _make_counter_golden_model(project_dir, increment=2)
            _make_counter_spec(project_dir)

            report = check_consistency(
                timing_model_path=project_dir / "workspace/docs/timing_model.py",
                golden_model_path=project_dir / "workspace/docs/golden_model.py",
                spec_path=project_dir / "workspace/docs/spec.json",
                block_name="counter",
                num_cycles=5,
            )
            self.assertFalse(report.passed)
            # Only algorithmic mismatches carry cycle/signal/value triples.
            algo_errs = [e for e in report.errors if e.category == "algorithmic"]
            self.assertGreaterEqual(len(algo_errs), 1, f"Got: {report.errors}")
            for err in algo_errs:
                self.assertIsNotNone(err.cycle, "Algorithmic error must reference a cycle")
                self.assertIsNotNone(err.signal, "Algorithmic error must reference a signal")
                self.assertIsNotNone(err.timing_value, "timing_model value must be present")
                self.assertIsNotNone(err.golden_value, "golden_model value must be present")


if __name__ == "__main__":
    unittest.main()
