"""Tests for timing_convention and fanout_skew checks in timing_contract_checker.py.

Covers:
- timing_convention offset >= max pipeline_delay_cycles
- Missing timing_convention (backward compat)
- offset < max delay -> error
- Fanout skew detection
- Fanout skew within tolerance
"""

import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from timing_contract_checker import check_timing_convention, check_fanout_skew


def _make_spec(offset=None, connectivity=None, fanout_groups=None):
    spec = {}
    if offset is not None:
        spec["timing_convention"] = {
            "golden_model": "software_instantaneous",
            "rtl": "post_nba_registered",
            "golden_to_rtl_offset_cycles": offset,
        }
    if connectivity is not None:
        spec["module_connectivity"] = connectivity
    if fanout_groups is not None:
        spec["fanout_groups"] = fanout_groups
    return spec


def _conn(src, dst, delay):
    return {
        "source": src,
        "destination": dst,
        "timing_contract": {
            "producer_type": "registered",
            "consumer_type": "sequential",
            "same_cycle_visible": False,
            "pipeline_delay_cycles": delay,
        },
    }


# --- timing_convention tests ---


def test_offset_matches_max_delay():
    """offset == max pipeline_delay -> pass."""
    spec = _make_spec(
        offset=2,
        connectivity=[
            _conn("a.x", "b.x", 1),
            _conn("a.y", "b.y", 2),
        ],
    )
    errors, warnings = check_timing_convention(spec)
    assert not errors, f"Expected no errors, got: {errors}"


def test_offset_less_than_max_delay():
    """offset < max pipeline_delay -> error."""
    spec = _make_spec(
        offset=0,
        connectivity=[
            _conn("a.x", "b.x", 1),
            _conn("a.y", "b.y", 2),
        ],
    )
    errors, warnings = check_timing_convention(spec)
    assert len(errors) == 1
    assert "golden_to_rtl_offset_cycles=0" in errors[0]
    assert "max pipeline_delay_cycles=2" in errors[0]


def test_missing_timing_convention():
    """No timing_convention -> no error (backward compat)."""
    spec = _make_spec(
        connectivity=[_conn("a.x", "b.x", 1)]
    )
    errors, warnings = check_timing_convention(spec)
    assert not errors


def test_no_connectivity():
    """timing_convention set but no connectivity -> pass."""
    spec = _make_spec(offset=1)
    errors, warnings = check_timing_convention(spec)
    assert not errors


def test_offset_missing_field():
    """timing_convention present but golden_to_rtl_offset_cycles not set -> warning."""
    spec = {
        "timing_convention": {
            "golden_model": "software_instantaneous",
            "rtl": "post_nba_registered",
        },
    }
    errors, warnings = check_timing_convention(spec)
    assert not errors
    assert any("golden_to_rtl_offset_cycles not set" in w for w in warnings)


# --- fanout skew tests ---


def test_fanout_skew_zero_delay():
    """Two signals with same delay -> pass."""
    spec = _make_spec(
        connectivity=[
            _conn("fsm.a", "sub.a", 1),
            _conn("fsm.b", "sub.b", 1),
        ],
        fanout_groups=[
            {
                "name": "same_delay",
                "common_source": "fsm.STATE_X",
                "signals": [
                    {"name": "sig_a", "path": "fsm.a -> sub.a"},
                    {"name": "sig_b", "path": "fsm.b -> sub.b"},
                ],
                "constraint": "same_arrival",
                "max_delay_skew_cycles": 0,
            }
        ],
    )
    errors, warnings = check_fanout_skew(spec)
    assert not errors, f"Expected no errors, got: {errors}"


def test_fanout_skew_within_tolerance():
    """Skew within max_delay_skew_cycles -> pass."""
    spec = _make_spec(
        connectivity=[
            _conn("fsm.a", "sub.a", 1),
            _conn("fsm.b", "sub.b", 2),
        ],
        fanout_groups=[
            {
                "name": "ok_group",
                "common_source": "fsm.STATE_X",
                "signals": [
                    {"name": "sig_a", "path": "fsm.a -> sub.a"},
                    {"name": "sig_b", "path": "fsm.b -> sub.b"},
                ],
                "constraint": "same_arrival",
                "max_delay_skew_cycles": 1,
            }
        ],
    )
    errors, warnings = check_fanout_skew(spec)
    assert not errors, f"Expected no errors, got: {errors}"


def test_fanout_group_missing():
    """No fanout_groups -> no error (backward compat)."""
    spec = _make_spec(
        connectivity=[_conn("a.x", "b.x", 1)]
    )
    errors, warnings = check_fanout_skew(spec)
    assert not errors


def test_fanout_empty_signals():
    """fanout_group with empty signals list -> no error."""
    spec = _make_spec(
        fanout_groups=[
            {
                "name": "empty",
                "common_source": "fsm.STATE_X",
                "signals": [],
                "constraint": "same_arrival",
                "max_delay_skew_cycles": 0,
            }
        ],
    )
    errors, warnings = check_fanout_skew(spec)
    assert not errors


if __name__ == "__main__":
    test_offset_matches_max_delay()
    test_offset_less_than_max_delay()
    test_missing_timing_convention()
    test_no_connectivity()
    test_offset_missing_field()
    test_fanout_skew_zero_delay()
    test_fanout_skew_within_tolerance()
    test_fanout_group_missing()
    test_fanout_empty_signals()
    print("All timing_convention + fanout_skew tests passed.")
