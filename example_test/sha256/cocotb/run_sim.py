#!/usr/bin/env python3
"""cocotb simulation runner for sha256_core.

Uses cocotb_tools.runner API (no Makefile required).
Equivalent to: make SIM=icarus

Usage:
    python run_sim.py              # Run all tests
    python run_sim.py --clean      # Clean and re-run

On failure, produces structured Python tracebacks that are directly
consumable by LLM for root cause analysis and auto-fix.
"""

import sys
import os
from pathlib import Path

# Set up EDA environment (same as .veriflow/eda_env.sh)
EDA_BIN = "/c/oss-cad-suite/bin"
EDA_LIB = "/c/oss-cad-suite/lib"
EDA_LIB_IVL = "/c/oss-cad-suite/lib/ivl"
os.environ["PATH"] = os.pathsep.join([EDA_BIN, EDA_LIB, EDA_LIB_IVL, os.environ.get("PATH", "")])

from cocotb_tools.runner import Icarus, get_results


def main():
    proj_dir = Path(__file__).parent
    rtl_dir = proj_dir.parent / "workspace" / "rtl"
    build_dir = proj_dir / "sim_build"

    if "--clean" in sys.argv:
        import shutil
        if build_dir.exists():
            shutil.rmtree(build_dir)
            print(f"[CLEAN] Removed {build_dir}")
        if len(sys.argv) == 2 and sys.argv[1] == "--clean":
            return

    # Ensure build directory
    build_dir.mkdir(parents=True, exist_ok=True)

    # Icarus Verilog runner
    runner = Icarus()
    # Copy current environment into runner (otherwise subprocess loses PATH)
    runner.env = os.environ.copy()

    # Test sources
    rtl_src = str(rtl_dir / "sha256_core.v")
    test_src = str(proj_dir / "test_sha256_core.py")

    if not Path(rtl_src).exists():
        print(f"ERROR: RTL source not found: {rtl_src}")
        sys.exit(1)

    print("=" * 72)
    print("cocotb SHA-256 Core Simulation")
    print(f"  RTL      : {rtl_src}")
    print(f"  Testbench: {test_src}")
    print(f"  Build dir: {build_dir}")
    print(f"  Top-level: sha256_core")
    print("=" * 72)
    print()

    # Build simulation
    print("[BUILD] Compiling with iverilog...")
    runner.build(
        sources=[rtl_src],
        hdl_toplevel="sha256_core",
        build_dir=str(build_dir),
        build_args=["-g2012"],
    )

    print("[BUILD] Compile OK")
    print()

    # Run tests
    print("[RUN] Executing tests...")
    print()

    results_xml = runner.test(
        test_module="test_sha256_core",
        hdl_toplevel="sha256_core",
        test_dir=str(proj_dir),
        build_dir=str(build_dir),
    )

    # Parse results from xUnit XML
    num_tests, num_failed = get_results(Path(results_xml))
    num_passed = num_tests - num_failed

    print()
    print("=" * 72)
    print(f"RESULTS: {num_passed} passed, {num_failed} failed, {num_tests} total")
    print(f"Results XML: {results_xml}")
    print("=" * 72)

    if num_failed > 0:
        print()
        print("SIM_RESULT: FAIL")
        print()
        print("── cocotb Error Recovery Guide ──")
        print("  Run with: pytest -v --tb=long <test_file>")
        print("  Each failure produces a Python traceback with:")
        print("    - File path and line number of the assertion")
        print("    - Expected vs actual values")
        print("    - DUT signal state at failure point")
        print("  Use this structured information to locate and fix RTL bugs.")
        sys.exit(1)
    else:
        print()
        print("SIM_RESULT: PASS")
        print("All cocotb tests passed.")


if __name__ == "__main__":
    main()
