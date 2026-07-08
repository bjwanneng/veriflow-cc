"""Tests for self_improve.py — the cross-run learning loop."""

import json
import sys
import tempfile
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from self_improve import SelfImprover  # noqa: E402


def _make_project(tmp, *, retry_verify=0, coverage=None, with_diag=False,
                  module_name="dut", rtl="module dut(input clk); endmodule\n"):
    proj = Path(tmp)
    (proj / ".veriflow").mkdir(parents=True, exist_ok=True)
    (proj / ".veriflow" / "pipeline_state.json").write_text(json.dumps({
        "project_dir": str(proj),
        "stages_completed": ["spec_golden", "codegen", "verify_fix", "lint_synth"],
        "retry_count": {"verify_fix": retry_verify},
    }))
    (proj / "workspace" / "docs").mkdir(parents=True, exist_ok=True)
    (proj / "workspace" / "docs" / "spec.json").write_text(json.dumps({
        "modules": [{"module_name": module_name, "ports": [
            {"name": "clk", "direction": "input"},
            {"name": "valid_in", "protocol": "valid", "ack_port": "ready_out"},
            {"name": "ready_out"}, {"name": "data_out", "direction": "output"},
        ]}],
    }))
    (proj / "workspace" / "rtl").mkdir(parents=True, exist_ok=True)
    (proj / "workspace" / "rtl" / f"{module_name}.v").write_text(rtl)
    (proj / "logs").mkdir(parents=True, exist_ok=True)
    if coverage is not None:
        (proj / "logs" / "functional_coverage.json").write_text(json.dumps({"ratio": coverage}))
    if with_diag:
        (proj / "logs" / "timing_diagnostic.json").write_text(json.dumps({
            "bug_class": "B_late", "divergence": {"signal": f"{module_name}.A_reg"},
        }))
    return proj


# --- record (Observe) -----------------------------------------------------


def test_record_appends_passed_first_try_and_snapshots_rtl():
    with tempfile.TemporaryDirectory() as proj_tmp, tempfile.TemporaryDirectory() as kb_tmp:
        proj = _make_project(proj_tmp, retry_verify=0, coverage=0.95)
        si = SelfImprover(kb_dir=kb_tmp)
        n = si.record(str(proj))
        assert n >= 1
        rec = json.loads(si.runs_file.read_text().strip().splitlines()[-1])
        assert rec["module"] == "dut"
        assert rec["passed_first_try"] is True
        assert rec["attempts_to_fix"] == 0
        assert rec["coverage_ratio"] == 0.95
        # RTL snapshot exists for the passing module
        snaps = list(si.artifacts_dir.glob("*.v"))
        assert snaps, "RTL not snapshotted for passed_first_try module"


def test_record_failed_first_try_records_bug_class_no_snapshot():
    with tempfile.TemporaryDirectory() as proj_tmp, tempfile.TemporaryDirectory() as kb_tmp:
        proj = _make_project(proj_tmp, retry_verify=2, with_diag=True)
        si = SelfImprover(kb_dir=kb_tmp)
        si.record(str(proj))
        rec = json.loads(si.runs_file.read_text().strip().splitlines()[-1])
        assert rec["passed_first_try"] is False
        assert rec["attempts_to_fix"] == 2
        # failed-first-try modules are NOT snapshotted (no reference candidate)
        assert not list(si.artifacts_dir.glob("*.v"))


# --- mine (Stage) ---------------------------------------------------------


def _seed_run(si, **kw):
    base = {"timestamp": "2026-01-01T00:00:00", "project": "p1", "module": "dut",
            "module_type": "handshake_valid_ready", "passed_first_try": True,
            "attempts_to_fix": 0, "bug_class": None, "signal_root": None,
            "fix_directive": None, "coverage_ratio": None, "synth_cells": None}
    base.update(kw)
    si._append_jsonl(si.runs_file, base)


def test_mine_reference_candidate_for_passing_high_coverage_module():
    with tempfile.TemporaryDirectory() as kb_tmp:
        si = SelfImprover(kb_dir=kb_tmp)
        _seed_run(si, project="p1", module="dut", module_type="handshake_valid_ready",
                  passed_first_try=True, coverage_ratio=0.95)
        (si.artifacts_dir / "p1__dut.v").write_text("module dut; endmodule\n")
        out = si.mine()
        assert any(c["type"] == "handshake_valid_ready" for c in out["references"])
        cand = out["references"][0]
        assert (si.staging_dir / "reference" / (cand["id"] + ".json")).exists()


def test_mine_skips_low_coverage_passing_module():
    with tempfile.TemporaryDirectory() as kb_tmp:
        si = SelfImprover(kb_dir=kb_tmp)
        _seed_run(si, passed_first_try=True, coverage_ratio=0.5)
        (si.artifacts_dir / "p1__dut.v").write_text("module dut; endmodule\n")
        out = si.mine()
        assert out["references"] == []


def test_mine_pattern_candidate_requires_recurrence_across_two_projects():
    with tempfile.TemporaryDirectory() as kb_tmp:
        si = SelfImprover(kb_dir=kb_tmp)
        for proj in ("p1", "p1", "p2"):  # 3 occurrences, 2 distinct projects
            _seed_run(si, project=proj, module="m", passed_first_try=False,
                      bug_class="B_late", signal_root="A_reg")
        out = si.mine()
        assert len(out["patterns"]) == 1
        assert out["patterns"][0]["signature"]["bug_class"] == "B_late"


def test_mine_pattern_needs_two_distinct_projects():
    with tempfile.TemporaryDirectory() as kb_tmp:
        si = SelfImprover(kb_dir=kb_tmp)
        for _ in range(3):
            _seed_run(si, project="p1", bug_class="B_late", signal_root="A_reg",
                      passed_first_try=False)
        out = si.mine()
        assert out["patterns"] == []  # only 1 project → not a cross-project pattern


# --- validate (Validate) -------------------------------------------------


def _stage(si, kind, cand):
    si._atomic_write_json(si.staging_dir / kind / (cand["id"] + ".json"), cand)


def test_validate_reference_accepts_synthesizable_snippet():
    import shutil
    if shutil.which("yosys") is None:
        import pytest
        pytest.skip("yosys not installed")
    with tempfile.TemporaryDirectory() as kb_tmp:
        si = SelfImprover(kb_dir=kb_tmp)
        _stage(si, "reference", {
            "id": "counter__p__c", "type": "counter", "source_project": "p",
            "source_module": "counter",
            "artifact": str(_SKILLS_DIR / "references" / "counter.v"),
            "coverage_ratio": 0.95, "validation": "pending",
        })
        si.validate()
        c = json.loads((si.staging_dir / "reference" / "counter__p__c.json").read_text())
        assert c["validation"] == "validated"


def test_validate_reference_rejects_broken_snippet():
    import shutil
    if shutil.which("yosys") is None:
        import pytest
        pytest.skip("yosys not installed")
    with tempfile.TemporaryDirectory() as kb_tmp:
        si = SelfImprover(kb_dir=kb_tmp)
        broken = Path(kb_tmp) / "broken.v"
        broken.write_text("module broken (\nendmodul\n")  # malformed
        _stage(si, "reference", {
            "id": "bad__p__b", "type": "generic", "source_project": "p",
            "source_module": "broken", "artifact": str(broken),
            "coverage_ratio": None, "validation": "pending",
        })
        si.validate()
        c = json.loads((si.staging_dir / "reference" / "bad__p__b.json").read_text())
        assert c["validation"] == "rejected"


def test_validate_pattern_well_formedness():
    with tempfile.TemporaryDirectory() as kb_tmp:
        si = SelfImprover(kb_dir=kb_tmp)
        _stage(si, "pattern", {
            "id": "pat__B_late__A_reg",
            "signature": {"bug_class": "B_late", "signal_root": "A_reg"},
            "recurrence": 4, "projects": ["p1", "p2"],
            "proposed_md_entry": "## Learned Pattern\n...",
            "validation": "pending",
        })
        si.validate()
        c = json.loads((si.staging_dir / "pattern" / "pat__B_late__A_reg.json").read_text())
        assert c["validation"] == "validated"


# --- promote (gated) — SAFETY PROPERTIES ---------------------------------


def _validated_ref(si, artifact):
    cand = {"id": "handshake_valid_ready__p__d", "type": "handshake_valid_ready",
            "source_project": "p", "source_module": "dut", "artifact": str(artifact),
            "coverage_ratio": 0.95, "validation": "validated"}
    _stage(si, "reference", cand)
    return cand


def test_promote_default_is_dry_run_no_hotpath_write():
    with tempfile.TemporaryDirectory() as kb_tmp, tempfile.TemporaryDirectory() as ref_tmp:
        si = SelfImprover(kb_dir=kb_tmp, references_dir=ref_tmp)
        _validated_ref(si, _SKILLS_DIR / "references" / "handshake_valid_ready.v")
        before = sorted(p.name for p in Path(ref_tmp).glob("*.v"))
        out = si.promote()  # no flags → dry-run
        assert out["mode"] == "dry-run"
        assert sorted(p.name for p in Path(ref_tmp).glob("*.v")) == before
        # a promotion request was written for human review
        assert any(si.requests_dir.glob("*.json"))


def test_promote_apply_moves_artifact_and_logs_previous():
    with tempfile.TemporaryDirectory() as kb_tmp, tempfile.TemporaryDirectory() as ref_tmp:
        si = SelfImprover(kb_dir=kb_tmp, references_dir=ref_tmp)
        _validated_ref(si, _SKILLS_DIR / "references" / "handshake_valid_ready.v")
        out = si.promote(apply_id="handshake_valid_ready__p__d")
        assert out["mode"] == "manual"
        learned = list(Path(ref_tmp).glob("*_learned_*.v"))
        assert learned, "no learned reference written"
        log = si._read_jsonl(si.log_file)
        assert log and log[-1]["candidate_id"] == "handshake_valid_ready__p__d"
        assert log[-1]["is_new"] is True


def test_promote_auto_refuses_without_benchmark_cmd():
    with tempfile.TemporaryDirectory() as kb_tmp, tempfile.TemporaryDirectory() as ref_tmp:
        si = SelfImprover(kb_dir=kb_tmp, references_dir=ref_tmp)
        si.benchmark_cmd = None  # simulate unset VF_BENCHMARK_CMD
        _validated_ref(si, _SKILLS_DIR / "references" / "handshake_valid_ready.v")
        out = si.promote(auto=True)
        assert out["refused"] is True
        assert not list(Path(ref_tmp).glob("*_learned_*.v"))


def test_promote_auto_rolls_back_on_regression():
    with tempfile.TemporaryDirectory() as kb_tmp, tempfile.TemporaryDirectory() as ref_tmp:
        si = SelfImprover(kb_dir=kb_tmp, references_dir=ref_tmp)
        si.benchmark_cmd = "echo skipped"  # set, but we override _run_benchmark below
        _validated_ref(si, _SKILLS_DIR / "references" / "handshake_valid_ready.v")
        seq = [0.9, 0.5]  # baseline then after-promotion (regression)
        si._run_benchmark = lambda: seq.pop(0)
        out = si.promote(auto=True)
        assert out["rolled_back"], f"expected rollback, got {out}"
        assert not list(Path(ref_tmp).glob("*_learned_*.v"))


def test_rollback_restores_previous_content():
    with tempfile.TemporaryDirectory() as kb_tmp:
        bp = Path(kb_tmp) / "bug_patterns.md"
        bp.write_text("ORIGINAL\n")
        si = SelfImprover(kb_dir=kb_tmp, bug_patterns_path=bp)
        _stage(si, "pattern", {
            "id": "pat__B_late__A_reg",
            "signature": {"bug_class": "B_late", "signal_root": "A_reg"},
            "recurrence": 4, "projects": ["p1", "p2"],
            "proposed_md_entry": "\n## Learned\n\nappended\n",
            "validation": "validated",
        })
        out = si.promote(apply_id="pat__B_late__A_reg")
        assert "## Learned" in bp.read_text()
        si.rollback(out["promotion_id"])
        assert bp.read_text() == "ORIGINAL\n"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS  {name}")
    print("All self_improve tests passed.")
