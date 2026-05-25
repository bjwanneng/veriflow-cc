"""Tests for benchmark_runner.py."""

import json
import tempfile
from pathlib import Path

# benchmark_runner.py lives in the skill directory
skill_dir = Path(__file__).resolve().parent.parent / "src" / "claude_skills" / "vf-rtl"
import sys
sys.path.insert(0, str(skill_dir))

from benchmark_runner import BenchmarkRunner, ProjectResult, parse_realbench_jsonl


def _make_project(tmp: Path, name: str, sim_pass: bool = True, stages: list[str] | None = None):
    """Create a mock project directory with state and logs."""
    proj = tmp / name
    proj.mkdir(parents=True)

    # pipeline_state.json
    veriflow = proj / ".veriflow"
    veriflow.mkdir()
    state = {
        "project_dir": str(proj),
        "stages_completed": stages or ["spec_golden", "codegen", "verify_fix", "lint_synth"],
        "retry_count": {"verify_fix": 1},
    }
    (veriflow / "pipeline_state.json").write_text(json.dumps(state), encoding="utf-8")

    # logs
    logs = proj / "logs"
    logs.mkdir()
    sim_log = "ALL TESTS PASSED\n" if sim_pass else "[FAIL] cycle=5 signal=x\n"
    (logs / "sim.log").write_text(sim_log, encoding="utf-8")
    (logs / "lint.log").write_text("No errors found.\n", encoding="utf-8")

    # RTL
    rtl = proj / "workspace" / "rtl"
    rtl.mkdir(parents=True)
    (rtl / f"{name}_top.v").write_text("module top(); endmodule\n", encoding="utf-8")

    # Synth report
    synth = proj / "workspace" / "synth"
    synth.mkdir(parents=True)
    (synth / "synth_report.txt").write_text("Number of cells: 42\n", encoding="utf-8")

    return proj


def test_analyze_passing_project():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp), "passing")
        runner = BenchmarkRunner()
        r = runner.analyze_project(proj)
        assert r.project_name == "passing"
        assert r.sim_passed is True
        assert r.lint_passed is True
        assert r.overall_pass() is True
        assert r.rtl_lines == 1
        assert r.rtl_modules == 1


def test_analyze_failing_project():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp), "failing", sim_pass=False)
        runner = BenchmarkRunner()
        r = runner.analyze_project(proj)
        assert r.sim_passed is False
        assert r.overall_pass() is False


def test_analyze_missing_state():
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "empty"
        proj.mkdir()
        runner = BenchmarkRunner()
        r = runner.analyze_project(proj)
        assert r.sim_passed is None
        assert "no pipeline_state.json" in r.notes[0]


def test_aggregate():
    with tempfile.TemporaryDirectory() as tmp:
        p1 = _make_project(Path(tmp), "p1", sim_pass=True)
        p2 = _make_project(Path(tmp), "p2", sim_pass=False)
        runner = BenchmarkRunner()
        results = [runner.analyze_project(p1), runner.analyze_project(p2)]
        agg = BenchmarkRunner.aggregate(results)
        assert agg["total_projects"] == 2
        assert agg["overall_pass"] == 1
        assert agg["overall_fail"] == 1
        assert agg["pass_rate"] == 0.5


def test_compare_variants():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "sm3"
        base.mkdir()
        _make_project(base, "deepseek", sim_pass=True)
        _make_project(base, "glm5.1", sim_pass=True)
        runner = BenchmarkRunner()
        comp = runner.compare_variants(base, ["deepseek", "glm5.1"])
        assert comp["base_design"] == "sm3"
        assert comp["overall_pass"]["deepseek"] is True
        assert comp["overall_pass"]["glm5.1"] is True


def test_parse_realbench_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "tasks.jsonl"
        lines = [
            json.dumps({"task_id": "add_8bit", "description": "8-bit adder"}),
            json.dumps({"task_id": "mux_4to1", "description": "4-to-1 mux"}),
        ]
        jsonl.write_text("\n".join(lines), encoding="utf-8")
        tasks = parse_realbench_jsonl(str(jsonl))
        assert len(tasks) == 2
        assert tasks[0]["task_id"] == "add_8bit"


def test_to_markdown():
    with tempfile.TemporaryDirectory() as tmp:
        p1 = _make_project(Path(tmp), "p1", sim_pass=True)
        runner = BenchmarkRunner()
        results = [runner.analyze_project(p1)]
        agg = BenchmarkRunner.aggregate(results)
        md = BenchmarkRunner.to_markdown(agg)
        assert "# VeriFlow Benchmark Report" in md
        assert "p1" in md
        assert "PASS" in md
