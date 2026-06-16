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


if __name__ == "__main__":
    test_find_unreachable_returns_none_when_no_top()
    test_find_unreachable_finds_isolated_module()
    test_find_unreachable_none_when_all_reachable()
    test_detect_cycles_finds_simple_cycle()
    test_detect_cycles_acyclic_returns_empty()
    test_detect_cycles_self_loop()
    print("All design_graph tests passed.")
