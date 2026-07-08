"""Tests for candidate_selector.py — ranking + scoring plumbing."""

import sys
import tempfile
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from candidate_selector import select_best, score_candidate  # noqa: E402


# --- select_best: the ranking brain (pure) --------------------------------


def test_select_best_prefers_passing_then_fewest_cells():
    scores = [
        {"rtl": "cand0", "passed": False, "fails": 3, "cells": 100},
        {"rtl": "cand1", "passed": True, "fails": 0, "cells": 200},
        {"rtl": "cand2", "passed": True, "fails": 0, "cells": 150},
    ]
    assert select_best(scores)["rtl"] == "cand2"


def test_select_best_all_failing_picks_fewest_fails():
    scores = [
        {"rtl": "cand0", "passed": False, "fails": 5, "cells": 100},
        {"rtl": "cand1", "passed": False, "fails": 1, "cells": 300},
    ]
    assert select_best(scores)["rtl"] == "cand1"


def test_select_best_empty_returns_none():
    assert select_best([]) is None
    assert select_best([None, None]) is None


def test_select_best_cells_tiebreak_among_passing():
    scores = [
        {"rtl": "a", "passed": True, "fails": 0, "cells": 50},
        {"rtl": "b", "passed": True, "fails": 0, "cells": 40},
    ]
    assert select_best(scores)["rtl"] == "b"


# --- score_candidate: graceful degradation --------------------------------


def test_score_candidate_does_not_crash_on_bad_paths():
    """A bogus tb_dir must yield a score dict (passed=False), not an exception."""
    rtl = _SKILLS_DIR / "references" / "counter.v"
    with tempfile.TemporaryDirectory() as tmp:
        r = score_candidate(str(rtl), str(Path(tmp) / "no_such_tb"),
                            "counter", str(Path(tmp) / "build"))
    assert isinstance(r, dict)
    assert r["passed"] is False
    assert "cells" in r


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS  {name}")
    print("All candidate_selector tests passed.")
