#!/usr/bin/env python3
"""Functional-coverage analyzer for VeriFlow-CC (coverage-driven verification).

The generated cocotb testbench instruments a small set of functional cover
points (FSM states visited, handshake valid/ready combos exercised) and dumps
them to coverage.json. This tool derives the cover GOALS from spec.json,
scores how many were hit, and — if below threshold — builds a directive for
vf-tb-gen to generate the missing directed tests. Closes the LLM4DV/ChatTest
coverage-feedback loop with zero external dependencies.

coverage.json shape (written by the TB): {"<point_key>": <hit_count>}

Usage:
    python coverage_analyzer.py --coverage logs/coverage.json \\
        --spec workspace/docs/spec.json --module <top>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _iter_modules(spec: dict):
    modules = spec.get("modules", [])
    if isinstance(modules, dict):
        return list(modules.values())
    return modules or []


def extract_cover_goals(spec: dict, module: str | None = None) -> list[dict]:
    """Derive functional cover goals from spec.json.

    Goals: every named FSM state (cycle_timing[].state) and every valid/ready
    handshake combo (port protocol=valid + ack_port). Scoped to `module` when
    given.
    """
    goals: list[dict] = []
    for mod in _iter_modules(spec):
        if module and mod.get("module_name") != module:
            continue
        mname = mod.get("module_name", "?")
        for ct in mod.get("cycle_timing") or []:
            state = ct.get("state") if isinstance(ct, dict) else None
            if state:
                goals.append({
                    "key": f"fsm:{mname}:{state}",
                    "kind": "fsm_state",
                    "name": str(state),
                    "desc": f"FSM state {state} of {mname} is reached",
                })
        for port in mod.get("ports") or []:
            if port.get("protocol") == "valid" and port.get("ack_port"):
                v = port.get("name", "?")
                r = port.get("ack_port")
                goals.append({
                    "key": f"hs:{v}:{r}",
                    "kind": "handshake_combo",
                    "name": f"{v}/{r}",
                    "desc": f"handshake {v} asserted with {r} observed",
                })
    return goals


def analyze(coverage: dict, spec: dict, module: str | None = None) -> dict:
    """Score coverage against spec-derived goals.

    Returns {"ratio": float|None, "covered": int, "total": int, "uncovered": [...]}.
    ratio is None when there are no goals (N/A — caller should skip the loop).
    """
    coverage = coverage or {}
    goals = extract_cover_goals(spec, module)
    if not goals:
        return {"ratio": None, "covered": 0, "total": 0, "uncovered": []}

    uncovered = [g for g in goals if coverage.get(g["key"], 0) <= 0]
    covered = len(goals) - len(uncovered)
    return {
        "ratio": round(covered / len(goals), 4),
        "covered": covered,
        "total": len(goals),
        "uncovered": uncovered,
    }


def build_directives(uncovered: list[dict]) -> str:
    """Turn uncovered goals into a vf-tb-gen directive for directed tests."""
    if not uncovered:
        return ""
    lines = [
        "COVERAGE DIRECTIVE — the following functional cover points were NOT",
        "exercised. Generate directed test vectors (add to TEST_VECTORS) that",
        "drive the DUT to hit each:",
        "",
    ]
    for g in uncovered:
        lines.append(f"- [{g['kind']}] {g['name']} — {g['desc']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze functional coverage")
    parser.add_argument("--coverage", required=True, help="coverage.json from the TB")
    parser.add_argument("--spec", required=True, help="spec.json")
    parser.add_argument("--module", default=None, help="scope to one module")
    args = parser.parse_args(argv)

    coverage_path = Path(args.coverage)
    coverage = json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.exists() else {}
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))

    result = analyze(coverage, spec, args.module)
    result["directives"] = build_directives(result["uncovered"])
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
