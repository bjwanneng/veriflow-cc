"""Tests for state.py — stage ordering, summaries, validation, persistence."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

# Resolve the skills directory relative to this test file
_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-pipeline"
import sys
sys.path.insert(0, str(_SKILLS_DIR))

from state import (
    PipelineState, STAGE_ORDER, STAGE_PREREQUISITES,
    next_pending_stage, can_execute,
)


def test_stage_order_is_4_stages():
    """Pipeline must have exactly 4 stages."""
    assert len(STAGE_ORDER) == 4
    assert STAGE_ORDER == ["spec_golden", "codegen", "verify_fix", "lint_synth"]


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
        [sys.executable, str(_SKILLS_DIR / "state.py"), "/tmp/test", "invalid_stage"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "Unknown stage" in result.stderr


def test_cli_accepts_valid_stage():
    """CLI should accept spec_golden with --start."""
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [sys.executable, str(_SKILLS_DIR / "state.py"), tmp, "spec_golden", "--start"],
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
            [sys.executable, str(_SKILLS_DIR / "state.py"), tmp, "verify_fix"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "blocked" in result.stderr.lower() or "BLOCKED" in result.stdout


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
