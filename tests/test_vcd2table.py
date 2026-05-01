"""Tests for vcd2table CLI and golden diff behavior."""

import subprocess
import sys
import tempfile
from pathlib import Path


_PROJECT_DIR = Path(__file__).parent.parent
_SKILLS_DIR = _PROJECT_DIR / "src" / "claude_skills" / "vf-pipeline"
sys.path.insert(0, str(_SKILLS_DIR))


from vcd2table import build_cycle_table, run_golden_model_comparison  # noqa: E402


def _write_golden_model(tmp: str, body: str) -> str:
    path = Path(tmp) / "golden_model.py"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_golden_diff_reports_expected_zero_mismatch():
    """A golden expected value of zero is still a real assertion target."""
    with tempfile.TemporaryDirectory() as tmp:
        golden = _write_golden_model(
            tmp,
            "def run(test_vector_index=0):\n"
            "    return [{'data_out': 0}]\n",
        )
        cycle_snapshots = [(0, {"tb.data_out": "1"})]

        report = run_golden_model_comparison(
            golden, cycle_snapshots, ["tb.data_out"]
        )

        assert "FIRST DIVERGENCE: cycle 0" in report
        assert "golden=0x0" in report


def test_golden_diff_does_not_apply_cycle_offset_by_default():
    """Timing offsets should be reported, not silently aligned away."""
    with tempfile.TemporaryDirectory() as tmp:
        golden = _write_golden_model(
            tmp,
            "def run(test_vector_index=0):\n"
            "    return [{'data_out': 5}]\n",
        )
        cycle_snapshots = [
            (0, {"tb.data_out": "0"}),
            (1, {"tb.data_out": "101"}),
        ]

        report = run_golden_model_comparison(
            golden, cycle_snapshots, ["tb.data_out"]
        )

        assert "CYCLE OFFSET CANDIDATE: +1" in report
        assert "FIRST DIVERGENCE: cycle 0" in report


def test_build_cycle_table_preserves_unknown_values():
    """Unknown/high-impedance values must not be converted to numeric zero."""
    class FakeVCD:
        changes = {
            0: {"tb.clk": "0", "tb.data_out": "x"},
            5: {"tb.clk": "1"},
        }

    table, _ = build_cycle_table(
        FakeVCD(), ["tb.data_out"], [(0, 0)], {}, "tb.clk"
    )

    assert "| x" in table


def test_vcd2table_accepts_vcd_alias():
    """error_recovery.md may call vcd2table with --vcd."""
    with tempfile.TemporaryDirectory() as tmp:
        vcd = Path(tmp) / "tb.vcd"
        vcd.write_text(
            "$timescale 1ns $end\n"
            "$scope module tb $end\n"
            "$var wire 1 ! clk $end\n"
            "$var wire 8 # data_out $end\n"
            "$upscope $end\n"
            "$enddefinitions $end\n"
            "$dumpvars\n"
            "0!\n"
            "b00000001 #\n"
            "$end\n"
            "#5\n"
            "1!\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_SKILLS_DIR / "vcd2table.py"),
                "--vcd",
                str(vcd),
                "--signals",
                "data_out",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "VCD WAVEFORM TABLE" in result.stdout


def test_error_recovery_uses_working_vcd2table_command():
    content = (_SKILLS_DIR / "error_recovery.md").read_text(encoding="utf-8")

    assert "--sim-log logs/sim.log" in content
    assert "--output logs/wave_diff.txt" in content
    assert "--output logs/wave_table.txt" in content
