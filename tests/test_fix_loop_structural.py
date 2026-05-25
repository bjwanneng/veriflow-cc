"""Tests for structured fix-loop detection in state.py.

Legacy detect_fix_loop used exact string matching on error signatures.
This meant that if a fix attempt shifted line numbers, the same root-cause
bug would appear as a "new" signature and the loop detector would miss it.

The structured signature format (classification, signal_root, cycle_offset)
is robust to line-number changes because it captures the semantic identity
of the bug rather than its textual location.
"""

import json
import sys
from pathlib import Path

# state.py lives in the skill directory, not in a package.
skill_dir = Path(__file__).resolve().parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(skill_dir))

from state import PipelineState


def _make_state() -> PipelineState:
    return PipelineState(project_dir="/tmp/test_fix_loop")


def test_structured_signature_detects_loop():
    """Same B_late bug on w_reg, offset -1 — detected after 2 occurrences."""
    s = _make_state()
    for _ in range(2):
        s.error_history.setdefault("verify_fix", [])
        s.error_history["verify_fix"].append({
            "time": 0.0,
            "errors": [("B_late", "w_reg", -1)],
        })
    assert s.detect_fix_loop("verify_fix", ("B_late", "w_reg", -1))


def test_structured_signature_ignores_line_changes():
    """Legacy string signatures would miss this; structured catches it."""
    s = _make_state()
    s.error_history["verify_fix"] = [
        {"time": 0.0, "errors": [("B_late", "w_reg", -1)]},
        {"time": 1.0, "errors": [("B_late", "w_reg", -1)]},
    ]
    assert s.detect_fix_loop("verify_fix", ("B_late", "w_reg", -1))


def test_structured_signature_requires_three_fields():
    """Tuples with wrong length are ignored — falls through safely."""
    s = _make_state()
    s.error_history["verify_fix"] = [
        {"time": 0.0, "errors": [("B_late", "w_reg")]},  # only 2 fields
        {"time": 1.0, "errors": [("B_late", "w_reg")]},
    ]
    # Should NOT detect loop — tuples are skipped, no string matches
    assert not s.detect_fix_loop("verify_fix", ("B_late", "w_reg", -1))


def test_structured_signature_different_signal_not_loop():
    """Same classification and offset but different signal — not a loop."""
    s = _make_state()
    s.error_history["verify_fix"] = [
        {"time": 0.0, "errors": [("B_late", "w_reg", -1)]},
        {"time": 1.0, "errors": [("B_late", "msg_reg", -1)]},
    ]
    assert not s.detect_fix_loop("verify_fix", ("B_late", "w_reg", -1))


def test_structured_signature_different_class_not_loop():
    """Same signal and offset but different classification — not a loop."""
    s = _make_state()
    s.error_history["verify_fix"] = [
        {"time": 0.0, "errors": [("B_late", "w_reg", -1)]},
        {"time": 1.0, "errors": [("A", "w_reg", -1)]},
    ]
    assert not s.detect_fix_loop("verify_fix", ("B_late", "w_reg", -1))


def test_legacy_string_still_works():
    """Non-Stage-3 errors (lint, syntax) still use exact string match."""
    s = _make_state()
    s.error_history["lint_synth"] = [
        {"time": 0.0, "errors": ["iverilog:line42:syntax error"]},
        {"time": 1.0, "errors": ["iverilog:line42:syntax error"]},
    ]
    assert s.detect_fix_loop("lint_synth", "iverilog:line42:syntax error")


def test_no_history_returns_false():
    """Empty history — never a loop."""
    s = _make_state()
    assert not s.detect_fix_loop("verify_fix", ("B_late", "w_reg", -1))


def test_single_occurrence_not_loop():
    """Only one prior error — not a loop yet."""
    s = _make_state()
    s.error_history["verify_fix"] = [
        {"time": 0.0, "errors": [("B_late", "w_reg", -1)]},
    ]
    assert not s.detect_fix_loop("verify_fix", ("B_late", "w_reg", -1))


def test_mixed_structured_and_legacy_errors():
    """History contains both structured and legacy signatures — both work."""
    s = _make_state()
    s.error_history["verify_fix"] = [
        {"time": 0.0, "errors": [("D", "state_reg", 0), "legacy:string"]},
        {"time": 1.0, "errors": [("D", "state_reg", 0), "legacy:string"]},
    ]
    assert s.detect_fix_loop("verify_fix", ("D", "state_reg", 0))
    assert s.detect_fix_loop("verify_fix", "legacy:string")
