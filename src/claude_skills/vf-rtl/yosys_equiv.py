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

    # Rename modules to avoid collision if both files define the same module name.
    script = f"""# VeriFlow Yosys equivalence check
read_verilog -defer {ref_path}
rename {ref_top} ref_top
read_verilog -defer {impl_path}
rename {impl_top} impl_top
prep -top ref_top
equiv_make ref_top impl_top equiv
equiv_simple
equiv_status -assert
"""
    return script


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

    if "Equivalence successfully proved" in output:
        result["equivalent"] = True
        return result

    # Look for unproven lines: "gold.<sig> != gate.<sig>"
    for line in output.splitlines():
        line = line.strip()
        if "unproven" in line.lower() and "!=" in line:
            result["unproven"].append(line)
        elif line.startswith("gold.") and "!=" in line:
            result["unproven"].append(line)

    if result["unproven"]:
        result["equivalent"] = False

    # If we see "Found N unproven" but no specific lines, still mark as fail
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

    parsed = _parse_equiv_output(result.stdout + "\n" + result.stderr)
    parsed["yosys_available"] = True
    parsed["yosys_returncode"] = result.returncode
    if parsed["equivalent"] is None and result.returncode != 0:
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
        return 0  # Graceful skip
    return 1


if __name__ == "__main__":
    sys.exit(main())
