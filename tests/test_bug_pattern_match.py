"""Tests for bug_pattern_match.match_patterns robustness on malformed input."""

import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from bug_pattern_match import match_patterns  # noqa: E402


def test_match_patterns_tolerates_non_dict_entries():
    """Non-dict entries (strings/None/int) must be skipped, not crash."""
    divergences = [
        "not a dict",
        None,
        42,
        {"signal": "data_latch_reg", "classification": "D",
         "expected": 0xDEAD, "actual": 0, "cycle": 1},
    ]
    # Should not raise; the one well-formed entry is still processed.
    matches = match_patterns(divergences)
    assert isinstance(matches, list)


def test_match_patterns_tolerates_missing_signal():
    """Entries missing 'signal' must be skipped so a matcher's d['signal']
    access can't KeyError and disable the matcher for the whole batch."""
    divergences = [
        {"classification": "D", "expected": 1, "actual": 0, "cycle": 0},  # no signal
        {"signal": "data_latch_reg", "classification": "D",
         "expected": 0xDEAD, "actual": 0, "cycle": 1},
    ]
    matches = match_patterns(divergences)
    # The latch-race matcher should still fire on the second entry.
    assert any(m.pattern_id == 1 for m in matches)


def test_match_patterns_empty_input():
    assert match_patterns([]) == []
    assert match_patterns(None) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS  {name}")
    print("All bug_pattern_match tests passed.")
