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


def golden_check(golden_path: str, verbose: bool = False) -> dict:
    """Run golden_model.py standalone and verify all test vectors pass.

    This runs BEFORE simulation to confirm the reference model is correct.
    If the golden model itself has bugs, any RTL comparison is meaningless.
    """
    golden_path = str(Path(golden_path).resolve())
    if not Path(golden_path).exists():
        return {"error": f"Golden model not found: {golden_path}", "passed": False}

    try:
        result = subprocess.run(
            [sys.executable, golden_path],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(golden_path).parent),
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return {"error": "Golden model timed out after 30s", "passed": False}
    except Exception as e:
        return {"error": f"Golden model execution error: {e}", "passed": False}

    # Check for [PASS] and [FAIL] markers
    pass_lines = [l for l in output.splitlines() if "[PASS]" in l]
    fail_lines = [l for l in output.splitlines() if "[FAIL]" in l]

    if verbose:
        print(f"[golden_check] Output:\n{output[:3000]}", file=sys.stderr)

    if fail_lines:
        return {
            "passed": False,
            "test_count": len(pass_lines) + len(fail_lines),
            "pass_count": len(pass_lines),
            "fail_count": len(fail_lines),
            "failures": fail_lines[:10],
            "output": output[:2000],
        }

    if result.returncode != 0:
        return {
            "passed": False,
            "error": f"Golden model exited with code {result.returncode}",
            "output": output[:2000],
        }

    return {
        "passed": True,
        "test_count": len(pass_lines),
        "pass_count": len(pass_lines),
        "fail_count": 0,
    }


_FAIL_PATTERN = re.compile(
    r'\[FAIL\]\s+'
    r'test=(\S+)\s+'
    r'vector=(\d+)\s+'
    r'cycle=(\d+)\s+'
    r'signal=(\S+)\s+'
    r'expected=(\S+)\s+'
    r'actual=(\S+)\s+'
    r'phase=(\S+)'
)


def _parse_fail_line(fl: str) -> dict:
    """Parse a structured [FAIL] line into a failure dict."""
    m = _FAIL_PATTERN.search(fl)
    if m:
        return {
            "test": m.group(1),
            "message": fl,
            "vector": int(m.group(2)),
            "cycle": int(m.group(3)),
            "signal": m.group(4),
            "expected": m.group(5),
            "actual": m.group(6),
            "phase": m.group(7),
        }
    # Fallback: legacy unstructured [FAIL] line
    fallback = {"test": "verilog_tb", "message": fl}
    m_cycle = re.search(r'cycle=(\d+)', fl)
    if m_cycle:
        fallback["cycle"] = int(m_cycle.group(1))
    return fallback


def _normalize_value(val: str) -> int | None:
    """Normalize a hex/decimal value string to int. Returns None for unknowns."""
    if not val:
        return None
    val = str(val).strip().lower().replace("_", "")
    if val.startswith("0x"):
        digits = val[2:]
        if any(c in digits for c in "xz"):
            return None
        try:
            return int(digits, 16)
        except ValueError:
            return None
    if any(c in val for c in "xz"):
        return None
    try:
        return int(val)
    except ValueError:
        return None


def _is_unknown(val: str) -> bool:
    """Check if a value string contains x/z unknown bits (not hex prefix)."""
    val = str(val).lower().replace("0x", "")
    return any(c in val for c in "xz")


def _find_value_in_golden(
    golden_cycles: dict[int, dict[str, str]],
    signal: str,
    actual_raw: str,
    expected_cycle: int,
    search_window: int = 5,
) -> int | None:
    """Search golden trace for a cycle where signal matches actual value."""
    actual_norm = _normalize_value(actual_raw)
    if actual_norm is None:
        return None
    for offset in range(-search_window, search_window + 1):
        if offset == 0:
            continue
        check_cycle = expected_cycle + offset
        if check_cycle < 0:
            continue
        golden_at_cycle = golden_cycles.get(check_cycle, {})
        golden_val = golden_at_cycle.get(signal)
        if golden_val is not None:
            golden_norm = _normalize_value(str(golden_val))
            if golden_norm == actual_norm:
                return check_cycle
    return None


def classify_failure(
    failures: list[dict],
    golden_cycles: dict[int, dict[str, str]] | None = None,
) -> list[dict]:
    """Classify each failure into A/B/D types with reasoning.

    Classification:
        D (Initialization): RTL value is x/z, or expected=0 but actual≠0
        B (Timing):         Correct value at wrong cycle (golden trace match)
        A (Computation):    Default — value mismatch, no timing alignment
    """
    results = []
    for f in failures:
        signal = f.get("signal", "")
        expected_raw = f.get("expected", "")
        actual_raw = f.get("actual", "")
        cycle = f.get("cycle")

        expected_norm = _normalize_value(expected_raw)
        actual_norm = _normalize_value(actual_raw)

        cls = "A"
        reasoning = "Computation error — trace datapath logic"

        if _is_unknown(actual_raw):
            cls = "D"
            reasoning = "RTL value is x/z/unknown — register not initialized or undriven"
        elif expected_norm is not None and expected_norm == 0 and actual_norm not in (None, 0):
            cls = "D"
            reasoning = f"Expected 0 but got {actual_raw} — register not cleared or spurious enable"
        elif golden_cycles is not None and cycle is not None:
            found_at = _find_value_in_golden(golden_cycles, signal, actual_raw, cycle)
            if found_at is not None:
                cls = "B"
                reasoning = (f"Value {actual_raw} matches golden at cycle {found_at}, "
                             f"not at cycle {cycle} — pipeline alignment issue")

        result = dict(f)
        result["classification"] = cls
        result["reasoning"] = reasoning
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Pure-Verilog simulation runner for VeriFlow-CC pipeline"
    )
    parser.add_argument("--rtl-dir", required=False, default=None,
                        help="Directory containing *.v RTL source files")
    parser.add_argument("--tb-file", required=False, default=None,
                        help="Path to Verilog testbench file (tb_<design>.v)")
    parser.add_argument("--module", required=False, default=None,
                        help="Verilog top-level module name (for reference)")
    parser.add_argument("--build-dir", required=False, default=None,
                        help="Build directory for compilation artifacts")
    parser.add_argument("--no-vcd", action="store_true",
                        help="Disable VCD waveform dump")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed output")
    parser.add_argument("--save-raw-log",
                        help="Save raw simulation output to this file path")
    parser.add_argument("--golden-check",
                        help="Run golden model self-check (path to golden_model.py)")
    args = parser.parse_args()

    if args.golden_check:
        result = golden_check(args.golden_check, verbose=args.verbose)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("passed") else 1)

    if not args.golden_check:
        if not args.rtl_dir or not args.tb_file or not args.module or not args.build_dir:
            parser.error("--rtl-dir, --tb-file, --module, --build-dir required "
                         "when not using --golden-check")

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

        # Save raw simulation output for post-mortem debug
        if args.save_raw_log:
            raw_log_path = Path(args.save_raw_log)
            raw_log_path.parent.mkdir(parents=True, exist_ok=True)
            raw_log_path.write_text(sim_output, encoding="utf-8")

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

    # Parse structured [FAIL] lines
    failures = [_parse_fail_line(fl) for fl in fail_lines]

    # Extract first failure cycle from parsed data
    first_fail_cycle = None
    for f in failures:
        if "cycle" in f and f["cycle"] is not None:
            first_fail_cycle = f["cycle"]
            break

    num_passed = len(pass_lines)
    num_failed = len(fail_lines)
    if failed_summary:
        num_failed = max(num_failed, int(failed_summary.group(1)))
    num_tests = num_passed + num_failed

    # Find VCD file
    vcd_files = sorted(build_dir.glob("*.vcd"))
    vcd_path = str(vcd_files[0]) if vcd_files else None

    if num_failed > 0 or not all_passed:
        classified = classify_failure(failures)
        result = {
            "tests": num_tests,
            "passed": num_passed,
            "failed": num_failed,
            "vcd_path": vcd_path,
            "failures": classified,
            "first_fail_cycle": first_fail_cycle,
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
