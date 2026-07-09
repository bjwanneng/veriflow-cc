#!/usr/bin/env python3
"""Benchmark runner for VeriFlow-CC — batch evaluation and reporting.

Usage:
    python benchmark_runner.py --project example_test/sm3/deepseek
    python benchmark_runner.py --compare example_test/sm3 --variants deepseek,glm4.7,glm5.1
    python benchmark_runner.py --all-projects example_test/
    python benchmark_runner.py --realbench /path/to/realbench.jsonl --output results.json

Outputs structured JSON with pass/fail breakdown, per-stage stats,
budget consumption, and LLM variant comparison.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
import contextlib


@dataclass
class ProjectResult:
    project_dir: str
    project_name: str
    stages_completed: list[str]
    sim_passed: bool | None = None
    lint_passed: bool | None = None
    synth_passed: bool | None = None
    equiv_passed: bool | None = None
    retry_count: int = 0
    fix_loops_detected: int = 0
    rtl_lines: int = 0
    rtl_modules: int = 0
    sim_log_path: str = ""
    lint_log_path: str = ""
    synth_report_path: str = ""
    timing_diagnostic_path: str = ""
    stage_timings: dict = field(default_factory=dict)
    total_duration_s: float | None = None
    retries_per_stage: dict = field(default_factory=dict)
    notes: list[str] = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []

    def overall_pass(self) -> bool:
        return self.sim_passed is True and self.lint_passed is not False


class BenchmarkRunner:
    """Evaluate one or more VeriFlow projects and aggregate results."""

    def __init__(self, skill_dir: str | Path | None = None):
        self.skill_dir = Path(skill_dir) if skill_dir else None

    # ------------------------------------------------------------------
    # Per-project analysis
    # ------------------------------------------------------------------

    def analyze_project(self, project_dir: str | Path) -> ProjectResult:
        """Parse a single project's state and logs into a result record."""
        p = Path(project_dir).resolve()
        name = p.name

        result = ProjectResult(
            project_dir=str(p),
            project_name=name,
            stages_completed=[],
            notes=[],
        )

        # --- pipeline_state.json --------------------------------------
        state_file = p / ".veriflow" / "pipeline_state.json"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
                result.stages_completed = state.get("stages_completed", [])
                _rc = state.get("retry_count", {}) or {}
                result.retries_per_stage = dict(_rc) if isinstance(_rc, dict) else {}
                result.retry_count = sum(_rc.values()) if isinstance(_rc, dict) else 0
                # Per-stage durations (keep duration_s; drop raw timestamps).
                _st = state.get("stage_timings", {}) or {}
                _inferred = []
                for _stage, _t in _st.items():
                    if isinstance(_t, dict):
                        if "duration_s" in _t:
                            result.stage_timings[_stage] = _t["duration_s"]
                        if _t.get("duration_inferred"):
                            _inferred.append(_stage)
                if _inferred:
                    result.notes.append(
                        f"timing inferred (no --start) for: {', '.join(_inferred)}"
                    )
                # Total duration: prefer start_time/last_updated; else sum stages.
                _start = state.get("start_time")
                _last = state.get("last_updated")
                if isinstance(_start, (int, float)) and isinstance(_last, (int, float)):
                    result.total_duration_s = round(_last - _start, 1)
                elif result.stage_timings:
                    result.total_duration_s = round(sum(result.stage_timings.values()), 1)
            except (json.JSONDecodeError, OSError) as e:
                result.notes.append(f"state parse error: {e}")
        else:
            result.notes.append("no pipeline_state.json found")

        # --- simulation log -------------------------------------------
        sim_log = p / "logs" / "sim.log"
        result.sim_log_path = str(sim_log) if sim_log.exists() else ""
        if sim_log.exists():
            content = sim_log.read_text(encoding="utf-8", errors="ignore")
            result.sim_passed = (
                "ALL TESTS PASSED" in content
                and "[FAIL]" not in content
                and "FAILED:" not in content
            )
        else:
            result.sim_passed = None

        # --- lint log -------------------------------------------------
        lint_log = p / "logs" / "lint.log"
        result.lint_log_path = str(lint_log) if lint_log.exists() else ""
        if lint_log.exists():
            content = lint_log.read_text(encoding="utf-8", errors="ignore")
            # Only flag as fail if there are actual error/warning lines
            # "no errors" / "0 errors" should NOT count as failure
            lower = content.lower()
            has_real_error = (
                ("error" in lower and "no errors" not in lower and "0 errors" not in lower)
                or "syntax error" in lower
            )
            result.lint_passed = not has_real_error
        else:
            result.lint_passed = None

        # --- synthesis report -----------------------------------------
        synth_report = p / "workspace" / "synth" / "synth_report.txt"
        result.synth_report_path = str(synth_report) if synth_report.exists() else ""
        if synth_report.exists():
            content = synth_report.read_text(encoding="utf-8", errors="ignore")
            result.synth_passed = "error" not in content.lower() or "synth" in content.lower()
            # Extract cell count
            for line in content.splitlines():
                if "Number of cells:" in line:
                    with contextlib.suppress(Exception):
                        result.notes.append(line.strip())
                    break
        else:
            result.synth_passed = None

        # --- equivalence check ----------------------------------------
        equiv_file = p / "logs" / "yosys_equiv_synth.json"
        if equiv_file.exists():
            try:
                equiv = json.loads(equiv_file.read_text(encoding="utf-8"))
                result.equiv_passed = equiv.get("equivalent")
            except Exception:
                result.equiv_passed = None

        # --- RTL stats ------------------------------------------------
        rtl_dir = p / "workspace" / "rtl"
        if rtl_dir.exists():
            v_files = list(rtl_dir.glob("*.v"))
            result.rtl_modules = len(v_files)
            result.rtl_lines = sum(
                len(f.read_text(encoding="utf-8").splitlines())
                for f in v_files
            )

        # --- timing diagnostic ----------------------------------------
        diag_file = p / "logs" / "timing_diagnostic.json"
        result.timing_diagnostic_path = str(diag_file) if diag_file.exists() else ""
        if diag_file.exists():
            try:
                diag = json.loads(diag_file.read_text(encoding="utf-8"))
                bug_class = diag.get("bug_class", "?")
                result.notes.append(f"timing_diagnostic: {bug_class}")
            except Exception:
                pass

        return result

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    def run_projects(self, project_dirs: list[str | Path]) -> list[ProjectResult]:
        """Analyze multiple projects and return results."""
        return [self.analyze_project(d) for d in project_dirs]

    def compare_variants(
        self,
        base_dir: str | Path,
        variants: list[str],
    ) -> dict:
        """Compare multiple LLM variants on the same base design."""
        base = Path(base_dir)
        results = []
        for variant in variants:
            variant_dir = base / variant
            if variant_dir.exists():
                results.append(self.analyze_project(variant_dir))
            else:
                results.append(ProjectResult(
                    project_dir=str(variant_dir),
                    project_name=variant,
                    stages_completed=[],
                    notes=["variant directory not found"],
                ))

        # Build comparison table
        return {
            "base_design": base.name,
            "variants": [r.project_name for r in results],
            "overall_pass": {r.project_name: r.overall_pass() for r in results},
            "rtl_lines": {r.project_name: r.rtl_lines for r in results},
            "rtl_modules": {r.project_name: r.rtl_modules for r in results},
            "retry_count": {r.project_name: r.retry_count for r in results},
            "per_variant": [asdict(r) for r in results],
        }

    def run_all_in_dir(self, root_dir: str | Path) -> list[ProjectResult]:
        """Find all project directories under root and analyze them."""
        root = Path(root_dir)
        # A project directory has .veriflow/pipeline_state.json
        project_dirs = [
            d.parent.parent
            for d in root.rglob(".veriflow/pipeline_state.json")
        ]
        # Also include immediate subdirs that look like projects
        for subdir in root.iterdir():
            if subdir.is_dir():
                state_file = subdir / ".veriflow" / "pipeline_state.json"
                if state_file.exists() and subdir not in project_dirs:
                    project_dirs.append(subdir)
        return self.run_projects(sorted(set(str(d) for d in project_dirs)))

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate(results: list[ProjectResult]) -> dict:
        """Compute aggregate statistics across all results."""
        total = len(results)
        passed = sum(1 for r in results if r.overall_pass())
        failed = total - passed
        sim_passed = sum(1 for r in results if r.sim_passed is True)
        lint_passed = sum(1 for r in results if r.lint_passed is not False)
        synth_done = sum(1 for r in results if r.synth_passed is not None)
        total_retries = sum(r.retry_count for r in results)
        total_lines = sum(r.rtl_lines for r in results)

        durations = [r.total_duration_s for r in results if r.total_duration_s is not None]
        avg_duration_s = round(sum(durations) / len(durations), 1) if durations else None
        per_stage_avg = {}
        for stage in ("spec_golden", "codegen", "verify_fix", "lint_synth"):
            vals = [r.stage_timings[stage] for r in results
                    if isinstance(r.stage_timings.get(stage), (int, float))]
            if vals:
                per_stage_avg[stage] = round(sum(vals) / len(vals), 1)

        return {
            "total_projects": total,
            "overall_pass": passed,
            "overall_fail": failed,
            "pass_rate": round(passed / total, 2) if total else 0,
            "sim_passed": sim_passed,
            "lint_passed": lint_passed,
            "synth_completed": synth_done,
            "total_retries": total_retries,
            "total_rtl_lines": total_lines,
            "total_duration_s_sum": sum(durations),
            "avg_duration_s": avg_duration_s,
            "per_stage_avg": per_stage_avg,
            "per_project": [asdict(r) for r in results],
        }

    @staticmethod
    def to_markdown(aggregate: dict) -> str:
        """Render aggregate results as Markdown."""
        lines = [
            "# VeriFlow Benchmark Report",
            "",
            f"**Projects evaluated**: {aggregate['total_projects']}",
            f"**Overall pass**: {aggregate['overall_pass']} / {aggregate['total_projects']} "
            f"({aggregate['pass_rate']:.0%})",
            f"**Simulation passed**: {aggregate['sim_passed']}",
            f"**Lint passed**: {aggregate['lint_passed']}",
            f"**Synthesis completed**: {aggregate['synth_completed']}",
            f"**Total retries**: {aggregate['total_retries']}",
            f"**Total RTL lines**: {aggregate['total_rtl_lines']}",
            "",
            "| Project | Stages | Sim | Lint | Synth | Lines | Notes |",
            "|---------|--------|-----|------|-------|-------|-------|",
        ]
        for r in aggregate["per_project"]:
            stages = ", ".join(r["stages_completed"]) if r["stages_completed"] else "—"
            sim = "PASS" if r["sim_passed"] else ("FAIL" if r["sim_passed"] is False else "—")
            lint = "PASS" if r["lint_passed"] else ("FAIL" if r["lint_passed"] is False else "—")
            synth = "PASS" if r["synth_passed"] else ("FAIL" if r["synth_passed"] is False else "—")
            notes = "; ".join(r["notes"][:2]) if r["notes"] else ""
            lines.append(
                f"| {r['project_name']} | {stages} | {sim} | {lint} | {synth} | "
                f"{r['rtl_lines']} | {notes} |"
            )

        # Timing section
        per_stage_avg = aggregate.get("per_stage_avg", {}) or {}
        total_dur = aggregate.get("total_duration_s_sum")
        avg = aggregate.get("avg_duration_s")
        lines.append("")
        lines.append("## Timing")
        if total_dur is not None:
            lines.append(f"**Total duration (sum)**: {round(total_dur, 1)}s")
        if avg is not None:
            lines.append(f"**Average per project**: {avg}s")
        if per_stage_avg:
            lines.append("")
            lines.append("| Stage | Avg (s) |")
            lines.append("|-------|---------|")
            for stage in ("spec_golden", "codegen", "verify_fix", "lint_synth"):
                if stage in per_stage_avg:
                    lines.append(f"| {stage} | {per_stage_avg[stage]} |")
        return "\n".join(lines)


# ------------------------------------------------------------------
# RealBench support
# ------------------------------------------------------------------

def parse_realbench_jsonl(path: str) -> list[dict]:
    """Parse RealBench JSONL format into task descriptors."""
    tasks = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return tasks


def realbench_to_project(task: dict, output_dir: Path) -> Path:
    """Convert a RealBench task into a VeriFlow project directory."""
    task_id = task.get("task_id", "unknown")
    proj = output_dir / task_id
    proj.mkdir(parents=True, exist_ok=True)

    # Write requirement.md
    requirement = task.get("description", task.get("prompt", ""))
    (proj / "requirement.md").write_text(requirement, encoding="utf-8")

    # Write constraints.md if available
    constraints = task.get("constraints", {})
    if constraints:
        lines = ["# Constraints", ""]
        for k, v in constraints.items():
            lines.append(f"- **{k}**: {v}")
        (proj / "constraints.md").write_text("\n".join(lines), encoding="utf-8")

    return proj


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def generate_pipeline_report(project_dir: str | Path) -> str:
    """Build a markdown pipeline_report.md for one project from its logs + state.

    Reads logs/sim.log, logs/lint.log, workspace/synth/synth_report.txt and
    .veriflow/pipeline_state.json. Missing artifacts render as N/A — never raises.
    Writes <project_dir>/pipeline_report.md and returns the body.
    """
    p = Path(project_dir).resolve()
    state = {}
    state_file = p / ".veriflow" / "pipeline_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    stages = state.get("stages_completed", []) or []
    st = state.get("stage_timings", {}) or {}
    retries = state.get("retry_count", {}) or {}
    start = state.get("start_time")
    last = state.get("last_updated")
    total = (round(last - start, 1)
             if isinstance(start, (int, float)) and isinstance(last, (int, float))
             else None)

    def _read(rel):
        f = p / rel
        return f.read_text(encoding="utf-8", errors="ignore") if f.exists() else ""

    sim = _read("logs/sim.log")
    lint = _read("logs/lint.log")
    synth = _read("workspace/synth/synth_report.txt")

    if sim and "ALL TESTS PASSED" in sim and "[FAIL]" not in sim and "FAILED:" not in sim:
        sim_verdict = "PASS"
    elif sim:
        sim_verdict = "FAIL"
    else:
        sim_verdict = "N/A"
    fail_line = next((ln.strip() for ln in sim.splitlines()
                      if "[FAIL]" in ln or "FAILED:" in ln), "")

    low = lint.lower()
    has_err = (("error" in low and "no errors" not in low and "0 errors" not in low)
               or "syntax error" in low)
    lint_verdict = "PASS" if (lint and not has_err) else ("FAIL" if lint else "N/A")
    cells = next((ln.strip() for ln in synth.splitlines() if "Number of cells:" in ln), "")

    lines = [
        f"# Pipeline Report — {p.name}",
        "",
        "## Summary",
        f"- Stages completed: {', '.join(stages) if stages else 'none'}",
        f"- Simulation: **{sim_verdict}**",
        f"- Lint: **{lint_verdict}**",
        f"- Synthesis: {cells or 'N/A'}",
        "",
        "## Timing",
    ]
    for stage in ("spec_golden", "codegen", "verify_fix", "lint_synth"):
        t = st.get(stage, {})
        if isinstance(t, dict):
            d = t.get("duration_s", "—")
            mark = " (inferred)" if t.get("duration_inferred") else ""
            lines.append(f"- {stage}: {d}s{mark}")
    lines.append(f"- **Total**: {total if total is not None else '—'}s")
    lines += [
        "",
        "## Simulation",
        ("ALL TESTS PASSED." if sim_verdict == "PASS"
         else (f"First failure: `{fail_line}`" if fail_line else "No simulation log.")),
        "",
        "## Retries",
    ]
    if retries:
        for k, v in retries.items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("None.")

    body = "\n".join(lines) + "\n"
    with contextlib.suppress(OSError):
        (p / "pipeline_report.md").write_text(body, encoding="utf-8")
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VeriFlow-CC benchmark runner")
    parser.add_argument("--project", help="Single project directory to evaluate")
    parser.add_argument("--compare", help="Base directory containing variant subdirs")
    parser.add_argument("--variants", help="Comma-separated variant names for --compare")
    parser.add_argument("--all-projects", help="Root directory — evaluate all projects found")
    parser.add_argument("--realbench", help="Path to RealBench JSONL file")
    parser.add_argument("--realbench-output", default="realbench_projects",
                        help="Directory to write RealBench project dirs (default: realbench_projects)")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--csv", help="Output CSV file path")
    parser.add_argument("--markdown", "-m", action="store_true",
                        help="Print Markdown report to stdout")
    parser.add_argument("--skill-dir", help="Path to installed skill directory")
    parser.add_argument("--report", help="Generate pipeline_report.md for a project dir and exit")
    args = parser.parse_args(argv)

    if args.report:
        generate_pipeline_report(args.report)
        print(f"[Benchmark] pipeline_report.md written to "
              f"{Path(args.report) / 'pipeline_report.md'}")
        return 0

    runner = BenchmarkRunner(skill_dir=args.skill_dir)

    # --- Single project ------------------------------------------------
    if args.project:
        result = runner.analyze_project(args.project)
        agg = BenchmarkRunner.aggregate([result])

    # --- Variant comparison --------------------------------------------
    elif args.compare and args.variants:
        variants = [v.strip() for v in args.variants.split(",")]
        comparison = runner.compare_variants(args.compare, variants)
        agg = comparison  # Already structured

    # --- All projects in directory -------------------------------------
    elif args.all_projects:
        results = runner.run_all_in_dir(args.all_projects)
        agg = BenchmarkRunner.aggregate(results)

    # --- RealBench -----------------------------------------------------
    elif args.realbench:
        tasks = parse_realbench_jsonl(args.realbench)
        output_dir = Path(args.realbench_output)
        output_dir.mkdir(parents=True, exist_ok=True)
        created = []
        for task in tasks:
            proj = realbench_to_project(task, output_dir)
            created.append(str(proj))
        agg = {
            "realbench_tasks": len(tasks),
            "projects_created": len(created),
            "project_dirs": created,
        }
        print(f"[RealBench] Created {len(created)} project directories in {output_dir}")

    else:
        parser.error("Specify one of: --project, --compare, --all-projects, --realbench")
        return 1

    # --- Output --------------------------------------------------------
    if args.output:
        Path(args.output).write_text(json.dumps(agg, indent=2), encoding="utf-8")
        print(f"[Benchmark] JSON report written to {args.output}")

    if args.csv and "per_project" in agg:
        csv_path = Path(args.csv)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            if agg["per_project"]:
                writer = csv.DictWriter(f, fieldnames=agg["per_project"][0].keys())
                writer.writeheader()
                writer.writerows(agg["per_project"])
        print(f"[Benchmark] CSV report written to {args.csv}")

    if args.markdown and "per_project" in agg:
        print(BenchmarkRunner.to_markdown(agg))
    elif not args.output and not args.csv:
        print(json.dumps(agg, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
