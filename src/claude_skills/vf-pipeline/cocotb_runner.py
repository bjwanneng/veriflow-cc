#!/usr/bin/env python3
"""Parameterized cocotb simulation runner for VeriFlow-CC pipeline.

Runs cocotb tests for a single Verilog module using the Icarus Verilog (iverilog)
simulator backend. Designed to be called from Bash by Stage 3 (verify_fix).

Usage:
    python3 cocotb_runner.py \\
        --rtl-dir     <path/to/workspace/rtl> \\
        --tb-dir      <path/to/workspace/tb> \\
        --module      <module_name> \\
        --build-dir   <path/to/build_dir> \\
        [--results-file <path/to/results.xml>] \\
        [--verbose]

Exit codes:
    0 — all tests passed
    1 — one or more tests failed
    2 — environment error (cocotb not installed, RTL not found, etc.)

Output (stdout):
    JSON object: {"tests": N, "passed": M, "failed": F, "xml_path": "...",
                  "failures": [{"test": "...", "message": "..."}, ...]}
"""

import argparse
import json
import os
import sys
from pathlib import Path


def check_environment():
    """Verify cocotb is importable. Exit 2 if not."""
    try:
        import cocotb                           # noqa: F401
        import cocotb_tools.runner              # noqa: F401
    except ImportError as e:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": f"cocotb not available: {e}",
            "hint": "Install with: pip install cocotb"
        }))
        sys.exit(2)


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


def find_test_module(tb_dir: Path, module_name: str) -> str:
    """Find the cocotb test file: test_<module>.py."""
    test_file = tb_dir / f"test_{module_name}.py"
    if not test_file.exists():
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": f"Test file not found: {test_file}"
        }))
        sys.exit(2)
    return f"test_{module_name}"


def main():
    parser = argparse.ArgumentParser(
        description="cocotb simulation runner for VeriFlow-CC pipeline"
    )
    parser.add_argument("--rtl-dir", required=True,
                        help="Directory containing *.v RTL source files")
    parser.add_argument("--tb-dir", required=True,
                        help="Directory containing test_<module>.py testbench")
    parser.add_argument("--module", required=True,
                        help="Verilog top-level module name")
    parser.add_argument("--build-dir", required=True,
                        help="Build directory for cocotb artifacts")
    parser.add_argument("--results-file", default=None,
                        help="Path to write xUnit XML results (default: <build_dir>/results.xml)")
    parser.add_argument("--vcd", action="store_true", default=True,
                        help="Enable VCD waveform dump (default: True)")
    parser.add_argument("--no-vcd", dest="vcd", action="store_false",
                        help="Disable VCD waveform dump")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed per-test results")
    args = parser.parse_args()

    # Phase 0: Check cocotb is importable
    check_environment()

    # Lazy imports after env check
    from cocotb_tools.runner import Icarus, get_results

    rtl_dir = Path(args.rtl_dir).resolve()
    tb_dir = Path(args.tb_dir).resolve()
    build_dir = Path(args.build_dir).resolve()
    module_name = args.module
    test_module = find_test_module(tb_dir, module_name)

    build_dir.mkdir(parents=True, exist_ok=True)

    # Copy test file to build_dir so cocotb can import it
    # (cocotb's test_module discovery searches the test_dir)
    rtl_sources = collect_rtl_sources(rtl_dir)

    if args.verbose:
        print(f"[cocotb_runner] RTL dir   : {rtl_dir}", file=sys.stderr)
        print(f"[cocotb_runner] RTL files : {len(rtl_sources)}", file=sys.stderr)
        print(f"[cocotb_runner] TB dir    : {tb_dir}", file=sys.stderr)
        print(f"[cocotb_runner] Module    : {module_name}", file=sys.stderr)
        print(f"[cocotb_runner] Build dir : {build_dir}", file=sys.stderr)

    # ── Icarus Verilog runner ──────────────────────────────────────────
    runner = Icarus()

    # Copy current environment (ensures PATH with iverilog/vvp is passed
    # to subprocess — without this, the runner's empty env loses PATH)
    runner.env = os.environ.copy()

    # ── Build ──────────────────────────────────────────────────────────
    if args.verbose:
        print(f"[cocotb_runner] Building {module_name}...", file=sys.stderr)

    try:
        runner.build(
            sources=rtl_sources,
            hdl_toplevel=module_name,
            build_dir=str(build_dir),
            build_args=[],
            waves=args.vcd,
        )
    except Exception as e:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": f"Build failed: {e}"
        }))
        sys.exit(2)

    # ── Test ───────────────────────────────────────────────────────────
    if args.verbose:
        print(f"[cocotb_runner] Running tests for {test_module}...", file=sys.stderr)

    results_xml_path = args.results_file or str(build_dir / "results.xml")

    try:
        runner.test(
            test_module=test_module,
            hdl_toplevel=module_name,
            test_dir=str(tb_dir),
            build_dir=str(build_dir),
            results_xml=results_xml_path,
            waves=args.vcd,
        )
    except Exception as e:
        # Simulation crashed before producing results
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 1,
            "error": f"Simulation crashed: {e}",
            "xml_path": results_xml_path,
            "failures": [{"test": test_module, "message": str(e)}]
        }))
        sys.exit(1)

    # ── Parse results ──────────────────────────────────────────────────
    try:
        num_tests, num_failed = get_results(Path(results_xml_path))
    except RuntimeError as e:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 1,
            "error": str(e),
            "xml_path": results_xml_path,
            "failures": [{"test": test_module, "message": str(e)}]
        }))
        sys.exit(1)

    num_passed = num_tests - num_failed

    # ── Extract failure details from XML ───────────────────────────────
    failures = []
    if num_failed > 0:
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(results_xml_path)
            for suite in tree.iter("testsuite"):
                for tc in suite.iter("testcase"):
                    fail_elem = tc.find("failure")
                    if fail_elem is not None:
                        msg = fail_elem.get("message", "")
                        text = fail_elem.text or ""
                        failures.append({
                            "test": tc.get("name", "unknown"),
                            "message": msg,
                            "traceback": text[:500],
                        })
        except Exception:
            pass

    # ── Output JSON summary to stdout ──────────────────────────────────
    # Find VCD file(s) in build_dir for waveform analysis
    vcd_files = sorted(build_dir.glob("*.vcd"))
    vcd_path = str(vcd_files[0]) if vcd_files else None
    if args.verbose and vcd_path:
        print(f"[cocotb_runner] VCD file  : {vcd_path}", file=sys.stderr)

    result = {
        "tests": num_tests,
        "passed": num_passed,
        "failed": num_failed,
        "xml_path": results_xml_path,
        "vcd_path": vcd_path,
        "failures": failures,
    }
    print(json.dumps(result))

    if num_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
