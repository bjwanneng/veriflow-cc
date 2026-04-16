"""Tests for state.py — stage ordering, summaries, validation, persistence."""

import json
import os
import tempfile
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "skills" / "vf-pipeline"))

from state import (
    PipelineState, STAGE_ORDER, STAGE_PREREQUISITES,
    next_pending_stage, can_execute,
)


def test_next_pending_empty():
    """Empty state → first stage is architect."""
    assert next_pending_stage([]) == "architect"


def test_next_pending_after_architect():
    assert next_pending_stage(["architect"]) == "microarch"


def test_next_pending_after_all():
    assert next_pending_stage(list(STAGE_ORDER)) is None


def test_can_execute_no_prereqs():
    """architect has no prereqs, always allowed."""
    ok, _ = can_execute("architect", [])
    assert ok


def test_can_execute_missing_prereqs():
    """coder needs architect + microarch + timing. Missing any → blocked."""
    ok, reason = can_execute("coder", ["architect"])
    assert not ok
    assert "microarch" in reason


def test_can_execute_all_prereqs_met():
    ok, _ = can_execute("coder", ["architect", "microarch", "timing"])
    assert ok


def test_validate_rejects_skip():
    """Trying to run coder when microarch hasn't run → BLOCKED."""
    s = PipelineState(project_dir="/tmp/test")
    s.stages_completed = ["architect"]
    ok, reason = s.validate_before_run("coder")
    assert not ok
    assert "microarch" in reason


def test_validate_allows_correct_order():
    s = PipelineState(project_dir="/tmp/test")
    s.stages_completed = ["architect", "microarch", "timing"]
    ok, _ = s.validate_before_run("coder")
    assert ok


# ── stage_summaries ─────────────────────────────────────────────────────


def test_mark_complete_saves_summary():
    """mark_complete should accept a summary string and store it."""
    s = PipelineState(project_dir="/tmp/test")
    s.stages_completed = []
    s.mark_complete("architect", {
        "success": True,
        "artifacts": ["workspace/docs/spec.json"],
        "summary": "ALU_4BIT: 8 operations, 4-bit datapath",
    })
    assert "architect" in s.stage_summaries
    assert s.stage_summaries["architect"] == "ALU_4BIT: 8 operations, 4-bit datapath"


def test_summary_persists_to_json():
    """Summaries should survive save/load cycle."""
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.mark_complete("architect", {
            "success": True,
            "summary": "Generated spec for FIFO buffer, 8-bit wide, 16 deep",
        })
        s.save()

        loaded = PipelineState.load(tmp)
        assert loaded.stage_summaries.get("architect") == "Generated spec for FIFO buffer, 8-bit wide, 16 deep"


def test_restore_context_from_summaries():
    """New session should be able to understand project state from summaries alone."""
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        s.mark_complete("architect", {"success": True, "summary": "UART TX: 115200 baud, 8N1, single clock domain"})
        s.mark_complete("microarch", {"success": True, "summary": "2 modules: uart_tx_top, baud_generator. No FSM, pure datapath."})
        s.save()

        loaded = PipelineState.load(tmp)
        # New session: what's done? what's next?
        assert loaded.stages_completed == ["architect", "microarch"]
        assert loaded.next_stage() == "timing"
        # Summaries give full picture
        assert "UART TX" in loaded.stage_summaries["architect"]
        assert "uart_tx_top" in loaded.stage_summaries["microarch"]


def test_mark_failed_no_summary():
    """Failed stage should not add a summary."""
    s = PipelineState(project_dir="/tmp/test")
    s.mark_failed("coder", {"success": False, "errors": ["syntax error at line 42"]})
    assert "coder" not in s.stage_summaries


# ── rollback ────────────────────────────────────────────────────────────


def test_rollback_clears_summaries():
    """Rolling back should clear summaries of removed stages."""
    s = PipelineState(project_dir="/tmp/test")
    s.mark_complete("architect", {"success": True, "summary": "spec done"})
    s.mark_complete("microarch", {"success": True, "summary": "microarch done"})
    s.mark_complete("timing", {"success": True, "summary": "timing done"})

    PipelineState.reset_stage(s, "microarch")

    assert "architect" in s.stage_summaries
    assert "microarch" not in s.stage_summaries
    assert "timing" not in s.stage_summaries
    assert s.stages_completed == ["architect"]
    assert s.next_stage() == "microarch"


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
