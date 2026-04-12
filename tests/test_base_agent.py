"""Tests for agents/_base.py — check_prerequisites() validation."""

import json
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "agents"))

from _base import BaseAgent


class FakeAgent(BaseAgent):
    """Test agent with configurable stage name."""
    stage = "architect"

    def execute(self, context):
        return {"success": True}


# ── check_prerequisites ────────────────────────────────────────────────


def test_architect_needs_requirement():
    """architect checks: requirement.md must exist and be non-empty."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = FakeAgent()
        agent.stage = "architect"

        # No requirement.md → should fail
        ok, reason = agent.check_prerequisites(tmp)
        assert not ok
        assert "requirement.md" in reason

        # Create requirement.md with content
        Path(tmp, "requirement.md").write_text("# Design a 4-bit ALU with 8 operations", encoding="utf-8")
        ok, reason = agent.check_prerequisites(tmp)
        assert ok


def test_microarch_needs_spec_json():
    """microarch checks: workspace/docs/spec.json must exist and be valid JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = FakeAgent()
        agent.stage = "microarch"

        ok, reason = agent.check_prerequisites(tmp)
        assert not ok
        assert "spec.json" in reason

        # Create spec.json
        docs = Path(tmp, "workspace", "docs")
        docs.mkdir(parents=True)
        (docs / "spec.json").write_text('{"module_name": "alu"}', encoding="utf-8")
        ok, reason = agent.check_prerequisites(tmp)
        assert ok


def test_coder_needs_spec_and_timing():
    """coder checks: spec.json + timing_model.yaml must exist."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = FakeAgent()
        agent.stage = "coder"

        ok, reason = agent.check_prerequisites(tmp)
        assert not ok

        docs = Path(tmp, "workspace", "docs")
        docs.mkdir(parents=True)
        (docs / "spec.json").write_text('{"module_name": "alu"}', encoding="utf-8")
        (docs / "micro_arch.md").write_text("# Micro Architecture\n" + "x" * 100, encoding="utf-8")
        (docs / "timing_model.yaml").write_text("clock_mhz: 100", encoding="utf-8")

        ok, reason = agent.check_prerequisites(tmp)
        assert ok


def test_lint_needs_rtl_files():
    """lint checks: workspace/rtl/*.v must have at least one file."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = FakeAgent()
        agent.stage = "lint"

        ok, reason = agent.check_prerequisites(tmp)
        assert not ok
        assert "rtl" in reason.lower()

        rtl = Path(tmp, "workspace", "rtl")
        rtl.mkdir(parents=True)
        (rtl / "alu.v").write_text("module alu; endmodule", encoding="utf-8")
        ok, reason = agent.check_prerequisites(tmp)
        assert ok


def test_sim_needs_rtl_and_tb():
    """sim checks: rtl/*.v AND tb/tb_*.v must exist."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = FakeAgent()
        agent.stage = "sim"

        # Only RTL, no TB
        rtl = Path(tmp, "workspace", "rtl")
        rtl.mkdir(parents=True)
        (rtl / "alu.v").write_text("module alu; endmodule", encoding="utf-8")
        ok, reason = agent.check_prerequisites(tmp)
        assert not ok

        # Add testbench
        tb = Path(tmp, "workspace", "tb")
        tb.mkdir(parents=True)
        (tb / "tb_alu.v").write_text("module tb_alu; endmodule", encoding="utf-8")
        ok, reason = agent.check_prerequisites(tmp)
        assert ok


def test_debugger_needs_rtl_and_errors():
    """debugger checks: rtl files + context must have error info."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = FakeAgent()
        agent.stage = "debugger"

        # No RTL
        ok, reason = agent.check_prerequisites(tmp)
        assert not ok

        # Add RTL
        rtl = Path(tmp, "workspace", "rtl")
        rtl.mkdir(parents=True)
        (rtl / "alu.v").write_text("module alu; endmodule", encoding="utf-8")

        # No error context → still fail
        ok, reason = agent.check_prerequisites(tmp, context={})
        assert not ok

        # With error context
        ok, reason = agent.check_prerequisites(tmp, context={
            "error_log": "syntax error at line 5",
            "feedback_source": "lint",
        })
        assert ok


def test_unknown_stage_always_passes():
    """Unknown stage name → pass (don't block stages we don't know about)."""
    agent = FakeAgent()
    agent.stage = "custom_stage"
    ok, _ = agent.check_prerequisites("/tmp/whatever")
    assert ok


if __name__ == "__main__":
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
