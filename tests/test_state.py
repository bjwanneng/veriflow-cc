"""Tests for state.py — stage ordering, summaries, validation, persistence."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

# Resolve the skills directory relative to this test file
_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
import sys
sys.path.insert(0, str(_SKILLS_DIR))

from state import (
    PipelineState, STAGE_ORDER, STAGE_PREREQUISITES,
    next_pending_stage, can_execute,
)


def test_stage_order_is_4_stages():
    """Pipeline must have exactly 4 stages."""
    assert len(STAGE_ORDER) == 4
    assert STAGE_ORDER == ("spec_golden", "codegen", "verify_fix", "lint_synth")


def test_next_pending_empty():
    """Empty state → first stage is spec_golden."""
    assert next_pending_stage([]) == "spec_golden"


def test_next_pending_after_spec_golden():
    assert next_pending_stage(["spec_golden"]) == "codegen"


def test_next_pending_after_all():
    assert next_pending_stage(list(STAGE_ORDER)) is None


def test_can_execute_no_prereqs():
    """spec_golden has no prereqs, always allowed."""
    ok, _ = can_execute("spec_golden", [])
    assert ok


def test_can_execute_missing_prereqs():
    """verify_fix needs spec_golden + codegen. Missing any → blocked."""
    ok, reason = can_execute("verify_fix", ["spec_golden"])
    assert not ok
    assert "codegen" in reason


def test_can_execute_all_prereqs_met():
    ok, _ = can_execute("codegen", ["spec_golden"])
    assert ok


def test_validate_rejects_skip():
    """Trying to run verify_fix when codegen hasn't run → BLOCKED."""
    s = PipelineState(project_dir="/tmp/test")
    s.stages_completed = ["spec_golden"]
    ok, reason = s.validate_before_run("verify_fix")
    assert not ok
    assert "codegen" in reason


def test_validate_allows_correct_order():
    s = PipelineState(project_dir="/tmp/test")
    s.stages_completed = ["spec_golden", "codegen"]
    ok, _ = s.validate_before_run("verify_fix")
    assert ok


# ── stage_summaries ─────────────────────────────────────────────────────


def test_mark_complete_saves_summary():
    """mark_complete should accept a summary string and store it."""
    s = PipelineState(project_dir="/tmp/test")
    s.stages_completed = []
    s.mark_complete("spec_golden", {
        "success": True,
        "artifacts": ["workspace/docs/spec.json"],
        "summary": "ALU_4BIT: 8 operations, 4-bit datapath",
    })
    assert "spec_golden" in s.stage_summaries
    assert s.stage_summaries["spec_golden"] == "ALU_4BIT: 8 operations, 4-bit datapath"


def test_summary_persists_to_json():
    """Summaries should survive save/load cycle."""
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.mark_complete("spec_golden", {
            "success": True,
            "summary": "Generated spec for FIFO buffer, 8-bit wide, 16 deep",
        })
        s.save()

        loaded = PipelineState.load(tmp)
        assert loaded.stage_summaries.get("spec_golden") == "Generated spec for FIFO buffer, 8-bit wide, 16 deep"


def test_restore_context_from_summaries():
    """New session should be able to understand project state from summaries alone."""
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.mark_complete("spec_golden", {"success": True, "summary": "UART TX: 115200 baud, 8N1, single clock domain"})
        s.mark_complete("codegen", {"success": True, "summary": "2 modules: uart_tx_top, baud_generator. No FSM, pure datapath."})
        s.save()

        loaded = PipelineState.load(tmp)
        # New session: what's done? what's next?
        assert loaded.stages_completed == ["spec_golden", "codegen"]
        assert loaded.next_stage() == "verify_fix"
        # Summaries give full picture
        assert "UART TX" in loaded.stage_summaries["spec_golden"]
        assert "uart_tx_top" in loaded.stage_summaries["codegen"]


def test_mark_failed_no_summary():
    """Failed stage should not add a summary."""
    s = PipelineState(project_dir="/tmp/test")
    s.mark_failed("codegen", {"success": False, "errors": ["syntax error at line 42"]})
    assert "codegen" not in s.stage_summaries


# ── D3: auto-save consistency ──────────────────────────────────────────


def test_mark_complete_persists_without_explicit_save():
    """mark_complete must persist to disk even if the caller forgets save().

    mark_started already auto-saves; mark_complete/mark_failed must too, so a
    caller can't silently lose a stage transition.
    """
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.mark_complete("spec_golden", {"success": True, "summary": "done"})
        # NOTE: no s.save() call.
        reloaded = PipelineState.load(tmp)
        assert "spec_golden" in reloaded.stages_completed
        assert reloaded.get_output("spec_golden")["success"] is True


def test_mark_failed_persists_without_explicit_save():
    """mark_failed must persist to disk even if the caller forgets save()."""
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.mark_failed("spec_golden", {"success": False, "errors": ["boom"]})
        reloaded = PipelineState.load(tmp)
        assert "spec_golden" in reloaded.stages_failed


# ── rollback ────────────────────────────────────────────────────────────


def test_rollback_clears_summaries():
    """Rolling back should clear summaries of removed stages."""
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.mark_complete("spec_golden", {"success": True, "summary": "spec done"})
        s.mark_complete("codegen", {"success": True, "summary": "codegen done"})
        s.mark_complete("verify_fix", {"success": True, "summary": "verify done"})

        s.reset_stage("codegen")

        assert "spec_golden" in s.stage_summaries
        assert "codegen" not in s.stage_summaries
        assert "verify_fix" not in s.stage_summaries
        assert s.stages_completed == ["spec_golden"]
        assert s.next_stage() == "codegen"


# ── CLI validation ──────────────────────────────────────────────────────


def test_cli_rejects_invalid_stage():
    """CLI should reject unknown stage names."""
    result = subprocess.run(
        [sys.executable, str(_SKILLS_DIR / "core" / "state.py"), "/tmp/test", "invalid_stage"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "Unknown stage" in result.stderr


def test_cli_accepts_valid_stage():
    """CLI should accept spec_golden with --start."""
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [sys.executable, str(_SKILLS_DIR / "core" / "state.py"), tmp, "spec_golden", "--start"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "STARTED" in result.stdout


def test_is_pipeline_complete():
    """Pipeline complete only after lint_synth."""
    s = PipelineState(project_dir="/tmp/test")
    assert not s.is_pipeline_complete()
    s.stages_completed = ["spec_golden", "codegen", "verify_fix"]
    assert not s.is_pipeline_complete()
    s.stages_completed.append("lint_synth")
    assert s.is_pipeline_complete()


def test_mark_complete_returns_false_on_prereq_violation():
    """mark_complete must refuse and return False when prerequisites are not met."""
    s = PipelineState(project_dir="/tmp/test")
    s.stages_completed = []
    result = s.mark_complete("verify_fix", {"success": True})
    assert result is False
    assert "verify_fix" not in s.stages_completed


def test_mark_complete_returns_true_when_prereqs_met():
    """mark_complete returns True when prerequisites are satisfied."""
    s = PipelineState(project_dir="/tmp/test")
    s.stages_completed = ["spec_golden"]
    result = s.mark_complete("codegen", {"success": True})
    assert result is True
    assert "codegen" in s.stages_completed


def test_cli_blocks_prereq_violation():
    """CLI must exit non-zero when marking a stage out of order."""
    with tempfile.TemporaryDirectory() as tmp:
        # Try to mark verify_fix without codegen — should be blocked
        result = subprocess.run(
            [sys.executable, str(_SKILLS_DIR / "core" / "state.py"), tmp, "verify_fix"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "blocked" in result.stderr.lower() or "BLOCKED" in result.stdout


# ── validate_spec_completeness ──────────────────────────────────────────


def _make_spec_dir(tmp, spec_dict):
    """Write spec.json into tmp/workspace/docs/ and return tmp."""
    docs = Path(tmp) / "workspace" / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "spec.json").write_text(json.dumps(spec_dict))
    return tmp


def _minimal_spec():
    """A spec that passes all completeness checks."""
    return {
        "design_name": "test_mod",
        "modules": [
            {
                "module_name": "test_mod",
                "module_type": "top",
                "ports": [{"name": "clk", "direction": "input", "width": 1}],
            }
        ],
        "constraints": {"timing": {"target_frequency_mhz": 100}},
        "timing_convention": {
            "golden_model": "software_instantaneous",
            "rtl": "post_nba_registered",
            "golden_to_rtl_offset_cycles": 1,
        },
    }


def test_validate_spec_complete_passes():
    """Minimal valid spec should pass completeness check."""
    with tempfile.TemporaryDirectory() as tmp:
        _make_spec_dir(tmp, _minimal_spec())
        s = PipelineState(project_dir=tmp)
        ok, missing = s.validate_spec_completeness(tmp)
        assert ok, f"Expected complete but missing: {missing}"


def test_validate_spec_catches_missing_timing_convention():
    """Spec without timing_convention should be flagged."""
    spec = _minimal_spec()
    del spec["timing_convention"]
    with tempfile.TemporaryDirectory() as tmp:
        _make_spec_dir(tmp, spec)
        s = PipelineState(project_dir=tmp)
        ok, missing = s.validate_spec_completeness(tmp)
        assert not ok
        assert any("timing_convention" in m for m in missing)


def test_validate_spec_catches_missing_timing_contract():
    """Multi-module spec with connectivity missing timing_contract should be flagged."""
    spec = _minimal_spec()
    spec["modules"].append({
        "module_name": "sub_mod",
        "module_type": "leaf",
        "ports": [{"name": "clk", "direction": "input", "width": 1}],
    })
    spec["module_connectivity"] = [
        {"source": "test_mod", "destination": "sub_mod", "bus_width": 8}
    ]
    with tempfile.TemporaryDirectory() as tmp:
        _make_spec_dir(tmp, spec)
        s = PipelineState(project_dir=tmp)
        ok, missing = s.validate_spec_completeness(tmp)
        assert not ok
        assert any("timing_contract" in m for m in missing)


def test_validate_spec_catches_invalid_fanout_groups():
    """fanout_groups with missing fields should be flagged."""
    spec = _minimal_spec()
    spec["fanout_groups"] = [{"common_source": "fsm.STATE"}]  # missing name and signals
    with tempfile.TemporaryDirectory() as tmp:
        _make_spec_dir(tmp, spec)
        s = PipelineState(project_dir=tmp)
        ok, missing = s.validate_spec_completeness(tmp)
        assert not ok
        assert any("fanout_groups" in m for m in missing)


def test_validate_spec_accepts_valid_fanout_groups():
    """fanout_groups with correct structure should pass."""
    spec = _minimal_spec()
    spec["fanout_groups"] = [{
        "name": "ctrl_group",
        "common_source": "fsm.STATE_DONE",
        "signals": [{"name": "sig_a", "path": "a -> b"}],
        "constraint": "same_arrival",
        "max_delay_skew_cycles": 0,
    }]
    with tempfile.TemporaryDirectory() as tmp:
        _make_spec_dir(tmp, spec)
        s = PipelineState(project_dir=tmp)
        ok, missing = s.validate_spec_completeness(tmp)
        assert ok, f"Expected complete but missing: {missing}"


# ── detect_fix_loop exact matching ──────────────────────────────────


def test_detect_fix_loop_no_false_positive_on_similar_signatures():
    """Signatures like 'lint:line42' must NOT match 'lint:line421'."""
    s = PipelineState(project_dir="/tmp/test")
    # Record two failures with a similar but different signature
    s.error_history["verify_fix"] = [
        {"time": 1.0, "errors": ["cycle:5:signal:w_reg"]},
        {"time": 2.0, "errors": ["cycle:5:signal:w_reg_0"]},  # different signal
    ]
    # Exact match for first signature should NOT count the second one
    assert not s.detect_fix_loop("verify_fix", "cycle:5:signal:w_reg")


def test_detect_fix_loop_detects_exact_repeat():
    """Same exact error signature appearing twice should be detected."""
    s = PipelineState(project_dir="/tmp/test")
    s.error_history["verify_fix"] = [
        {"time": 1.0, "errors": ["cycle:5:signal:w_reg"]},
        {"time": 2.0, "errors": ["cycle:5:signal:w_reg"]},
    ]
    assert s.detect_fix_loop("verify_fix", "cycle:5:signal:w_reg")


def test_detect_fix_loop_single_occurrence_no_loop():
    """Single occurrence of a signature should NOT trigger loop detection."""
    s = PipelineState(project_dir="/tmp/test")
    s.error_history["verify_fix"] = [
        {"time": 1.0, "errors": ["cycle:5:signal:w_reg"]},
        {"time": 2.0, "errors": ["cycle:10:signal:hash_out"]},
    ]
    assert not s.detect_fix_loop("verify_fix", "cycle:5:signal:w_reg")


# =============================================================================
# WS1: structured cross-platform hook predicate (evaluate_hook)
# Lazy import keeps the existing 30 tests green during the TDD red phase.
# =============================================================================

def _eh(spec, project_dir):
    from state import evaluate_hook  # noqa: E402
    return evaluate_hook(spec, project_dir)


def test_hook_exists_present():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "a.txt").write_text("x")
        passed, _ = _eh({"exists": "a.txt"}, tmp)
        assert passed is True


def test_hook_exists_missing():
    with tempfile.TemporaryDirectory() as tmp:
        passed, detail = _eh({"exists": "nope.txt"}, tmp)
        assert passed is False
        assert "nope.txt" in detail


def test_hook_exists_directory_counts():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "sub").mkdir()
        passed, _ = _eh({"exists": "sub"}, tmp)
        assert passed is True


def test_hook_glob_default_min_one():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "rtl").mkdir()
        (Path(tmp) / "rtl" / "a.v").write_text("m")
        assert _eh({"glob": "rtl/*.v"}, tmp)[0] is True
        (Path(tmp) / "rtl" / "a.v").unlink()
        assert _eh({"glob": "rtl/*.v"}, tmp)[0] is False


def test_hook_glob_min_n():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "rtl").mkdir()
        for n in ("a.v", "b.v"):
            (Path(tmp) / "rtl" / n).write_text("m")
        assert _eh({"glob": "rtl/*.v", "min": 3}, tmp)[0] is False
        (Path(tmp) / "rtl" / "c.v").write_text("m")
        assert _eh({"glob": "rtl/*.v", "min": 3}, tmp)[0] is True


def test_hook_glob_no_match_detail():
    with tempfile.TemporaryDirectory() as tmp:
        _, detail = _eh({"glob": "rtl/*.v"}, tmp)
        assert "rtl/*.v" in detail


def test_hook_contains_hit_and_miss():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "sim.log"
        p.write_text("blah\nALL TESTS PASSED\n")
        assert _eh({"contains": "sim.log", "text": "ALL TESTS PASSED"}, tmp)[0] is True
        assert _eh({"contains": "sim.log", "text": "NOPE"}, tmp)[0] is False


def test_hook_contains_case_sensitive_default():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "f.log").write_text("error here")
        # default case=True: "ERROR" != "error"
        assert _eh({"contains": "f.log", "text": "ERROR"}, tmp)[0] is False
        # case=False: matches
        assert _eh({"contains": "f.log", "text": "ERROR", "case": False}, tmp)[0] is True


def test_hook_contains_missing_file_is_false_not_exception():
    with tempfile.TemporaryDirectory() as tmp:
        passed, detail = _eh({"contains": "missing.log", "text": "x"}, tmp)
        assert passed is False
        assert "missing.log" in detail


def test_hook_combinator_all():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "a").write_text("1")
        spec_all_pass = {"all": [{"exists": "a"}, {"contains": "a", "text": "1"}]}
        assert _eh(spec_all_pass, tmp)[0] is True
        spec_one_fail = {"all": [{"exists": "a"}, {"exists": "b"}]}
        assert _eh(spec_one_fail, tmp)[0] is False


def test_hook_combinator_all_short_circuits():
    """`all` stops at first failing predicate — second is not surfaced."""
    with tempfile.TemporaryDirectory() as tmp:
        spec = {"all": [{"exists": "first_missing"}, {"exists": "second_missing"}]}
        passed, detail = _eh(spec, tmp)
        assert passed is False
        assert "first_missing" in detail
        assert "second_missing" not in detail


def test_hook_combinator_any():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "a").write_text("1")
        assert _eh({"any": [{"exists": "nope"}, {"exists": "a"}]}, tmp)[0] is True
        assert _eh({"any": [{"exists": "nope"}, {"exists": "alsobgone"}]}, tmp)[0] is False


def test_hook_combinator_any_short_circuits():
    """`any` stops at first passing predicate — second is not surfaced."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "first").write_text("1")
        spec = {"any": [{"exists": "first"}, {"exists": "second"}]}
        passed, detail = _eh(spec, tmp)
        assert passed is True
        assert "first" in detail
        assert "second" not in detail


def test_hook_combinator_nested():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "rtl").mkdir()
        (Path(tmp) / "rtl" / "top.v").write_text("m")
        spec = {"all": [
            {"glob": "rtl/*.v", "min": 1},
            {"any": [{"exists": "rtl/missing.py"}, {"exists": "rtl/top.v"}]},
        ]}
        assert _eh(spec, tmp)[0] is True


def test_hook_unknown_predicate_returns_false():
    with tempfile.TemporaryDirectory() as tmp:
        passed, detail = _eh({"frobnicate": "x"}, tmp)
        assert passed is False
        assert "frobnicate" in detail


def test_hook_accepts_json_string_or_dict():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "a").write_text("1")
        import json as _json
        as_str = _json.dumps({"exists": "a"})
        assert _eh(as_str, tmp)[0] is True
        assert _eh({"exists": "a"}, tmp)[0] is True


def test_hook_malformed_json_returns_false():
    with tempfile.TemporaryDirectory() as tmp:
        passed, detail = _eh("{not valid json", tmp)
        assert passed is False
        assert detail  # non-empty explanation


def test_hook_not_a_dict_returns_false():
    """A JSON value that isn't an object (e.g. a list) is rejected."""
    with tempfile.TemporaryDirectory() as tmp:
        assert _eh('["exists", "a"]', tmp)[0] is False


# --- CLI integration (subprocess) ---

_STATE_PY = str(_SKILLS_DIR / "core" / "state.py")


def test_hook_back_compat_shell_path():
    """A non-JSON hook value (starts with 'test ') still runs as a shell command."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "marker").write_text("1")
        r = subprocess.run(
            [sys.executable, _STATE_PY, tmp, "spec_golden",
             "--hook=test -f marker"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "spec_golden → COMPLETE" in r.stdout


def test_hook_structured_via_cli():
    """JSON hook predicate marks the stage complete end-to-end."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "workspace" / "docs").mkdir(parents=True)
        (Path(tmp) / "workspace" / "docs" / "spec.json").write_text("{}")
        (Path(tmp) / "workspace" / "docs" / "golden_model.py").write_text("x=1")
        hook = '{"all":[{"exists":"workspace/docs/spec.json"},' \
               '{"exists":"workspace/docs/golden_model.py"}]}'
        r = subprocess.run(
            [sys.executable, _STATE_PY, tmp, "spec_golden", f"--hook={hook}"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "spec_golden → COMPLETE" in r.stdout
        state = json.loads((Path(tmp) / ".veriflow" / "pipeline_state.json").read_text())
        assert "spec_golden" in state["stages_completed"]


def test_hook_structured_fail_via_cli():
    """A failing JSON predicate does NOT mark the stage complete."""
    with tempfile.TemporaryDirectory() as tmp:
        hook = '{"exists":"workspace/docs/absent.json"}'
        r = subprocess.run(
            [sys.executable, _STATE_PY, tmp, "spec_golden", f"--hook={hook}"],
            capture_output=True, text=True,
        )
        assert "spec_golden → COMPLETE" not in r.stdout
        state = json.loads((Path(tmp) / ".veriflow" / "pipeline_state.json").read_text())
        assert "spec_golden" not in state["stages_completed"]


# =============================================================================
# WS2: accurate per-stage timing (previous-stage-end fallback + inferred flag)
# =============================================================================

def test_record_end_no_start_uses_previous_end():
    """A stage completed without --start falls back to the previous stage's end."""
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.mark_started("spec_golden")
        s.mark_complete("spec_golden", {"success": True, "summary": "x"})
        s.mark_complete("codegen", {"success": True, "summary": "x"})  # no mark_started
        t = s.stage_timings["codegen"]
        assert "duration_s" in t
        assert t.get("duration_inferred") is True


def test_record_end_explicit_start_not_inferred():
    """A stage with an explicit --start is NOT flagged inferred."""
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.mark_started("spec_golden")
        s.mark_complete("spec_golden", {"success": True, "summary": "x"})
        s.mark_started("codegen")
        s.mark_complete("codegen", {"success": True, "summary": "x"})
        t = s.stage_timings["codegen"]
        assert "duration_s" in t
        assert t.get("duration_inferred") is not True


def test_record_end_no_data_no_duration():
    """First stage with no start and no previous end has no duration_s."""
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.mark_complete("spec_golden", {"success": True, "summary": "x"})
        assert "duration_s" not in s.stage_timings["spec_golden"]


def test_previous_end_skips_middle_without_end():
    """_previous_end walks back to the nearest stage that has an end."""
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.stage_timings["spec_golden"] = {"end": 1000.0}
        s.stage_timings["codegen"] = {}  # present, but no end
        assert s._previous_end("verify_fix") == 1000.0
        assert s._previous_end("codegen") == 1000.0
        assert s._previous_end("spec_golden") is None


def test_all_four_stages_have_duration_cli():
    """End-to-end: every stage gets a duration_s when --start is called."""
    with tempfile.TemporaryDirectory() as tmp:
        for st in STAGE_ORDER:
            (Path(tmp) / f"m_{st}").write_text("1")
        for st in STAGE_ORDER:
            r1 = subprocess.run([sys.executable, _STATE_PY, tmp, st, "--start"],
                                capture_output=True, text=True)
            assert r1.returncode == 0, r1.stderr
            r2 = subprocess.run([sys.executable, _STATE_PY, tmp, st, f'--hook={{"exists":"m_{st}"}}'],
                                capture_output=True, text=True)
            assert r2.returncode == 0, (st, r2.stderr, r2.stdout)
        state = json.loads((Path(tmp) / ".veriflow" / "pipeline_state.json").read_text())
        for st in STAGE_ORDER:
            assert "duration_s" in state["stage_timings"][st], st
            assert state["stage_timings"][st]["duration_s"] >= 0


if __name__ == "__main__":
    # Run all tests
    import traceback
    passed = 0
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {name}: {e}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
