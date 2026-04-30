#!/usr/bin/env python3
"""Pure-Verilog simulation runner for VeriFlow-CC pipeline.

Runs iverilog + vvp for a self-checking Verilog testbench. No cocotb dependency.

Usage:
    python3 iverilog_runner.py \\
        --rtl-dir     <path/to/workspace/rtl> \\
        --tb-file     <path/to/workspace/tb/tb_design.v> \\
        --module      <module_name> \\
        --build-dir   <path/to/build_dir> \\
        [--verbose]

Exit codes:
    0 — all tests passed (ALL TESTS PASSED in output)
    1 — one or more tests failed
    2 — environment error (iverilog not found, etc.)

Output (stdout):
    JSON object: {"tests": N, "passed": M, "failed": F, "vcd_path": "..."}
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def find_iverilog() -> str:
    """Find iverilog executable."""
    candidates = ["iverilog", "iverilog.exe"]
    # Check EDA_BIN from eda_env.sh if available
    eda_bin = os.environ.get("EDA_BIN", "")
    if eda_bin:
        for c in candidates:
            p = Path(eda_bin) / c
            if p.exists():
                return str(p)
    # Check PATH
    for c in candidates:
        found = shutil.which(c)
        if found:
            return found
    return ""


def find_vvp() -> str:
    """Find vvp executable."""
    candidates = ["vvp", "vvp.exe"]
    eda_bin = os.environ.get("EDA_BIN", "")
    if eda_bin:
        for c in candidates:
            p = Path(eda_bin) / c
            if p.exists():
                return str(p)
    for c in candidates:
        found = shutil.which(c)
        if found:
            return found
    return ""


def collect_rtl_sources(rtl_dir: Path) -> list[str]:
    """Find all Verilog source files in rtl_dir."""
    sources = sorted(rtl_dir.glob("*.v"))
    if not sources:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": f"No .v files found in {rtl_dir}"
        }))
        sys.exit(2)
    return [str(s) for s in sources]


def main():
    parser = argparse.ArgumentParser(
        description="Pure-Verilog simulation runner for VeriFlow-CC pipeline"
    )
    parser.add_argument("--rtl-dir", required=True,
                        help="Directory containing *.v RTL source files")
    parser.add_argument("--tb-file", required=True,
                        help="Path to Verilog testbench file (tb_<design>.v)")
    parser.add_argument("--module", required=True,
                        help="Verilog top-level module name (for reference)")
    parser.add_argument("--build-dir", required=True,
                        help="Build directory for compilation artifacts")
    parser.add_argument("--no-vcd", action="store_true",
                        help="Disable VCD waveform dump")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed output")
    args = parser.parse_args()

    rtl_dir = Path(args.rtl_dir).resolve()
    tb_file = Path(args.tb_file).resolve()
    build_dir = Path(args.build_dir).resolve()

    # Validate inputs
    if not tb_file.exists():
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": f"Testbench file not found: {tb_file}"
        }))
        sys.exit(2)

    build_dir.mkdir(parents=True, exist_ok=True)

    # Find executables
    iverilog_exe = find_iverilog()
    vvp_exe = find_vvp()

    if not iverilog_exe:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": "iverilog not found. Install Icarus Verilog or set EDA_BIN."
        }))
        sys.exit(2)

    if not vvp_exe:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": "vvp not found. Install Icarus Verilog or set EDA_BIN."
        }))
        sys.exit(2)

    # Collect RTL sources
    rtl_sources = collect_rtl_sources(rtl_dir)

    if args.verbose:
        print(f"[iverilog_runner] iverilog  : {iverilog_exe}", file=sys.stderr)
        print(f"[iverilog_runner] vvp       : {vvp_exe}", file=sys.stderr)
        print(f"[iverilog_runner] RTL dir   : {rtl_dir}", file=sys.stderr)
        print(f"[iverilog_runner] RTL files : {len(rtl_sources)}", file=sys.stderr)
        print(f"[iverilog_runner] TB file   : {tb_file}", file=sys.stderr)
        print(f"[iverilog_runner] Module    : {args.module}", file=sys.stderr)
        print(f"[iverilog_runner] Build dir : {build_dir}", file=sys.stderr)

    # Compile with iverilog
    # Note: use -g2005 for Verilog-2005 compatibility
    # Add timescale for proper clock timing
    output_vvp = str(build_dir / f"{args.module}.vvp")
    compile_cmd = [
        iverilog_exe,
        "-g2005",
        "-o", output_vvp,
        "-s", tb_file.stem,  # testbench module is top for simulation
    ]
    # Add timescale directive support
    compile_cmd.extend(["-DCOCOTB_SIM=0"])

    # Add all RTL sources and testbench
    compile_cmd.extend(rtl_sources)
    compile_cmd.append(str(tb_file))

    if args.verbose:
        print(f"[iverilog_runner] Compile cmd: {' '.join(compile_cmd)}", file=sys.stderr)

    try:
        result = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            cwd=str(build_dir),
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            print(json.dumps({
                "tests": 0, "passed": 0, "failed": 0,
                "error": f"iverilog compilation failed",
                "compile_stderr": result.stderr[:2000],
                "compile_stdout": result.stdout[:2000],
            }))
            if args.verbose:
                print(f"[iverilog_runner] COMPILE FAILED:", file=sys.stderr)
                print(result.stderr, file=sys.stderr)
            sys.exit(2)
        if result.stderr.strip() and args.verbose:
            print(f"[iverilog_runner] Compile warnings:\n{result.stderr}", file=sys.stderr)
    except Exception as e:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": f"iverilog execution error: {e}"
        }))
        sys.exit(2)

    if args.verbose:
        print(f"[iverilog_runner] Compilation successful, running simulation...", file=sys.stderr)

    # Run simulation with vvp
    sim_cmd = [vvp_exe, output_vvp]
    if not args.no_vcd:
        # VCD is generated by $dumpfile/$dumpvars in the testbench
        pass

    try:
        result = subprocess.run(
            sim_cmd,
            capture_output=True,
            text=True,
            cwd=str(build_dir),
            env=os.environ.copy(),
            timeout=120,  # 2-minute timeout
        )

        sim_output = result.stdout + result.stderr

        if args.verbose:
            print(f"[iverilog_runner] Simulation output:", file=sys.stderr)
            print(sim_output[:5000], file=sys.stderr)

    except subprocess.TimeoutExpired:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 1,
            "error": "Simulation timed out after 120 seconds"
        }))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 1,
            "error": f"vvp execution error: {e}"
        }))
        sys.exit(1)

    # Parse simulation output
    # Look for: "ALL TESTS PASSED" or "[FAIL]" or "FAILED: N"
    all_passed = "ALL TESTS PASSED" in sim_output
    fail_lines = re.findall(r'\[FAIL\].*', sim_output)
    failed_summary = re.search(r'FAILED:\s*(\d+)\s*assertion', sim_output)
    pass_lines = re.findall(r'\[PASS\].*', sim_output)

    num_passed = len(pass_lines)
    num_failed = len(fail_lines)
    if failed_summary:
        num_failed = max(num_failed, int(failed_summary.group(1)))
    num_tests = num_passed + num_failed

    # Find VCD file
    vcd_files = sorted(build_dir.glob("*.vcd"))
    vcd_path = str(vcd_files[0]) if vcd_files else None

    if num_failed > 0 or not all_passed:
        failures = []
        for fl in fail_lines:
            failures.append({"test": "verilog_tb", "message": fl})
        result = {
            "tests": num_tests,
            "passed": num_passed,
            "failed": num_failed,
            "vcd_path": vcd_path,
            "failures": failures,
        }
        print(json.dumps(result))
        sys.exit(1)
    else:
        result = {
            "tests": num_tests,
            "passed": num_passed,
            "failed": 0,
            "vcd_path": vcd_path,
        }
        print(json.dumps(result))
        sys.exit(0)


if __name__ == "__main__":
    main()
