#!/usr/bin/env python3
"""Yosys equivalence checker — lightweight formal verification for VeriFlow-CC.

Uses Yosys equiv_* commands to prove that two Verilog modules are
functionally equivalent.  Best suited for combinational or simple
sequential blocks (single clock, synchronous reset).

Usage:
    python yosys_equiv.py --ref ref.v --impl impl.v --top MODULE_NAME
    python yosys_equiv.py --ref ref.v --impl impl.v --ref-top REF_TOP --impl-top IMPL_TOP

Exit codes:
    0  — equivalence proved (or yosys not available, skipped)
    1  — equivalence NOT proved (or error)
    2  — file/environment error
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def _build_yosys_script(
    ref_path: str,
    impl_path: str,
    ref_top: str,
    impl_top: str | None = None,
    *,
    clk2fflogic: bool = False,
    async2sync: bool = False,
    flatten: bool = False,
) -> str:
    """Generate a Yosys script for equivalence checking.

    Args:
        ref_path: Path to reference Verilog.
        impl_path: Path to implementation Verilog.
        ref_top: Top module name in reference.
        impl_top: Top module name in implementation (defaults to ref_top).
        clk2fflogic: Handle async-reset FFs ($adff) — convert clocked FFs to
            formal logic on the equiv module (inserted after equiv_make).
        async2sync: Convert async resets to sync on each side (after read_verilog).
        flatten: Dissolve hierarchy so submodule cells match across the two
            designs (inserted after equiv_make; exposes hierarchical/blackbox cells).

    With all flags False the original fixed recipe is emitted.
    """
    if impl_top is None:
        impl_top = ref_top

    # Approach: prep each side in its own namespace via `design -stash`,
    # then combine. This is the only reliable way to handle the common
    # case where both files define a top module with the same name.
    async_cmd = "async2sync\n" if async2sync else ""
    post_equiv = ""
    if flatten:
        post_equiv += "flatten equiv\n"
    if clk2fflogic:
        post_equiv += "clk2fflogic equiv\n"

    return f"""# VeriFlow Yosys equivalence check
read_verilog "{ref_path}"
{async_cmd}prep -top {ref_top}
rename {ref_top} ref_top
design -stash veriflow_ref

design -reset
read_verilog "{impl_path}"
{async_cmd}prep -top {impl_top}
rename {impl_top} impl_top
design -stash veriflow_impl

design -copy-from veriflow_ref -as ref_top ref_top
design -copy-from veriflow_impl -as impl_top impl_top

equiv_make ref_top impl_top equiv
{post_equiv}opt -full equiv
equiv_simple equiv
equiv_induct equiv
equiv_status -assert equiv
"""


def _parse_equiv_output(output: str) -> dict:
    """Parse Yosys equiv_status output.

    Returns:
        {"equivalent": bool|None, "unproven": [str], "raw": output}
    """
    result: dict[str, Any] = {
        "equivalent": None,
        "unproven": [],
        "raw": output,
    }

    # 1. Scan for concrete unproven-cell lines FIRST. These are authoritative:
    #    if yosys lists unproven cells, the design is NOT equivalent even if a
    #    success banner also appears (some yosys builds print both on partial
    #    runs). This also stops "Found 0 unproven ..." from being misread below.
    #    Covers two yosys phrasings: the legacy "gold.x != gate.x" form and the
    #    modern "Unproven $equiv ... \\y_gold [i] \\y_gate [i]" form.
    for line in output.splitlines():
        s = line.strip()
        if (s.lower().startswith("unproven $equiv")
                or ("unproven" in s.lower() and "!=" in s)
                or (s.startswith("gold.") and "!=" in s)):
            result["unproven"].append(s)
    if result["unproven"]:
        result["equivalent"] = False
        return result

    # 2. Affirmative PASS — accept the legacy yosys phrasings AND common
    #    rewordings so a future yosys version doesn't silently fall to UNKNOWN.
    #    (Safe to check now: step 1 already returned if any unproven cell existed.)
    pass_phrases = (
        "Equivalence successfully proved",
        "Equivalence successfully proven",
        "Equivalence checking succeeded",
        "Equivalence checking was successful",
        "proved equivalence",
    )
    if any(p in output for p in pass_phrases):
        result["equivalent"] = True
        return result

    # 3. Fallback: a "Found N unproven" summary line without per-cell detail.
    if result["equivalent"] is None:
        for line in output.splitlines():
            if "unproven" in line.lower():
                result["equivalent"] = False
                break

    return result


# Ordered strategies, most-likely-to-succeed first. clk2fflogic/async2sync
# handle async reset ($adff); flatten exposes hierarchical/blackbox cells so
# they can be matched across the two designs.
STRATEGIES = [
    {"name": "base"},
    {"name": "clk2fflogic", "clk2fflogic": True},
    {"name": "flatten", "flatten": True},
    {"name": "async2sync", "async2sync": True},
    {"name": "flatten+clk2fflogic", "flatten": True, "clk2fflogic": True},
]


def _detect_async_reset(verilog_path, top, yosys_path, timeout=30) -> bool:
    """Quick yosys probe: does the design contain $adff (async-reset FF)?"""
    script = f'read_verilog "{verilog_path}"\nprep -top {top}\nstat\n'
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ys", delete=False) as f:
            f.write(script)
            script_path = f.name
        try:
            r = subprocess.run([yosys_path, "-s", script_path],
                               capture_output=True, text=True, timeout=timeout)
            return "$adff" in (r.stdout or "")
        finally:
            Path(script_path).unlink(missing_ok=True)
    except Exception:
        return False


def _decide(tried: list[dict]) -> dict:
    """Pick the final verdict from a list of per-strategy attempts.

    Each attempt: {"name", "flatten", "equivalent", "unproven"}.
    Returns {equivalent, unproven, strategy_used, is_blackbox_limitation, message}.

    is_blackbox_limitation is True iff a non-flatten strategy reported unproven
    cells that then VANISHED under a flatten strategy — a hierarchical blackbox
    artifact (known yosys limitation), NOT functional inequivalence.
    """
    proven = [t for t in tried if t["equivalent"] is True]
    if proven:
        p = proven[0]
        non_flatten_had_unproven = any(
            (not t["flatten"]) and bool(t["unproven"]) for t in tried
        )
        is_bb = non_flatten_had_unproven and p["flatten"]
        return {
            "equivalent": True,
            "unproven": [],
            "strategy_used": p["name"],
            "is_blackbox_limitation": is_bb,
            "message": (
                "Equivalent after flattening hierarchy — earlier unproven cells "
                "were blackbox artifacts (known yosys limitation), not functional "
                "inequivalence."
            ) if is_bb else None,
        }
    counter = [t for t in tried if t["equivalent"] is False]
    if counter:
        return {
            "equivalent": False,
            "unproven": counter[0]["unproven"],
            "strategy_used": counter[0]["name"],
            "is_blackbox_limitation": False,
            "message": None,
        }
    return {
        "equivalent": None,
        "unproven": [],
        "strategy_used": tried[-1]["name"] if tried else None,
        "is_blackbox_limitation": False,
        "message": None,
    }


def _run_strategy(strat, ref_path, impl_path, top_name, impl_top,
                  yosys_path, timeout):
    """Run one yosys strategy. Returns (parsed, returncode, error_str|None)."""
    script = _build_yosys_script(
        str(ref_path), str(impl_path), top_name, impl_top,
        clk2fflogic=strat.get("clk2fflogic", False),
        async2sync=strat.get("async2sync", False),
        flatten=strat.get("flatten", False),
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ys", delete=False) as f:
        f.write(script)
        script_path = f.name
    try:
        _t0 = time.perf_counter()
        result = subprocess.run(
            [yosys_path, "-s", script_path],
            capture_output=True, text=True, timeout=timeout,
        )
        print(f"[TIMING] step=yosys_equiv strategy={strat.get('name')} "
              f"duration={time.perf_counter() - _t0:.2f}s", file=sys.stderr)
        rc = result.returncode
        err = None
    except subprocess.TimeoutExpired:
        return (_parse_equiv_output(""), None, f"Yosys timed out after {timeout}s")
    except Exception as e:
        return (_parse_equiv_output(""), None, str(e))
    finally:
        Path(script_path).unlink(missing_ok=True)

    combined = result.stdout
    if result.stderr:
        combined += "\n--- STDERR ---\n" + result.stderr
    parsed = _parse_equiv_output(combined)
    # equiv_status -assert exits non-zero on unproven; exit 0 with no unproven
    # means equivalence held even without a recognized success banner.
    if parsed["equivalent"] is None:
        if rc == 0 and not parsed["unproven"]:
            parsed["equivalent"] = True
        elif rc != 0:
            err = f"Yosys exited with code {rc}"
    return (parsed, rc, err)


def check_equivalence(
    ref_path: str | Path,
    impl_path: str | Path,
    top_name: str,
    impl_top: str | None = None,
    yosys_bin: str = "yosys",
    timeout: int = 60,
) -> dict:
    """Run Yosys equivalence check between two Verilog modules.

    Args:
        ref_path: Reference Verilog file.
        impl_path: Implementation Verilog file.
        top_name: Top module name in reference.
        impl_top: Top module name in implementation (defaults to top_name).
        yosys_bin: Yosys executable name or path.
        timeout: Max seconds to wait for Yosys.

    Returns:
        Dict with keys:
            - "equivalent": bool|None
            - "yosys_available": bool
            - "yosys_returncode": int|None
            - "unproven": list[str]
            - "error": str|None
    """
    ref_path = Path(ref_path)
    impl_path = Path(impl_path)

    for p in (ref_path, impl_path):
        if not p.exists():
            return {
                "equivalent": None,
                "yosys_available": False,
                "yosys_returncode": None,
                "unproven": [],
                "error": f"File not found: {p}",
                "strategy_used": None,
                "is_blackbox_limitation": False,
            }

    yosys_path = shutil.which(yosys_bin)
    if yosys_path is None:
        return {
            "equivalent": None,
            "yosys_available": False,
            "yosys_returncode": None,
            "unproven": [],
            "error": f"Yosys not found: {yosys_bin}",
            "strategy_used": None,
            "is_blackbox_limitation": False,
        }

    if impl_top is None:
        impl_top = top_name

    # Detect async-reset FFs; if present, try clk2fflogic-bearing strategies
    # first (they converge faster on $adff designs).
    has_async = (_detect_async_reset(ref_path, top_name, yosys_path) or
                 _detect_async_reset(impl_path, impl_top, yosys_path))
    strategies = list(STRATEGIES)
    if has_async:
        strategies.sort(key=lambda s: 0 if s.get("clk2fflogic") else 1)

    tried = []
    last_rc = None
    last_error = None
    for strat in strategies:
        parsed, rc, err = _run_strategy(
            strat, ref_path, impl_path, top_name, impl_top, yosys_path, timeout
        )
        last_rc = rc
        if err and last_error is None:
            last_error = err
        tried.append({
            "name": strat["name"],
            "flatten": strat.get("flatten", False),
            "equivalent": parsed["equivalent"],
            "unproven": parsed["unproven"],
        })
        if parsed["equivalent"] is True:
            break                       # proved — decide now
        # flatten couldn't clear the unproven cells → real counterexample; stop.
        if (parsed["equivalent"] is False and parsed["unproven"]
                and strat.get("flatten")):
            break

    decision = _decide(tried)
    result = {
        "equivalent": decision["equivalent"],
        "yosys_available": True,
        "yosys_returncode": last_rc,
        "unproven": decision["unproven"],
        "error": last_error,
        "strategy_used": decision["strategy_used"],
        "is_blackbox_limitation": decision["is_blackbox_limitation"],
    }
    if decision["message"]:
        result["message"] = decision["message"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Yosys equivalence checker for VeriFlow RTL"
    )
    parser.add_argument("--ref", required=True, help="Reference Verilog file")
    parser.add_argument("--impl", required=True, help="Implementation Verilog file")
    parser.add_argument("--top", required=True, help="Top module name in reference")
    parser.add_argument("--impl-top", help="Top module name in implementation (default: --top)")
    parser.add_argument("--yosys", default="yosys", help="Yosys executable (default: yosys)")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds (default: 60)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    result = check_equivalence(
        ref_path=args.ref,
        impl_path=args.impl,
        top_name=args.top,
        impl_top=args.impl_top,
        yosys_bin=args.yosys,
        timeout=args.timeout,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if not result["yosys_available"]:
            print(f"SKIP: {result.get('error', 'Yosys not available')}")
        elif result["equivalent"] is True:
            print("PASS: Equivalence proved.")
        elif result["equivalent"] is False:
            print("FAIL: Equivalence NOT proved.")
            for line in result.get("unproven", []):
                print(f"  {line}")
        else:
            print(f"UNKNOWN: {result.get('error', 'Could not determine equivalence')}")

    if result["equivalent"] is True:
        return 0
    if result["yosys_available"] is False:
        return 2  # Tool not available — distinguish from equivalence failure
    return 1


if __name__ == "__main__":
    sys.exit(main())
