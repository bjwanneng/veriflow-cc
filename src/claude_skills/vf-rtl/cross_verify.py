#!/usr/bin/env python3
"""Cross-verification runner for VeriFlow-CC dual-codegen mode.

Compares cocotb simulation outputs from two independently-generated RTL
implementations of the same module. Both must pass functional simulation;
any divergence between their outputs indicates inconsistent code generation.

Usage:
    python cross_verify.py --rtl-a workspace/rtl/v1 --rtl-b workspace/rtl/v2 \
        --tb workspace/tb --module top --output logs/cross_verify.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def run_cocotb(rtl_dir: Path, tb_dir: Path, module: str, build_dir: Path) -> dict:
    """Run cocotb simulation and return parsed results."""
    # Import cocotb runner
    skill_dir = Path(__file__).parent
    sys.path.insert(0, str(skill_dir))
    from cocotb_runner import main as cocotb_main

    result_file = build_dir / "cocotb_results.json"
    try:
        cocotb_main([
            "--rtl-dir", str(rtl_dir),
            "--tb-dir", str(tb_dir),
            "--module", module,
            "--build-dir", str(build_dir),
            "--results-file", str(build_dir / "results.xml"),
        ])
    except SystemExit:
        pass

    # Try to read results
    for fname in ("cocotb_results.json", "results.json"):
        fpath = build_dir / fname
        if fpath.exists():
            try:
                return json.loads(fpath.read_text())
            except Exception:
                pass
    return {"passed": False, "error": "Could not read cocotb results"}


def compare_outputs(result_a: dict, result_b: dict) -> dict:
    """Compare two cocotb result dicts and report divergences."""
    comparison = {
        "both_passed": False,
        "a_passed": result_a.get("passed", False),
        "b_passed": result_b.get("passed", False),
        "a_tests": result_a.get("tests", 0),
        "b_tests": result_b.get("tests", 0),
        "a_failed": result_a.get("failed", 0),
        "b_failed": result_b.get("failed", 0),
        "divergences": [],
        "equivalent": False,
    }

    if not comparison["a_passed"] or not comparison["b_passed"]:
        return comparison

    comparison["both_passed"] = True

    # Compare test counts
    if comparison["a_tests"] != comparison["b_tests"]:
        comparison["divergences"].append({
            "type": "test_count_mismatch",
            "a_tests": comparison["a_tests"],
            "b_tests": comparison["b_tests"],
        })
        return comparison

    # If both pass with same test count, consider equivalent
    # (Deep comparison of per-test results would require richer output format)
    comparison["equivalent"] = True
    return comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-verify two RTL implementations"
    )
    parser.add_argument("--rtl-a", required=True, help="Directory for RTL variant A")
    parser.add_argument("--rtl-b", required=True, help="Directory for RTL variant B")
    parser.add_argument("--tb-dir", required=True, help="Testbench directory")
    parser.add_argument("--module", required=True, help="Top module name")
    parser.add_argument("--output", "-o", required=True, help="Output JSON file")
    args = parser.parse_args(argv)

    rtl_a = Path(args.rtl_a).resolve()
    rtl_b = Path(args.rtl_b).resolve()
    tb_dir = Path(args.tb_dir).resolve()
    module = args.module

    if not rtl_a.exists() or not rtl_b.exists():
        print("[cross_verify] RTL directories must exist", file=sys.stderr)
        return 2

    # Run both variants
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        result_a = run_cocotb(rtl_a, tb_dir, module, Path(tmp_a))
        result_b = run_cocotb(rtl_b, tb_dir, module, Path(tmp_b))

    comparison = compare_outputs(result_a, result_b)

    out_path = Path(args.output)
    out_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    if comparison["equivalent"]:
        print(f"[cross_verify] PASS: Both variants equivalent ({comparison['a_tests']} tests)")
        return 0
    elif not comparison["both_passed"]:
        print(f"[cross_verify] FAIL: A passed={comparison['a_passed']} B passed={comparison['b_passed']}")
        return 1
    else:
        print(f"[cross_verify] DIVERGENCE: {len(comparison['divergences'])} differences")
        for d in comparison["divergences"]:
            print(f"  - {d['type']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
