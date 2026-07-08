#!/usr/bin/env python3
"""Multi-candidate RTL selector for VeriFlow-CC (test-time scaling).

Stage 2 generates K candidate implementations per module; this tool simulates
each against the golden cocotb testbench, scores synthesis quality, and picks
the best (passing + fewest cells). Mirrors the S*/MAGE generate-K-then-select
pattern that lifts RTL pass@1 from ~60% to ~95%.

Scope (v1): self-contained modules (the DUT and any submodules live in one .v
file, as cocotb_runner already treats one module as the DUT). Multi-module
candidate sets are a documented v2 extension.

Usage:
    python candidate_selector.py --module top \\
        --candidates-dir workspace/rtl/.candidates \\
        --tb-dir workspace/tb --rtl-out workspace/rtl --build-dir workspace/sim_cand
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(_SKILL_DIR))

from synth_score import quick_synth


def _parse_runner_json(stdout: str) -> dict:
    """cocotb_runner prints a JSON summary as its last stdout line."""
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {}


def score_candidate(
    rtl_file: str, tb_dir: str, module: str, build_dir: str,
    timeout: int = 600,
) -> dict:
    """Score one candidate: run cocotb (function) + quick synth (cells).

    Returns {"rtl","passed","fails","cells","score"}. Never raises — a failed
    sim is reported as passed=False so select_best can rank it.
    """
    rtl_file = str(rtl_file)
    runner = str(_SKILL_DIR / "cocotb_runner.py")
    work = Path(build_dir) / "iso"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(rtl_file, work / Path(rtl_file).name)

    passed = False
    fails = 1
    try:
        proc = subprocess.run(
            [sys.executable, runner,
             "--rtl-dir", str(work),
             "--tb-dir", str(tb_dir),
             "--module", module,
             "--build-dir", str(work / "sim"),
             "--results-file", str(work / "sim" / "results.xml")],
            capture_output=True, text=True, timeout=timeout,
        )
        res = _parse_runner_json(proc.stdout)
        n_fail = res.get("failed", 1 if proc.returncode != 0 else 0)
        n_pass = res.get("passed", 0)
        fails = n_fail
        passed = (proc.returncode == 0) and n_fail == 0 and n_pass > 0
    except Exception:
        passed = False
        fails = 1

    synth = quick_synth(rtl_file, module, str(work / "synth"))
    cells = synth.get("cells", 0)
    return {
        "rtl": rtl_file,
        "passed": passed,
        "fails": fails,
        "cells": cells,
        "score": cells,
    }


def select_best(scores: list[dict | None]) -> dict | None:
    """Pick the best candidate.

    Ranking key: (not passed, fails, cells). Passing candidates all have
    fails==0 so cells decides among them; failing candidates rank by fewest
    fails first (closest to correct), then cells.
    """
    valid = [s for s in (scores or []) if s]
    if not valid:
        return None
    return min(
        valid,
        key=lambda s: (not s.get("passed", False), s.get("fails", 1 << 30), s.get("cells", 1 << 30)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select best RTL candidate")
    parser.add_argument("--module", required=True)
    parser.add_argument("--candidates-dir", required=True,
                        help="Dir holding <module>_cand{0..K-1}.v")
    parser.add_argument("--tb-dir", required=True)
    parser.add_argument("--rtl-out", required=True, help="Dir to write the winning <module>.v")
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)

    cdir = Path(args.candidates_dir)
    candidates = sorted(cdir.glob(f"{args.module}_cand*.v"))
    if not candidates:
        print(json.dumps({"error": f"no candidates for {args.module} in {cdir}"}))
        return 2

    Path(args.build_dir).mkdir(parents=True, exist_ok=True)
    scores = []
    for i, cand in enumerate(candidates):
        s = score_candidate(str(cand), args.tb_dir, args.module,
                            str(Path(args.build_dir) / f"c{i}"), timeout=args.timeout)
        s["index"] = i
        scores.append(s)
        print(f"[selector] cand{i}: passed={s['passed']} fails={s['fails']} cells={s['cells']}",
              file=sys.stderr)

    best = select_best(scores)
    out_dir = Path(args.rtl_out)
    out_dir.mkdir(parents=True, exist_ok=True)
    winner_path = out_dir / f"{args.module}.v"
    if best and best.get("passed"):
        shutil.copy(best["rtl"], winner_path)
    else:
        # No passing candidate — keep the fewest-fails / smallest one so Stage 3
        # can still try to fix it (better than an empty rtl dir).
        if best:
            shutil.copy(best["rtl"], winner_path)

    print(json.dumps({
        "module": args.module,
        "winner": best,
        "winner_path": str(winner_path),
        "all": scores,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
