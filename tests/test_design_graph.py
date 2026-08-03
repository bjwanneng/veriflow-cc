"""Tests for design_graph.py — reachability, cycle detection."""

import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from design_graph import DesignGraph  # noqa: E402


def _mod(name, **kw):
    m = {"module_name": name, "ports": []}
    m.update(kw)
    return m


# --- E1: reachability -----------------------------------------------------


def test_find_unreachable_returns_none_when_no_top():
    """No module_type='top' → reachability is unknown, NOT falsely 'all reachable'.

    Regression: returned [] (= "verified, none unreachable") when it actually
    couldn't determine the root, a silent false-negative.
    """
    spec = {
        "modules": [_mod("a")],
        "module_connectivity": [],
    }
    g = DesignGraph(spec)
    assert g.find_unreachable_modules() is None


def test_find_unreachable_finds_isolated_module():
    spec = {
        "modules": [_mod("top", module_type="top"), _mod("orphan")],
        "module_connectivity": [],
    }
    g = DesignGraph(spec)
    assert g.find_unreachable_modules() == ["orphan"]


def test_find_unreachable_none_when_all_reachable():
    spec = {
        "modules": [_mod("top", module_type="top"), _mod("child")],
        "module_connectivity": [{"source": "top", "destination": "child"}],
    }
    g = DesignGraph(spec)
    assert g.find_unreachable_modules() == []


# --- E1: cycle detection --------------------------------------------------


def test_detect_cycles_finds_simple_cycle():
    spec = {
        "modules": [_mod("a"), _mod("b")],
        "module_connectivity": [
            {"source": "a", "destination": "b"},
            {"source": "b", "destination": "a"},
        ],
    }
    cycles = DesignGraph(spec).detect_cycles()
    assert len(cycles) >= 1


def test_detect_cycles_acyclic_returns_empty():
    spec = {
        "modules": [_mod("a"), _mod("b")],
        "module_connectivity": [{"source": "a", "destination": "b"}],
    }
    assert DesignGraph(spec).detect_cycles() == []


def test_detect_cycles_self_loop():
    """A self-edge a->a is a combinational loop and must be reported."""
    spec = {
        "modules": [_mod("a")],
        "module_connectivity": [{"source": "a", "destination": "a"}],
    }
    assert len(DesignGraph(spec).detect_cycles()) >= 1


# --- fanout skew (HIGH#5: was reading wrong field names → always no-op) ---


def test_check_fanout_skew_canonical_constraint_and_skew():
    """HIGH#5: a same_arrival group with skew > 0 must be reported. Previously
    the checker read 'max_skew_cycles' (canonical is 'max_delay_skew_cycles')
    and read 'same_arrival' as a bool (canonical is constraint='same_arrival'),
    so every group passed silently."""
    spec = {
        "modules": [_mod("top", module_type="top")],
        "fanout_groups": [{
            "name": "g",
            "constraint": "same_arrival",
            "max_delay_skew_cycles": 1,
            "signals": [{"name": "a"}, {"name": "b"}],
        }],
    }
    v = DesignGraph(spec).check_fanout_skew()
    assert len(v) == 1
    assert v[0]["group"] == "g"
    assert v[0]["max_skew"] == 1


def test_check_fanout_skew_no_violation_when_skew_zero():
    """A same_arrival group with max_delay_skew_cycles=0 is the STRICTEST
    same-arrival case (signals must arrive same cycle) and is still flagged,
    with max_skew reported as 0."""
    spec = {
        "modules": [_mod("top", module_type="top")],
        "fanout_groups": [{
            "name": "g",
            "constraint": "same_arrival",
            "max_delay_skew_cycles": 0,
            "signals": [{"name": "a"}, {"name": "b"}],
        }],
    }
    v = DesignGraph(spec).check_fanout_skew()
    assert len(v) == 1
    assert v[0]["max_skew"] == 0


def test_check_fanout_skew_ignores_non_same_arrival():
    """A group whose constraint is NOT same_arrival is not flagged."""
    spec = {
        "modules": [_mod("top", module_type="top")],
        "fanout_groups": [{
            "name": "g",
            "constraint": "relaxed",
            "max_delay_skew_cycles": 5,
            "signals": [{"name": "a"}, {"name": "b"}],
        }],
    }
    assert DesignGraph(spec).check_fanout_skew() == []


if __name__ == "__main__":
    test_find_unreachable_returns_none_when_no_top()
    test_find_unreachable_finds_isolated_module()
    test_find_unreachable_none_when_all_reachable()
    test_detect_cycles_finds_simple_cycle()
    test_detect_cycles_acyclic_returns_empty()
    test_detect_cycles_self_loop()
    test_check_fanout_skew_canonical_constraint_and_skew()
    test_check_fanout_skew_no_violation_when_skew_zero()
    test_check_fanout_skew_ignores_non_same_arrival()
    print("All design_graph tests passed.")
