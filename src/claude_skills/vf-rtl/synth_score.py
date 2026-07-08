#!/usr/bin/env python3
"""Synthesis-quality scoring for VeriFlow-CC.

Parses a yosys `stat` report (or runs a quick `synth`) into a compact numeric
score used to rank RTL candidates and tie-break fixes. yosys generic synth
reports cell counts only (no area / critical path / max frequency without a
liberty file), so the score is cell-based: fewer cells = better, with FF and
MUX counts exposed for finer tie-breaking.

Usage:
    python synth_score.py --rtl workspace/rtl/top.v --module top
    python synth_score.py --report workspace/synth/synth_report.txt
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# Breakdown total: "  10158 cells"
_CELLS_TOTAL_RE = re.compile(r"^\s*(\d+)\s+cells\s*$", re.MULTILINE)
# Stats header summary: "Number of cells: 10158"
_NUM_CELLS_RE = re.compile(r"Number of cells:\s*(\d+)")
# Per-type line: "   1024   $_DFFE_PP_" — type names may contain underscores,
# so capture the whole "$_..._" token and strip the wrappers.
_CELL_TYPE_RE = re.compile(r"^\s+(\d+)\s+(\$_[A-Za-z0-9_]+_)\s*$", re.MULTILINE)


def parse_synth_report(text: str) -> dict:
    """Parse a yosys stat report into a score dict.

    Returns {"cells", "ffs", "mux", "logic", "score"}. All zero if no stats
    found (degrades gracefully so callers can still rank by other signals).
    """
    cells = 0
    m = _CELLS_TOTAL_RE.search(text) or _NUM_CELLS_RE.search(text)
    if m:
        cells = int(m.group(1))

    ffs = 0
    mux = 0
    for cm in _CELL_TYPE_RE.finditer(text):
        count = int(cm.group(1))
        token = cm.group(2)            # e.g. "$_DFFE_PP_"
        celltype = token[2:-1]         # strip "$_" prefix and trailing "_" -> "DFFE_PP"
        if "DFF" in celltype:          # $_DFF* / $_DFFE* / $_SDFF* / $_ADFF* ...
            ffs += count
        elif celltype.startswith("MUX"):
            mux += count

    logic = max(cells - ffs - mux, 0)
    return {
        "cells": cells,
        "ffs": ffs,
        "mux": mux,
        "logic": logic,
        "score": cells,   # fewer is better; FF/MUX exposed for tie-break
    }


def quick_synth(
    rtl_file: str, module: str, build_dir: str, yosys: str = "yosys",
    timeout: int = 120,
) -> dict:
    """Run `yosys -p 'read_verilog <rtl>; synth -top <module>; stat'` and score.

    Returns parse_synth_report() output plus "error" on failure. Mirrors the
    subprocess + timeout + cleanup discipline of yosys_equiv.check_equivalence.
    """
    yosys_path = shutil.which(yosys)
    if yosys_path is None:
        return {**parse_synth_report(""), "error": f"yosys not found: {yosys}"}

    Path(build_dir).mkdir(parents=True, exist_ok=True)
    script = (
        f"read_verilog \"{rtl_file}\"; "
        f"synth -top {module}; "
        f"stat"
    )
    try:
        result = subprocess.run(
            [yosys_path, "-p", script],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(build_dir),
        )
    except subprocess.TimeoutExpired:
        return {**parse_synth_report(""), "error": f"yosys timed out after {timeout}s"}
    except Exception as e:  # pragma: no cover - defensive
        return {**parse_synth_report(""), "error": str(e)}

    if result.returncode != 0:
        return {
            **parse_synth_report(result.stdout or ""),
            "error": f"yosys exited {result.returncode}: {(result.stderr or '')[:200]}",
        }
    return parse_synth_report(result.stdout or "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score RTL synthesis quality")
    parser.add_argument("--rtl", help="RTL .v file (runs a quick synth)")
    parser.add_argument("--module", help="Top module name (with --rtl)")
    parser.add_argument("--report", help="Existing yosys stat report to parse")
    args = parser.parse_args(argv)

    if args.report:
        text = Path(args.report).read_text(encoding="utf-8")
        print(json.dumps(parse_synth_report(text), indent=2))
        return 0
    if args.rtl and args.module:
        with tempfile.TemporaryDirectory() as tmp:
            r = quick_synth(args.rtl, args.module, tmp)
        print(json.dumps(r, indent=2))
        return 0 if "error" not in r else 2
    parser.error("provide --report or --rtl + --module")
    return 2  # unreachable: parser.error exits


if __name__ == "__main__":
    sys.exit(main())
