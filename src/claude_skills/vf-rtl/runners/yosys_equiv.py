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
from pathlib import Path
from typing import Any


def _build_yosys_script(
    ref_path: str,
    impl_path: str,
    ref_top: str,
    impl_top: str | None = None,
) -> str:
    """Generate a Yosys script for equivalence checking.

    Args:
        ref_path: Path to reference Verilog.
        impl_path: Path to implementation Verilog.
        ref_top: Top module name in reference.
        impl_top: Top module name in implementation (defaults to ref_top).

    Returns:
        Yosys commands as a single string.
    """
    if impl_top is None:
        impl_top = ref_top

    # Approach: prep each side in its own namespace via `design -stash`,
    # then combine. This is the only reliable way to handle the common
    # case where both files define a top module with the same name.
    #
    # Why not a single design with two `prep -top` calls? `prep -top X`
    # internally runs `hierarchy -check -top X`, which prunes every module
    # not reachable from X. So the second prep would have already lost the
    # first design. Stashing each prepped side keeps them alive.
    #
    # Why not `-defer`? Deferred modules are stored as `$abstract\name`,
    # which the plain `rename name new_name` command cannot find.
    return f"""# VeriFlow Yosys equivalence check
read_verilog "{ref_path}"
prep -top {ref_top}
rename {ref_top} ref_top
design -stash veriflow_ref

design -reset
read_verilog "{impl_path}"
prep -top {impl_top}
rename {impl_top} impl_top
design -stash veriflow_impl

design -copy-from veriflow_ref -as ref_top ref_top
design -copy-from veriflow_impl -as impl_top impl_top

equiv_make ref_top impl_top equiv
opt -full equiv
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
    #    if yosys lists "gold.x != gate.x", the design is NOT equivalent even if
    #    a success banner also appears (some yosys builds print both on partial
    #    runs). This also stops "Found 0 unproven ..." from being misread below.
    for line in output.splitlines():
        s = line.strip()
        if ("unproven" in s.lower() and "!=" in s) or (
            s.startswith("gold.") and "!=" in s
        ):
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
            }

    yosys_path = shutil.which(yosys_bin)
    if yosys_path is None:
        return {
            "equivalent": None,
            "yosys_available": False,
            "yosys_returncode": None,
            "unproven": [],
            "error": f"Yosys not found: {yosys_bin}",
        }

    script = _build_yosys_script(
        str(ref_path), str(impl_path), top_name, impl_top
    )

    script_path = ""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ys", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        result = subprocess.run(
            [yosys_path, "-s", script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "equivalent": None,
            "yosys_available": True,
            "yosys_returncode": None,
            "unproven": [],
            "error": f"Yosys timed out after {timeout}s",
        }
    except Exception as e:
        return {
            "equivalent": None,
            "yosys_available": True,
            "yosys_returncode": None,
            "unproven": [],
            "error": str(e),
        }
    finally:
        Path(script_path).unlink(missing_ok=True)

    combined_output = result.stdout
    if result.stderr:
        combined_output += "\n--- STDERR ---\n" + result.stderr
    parsed = _parse_equiv_output(combined_output)
    parsed["yosys_available"] = True
    parsed["yosys_returncode"] = result.returncode
    if parsed["equivalent"] is None:
        # The yosys script ends with `equiv_status -assert`, which exits non-zero
        # when any $equiv cell is unproven. So exit 0 with no unproven lines means
        # equivalence held even if the success banner was worded unlike our known
        # phrases. Conservative: this can never turn a real FAIL (non-zero exit or
        # unproven cells) into a PASS.
        if result.returncode == 0 and not parsed["unproven"]:
            parsed["equivalent"] = True
        elif result.returncode != 0:
            parsed["error"] = f"Yosys exited with code {result.returncode}"

    return parsed


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
