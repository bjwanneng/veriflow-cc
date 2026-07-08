"""Tests for coverage_analyzer.py — functional coverage scoring + directives."""

import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from coverage_analyzer import extract_cover_goals, analyze, build_directives  # noqa: E402


_SPEC = {
    "modules": [{
        "module_name": "ctrl",
        "cycle_timing": [{"state": "IDLE"}, {"state": "RUN"}, {"state": "DONE"}],
        "ports": [
            {"name": "valid_in", "protocol": "valid", "ack_port": "ready_out"},
            {"name": "ready_out"},
        ],
    }],
}


def test_extract_cover_goals_fsm_and_handshake():
    goals = extract_cover_goals(_SPEC, "ctrl")
    states = [g for g in goals if g["kind"] == "fsm_state"]
    assert any(g["name"] == "IDLE" for g in states)
    assert any(g["name"] == "RUN" for g in states)
    assert any(g["name"] == "DONE" for g in states)
    assert any(g["kind"] == "handshake_combo" for g in goals)


def test_analyze_ratio_and_uncovered():
    # IDLE + RUN + handshake covered; DONE NOT covered.
    coverage = {
        "fsm:ctrl:IDLE": 3,
        "fsm:ctrl:RUN": 2,
        "hs:valid_in:ready_out": 1,
    }
    r = analyze(coverage, _SPEC, "ctrl")
    assert r["total"] == 4                 # IDLE, RUN, DONE + handshake
    assert r["covered"] == 3
    assert 0 < r["ratio"] < 1.0
    assert any("DONE" in u["name"] for u in r["uncovered"])


def test_analyze_full_coverage():
    coverage = {
        "fsm:ctrl:IDLE": 1, "fsm:ctrl:RUN": 1, "fsm:ctrl:DONE": 1,
        "hs:valid_in:ready_out": 1,
    }
    r = analyze(coverage, _SPEC, "ctrl")
    assert r["ratio"] == 1.0
    assert r["uncovered"] == []


def test_analyze_no_goals_is_na():
    spec = {"modules": [{"module_name": "x", "ports": [{"name": "a"}]}]}
    r = analyze({}, spec, "x")
    assert r["ratio"] is None   # N/A → loop skipped


def test_build_directives_mention_uncovered():
    coverage = {"fsm:ctrl:IDLE": 1}  # RUN, DONE, handshake uncovered
    r = analyze(coverage, _SPEC, "ctrl")
    d = build_directives(r["uncovered"])
    assert "RUN" in d and "DONE" in d


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS  {name}")
    print("All coverage_analyzer tests passed.")
