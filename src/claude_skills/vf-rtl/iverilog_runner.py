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

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from rtl_utils import find_executable, collect_rtl_sources, DIVERGENCE_SEARCH_WINDOW


def find_iverilog() -> str:
    return find_executable(["iverilog", "iverilog.exe"])


def find_vvp() -> str:
    return find_executable(["vvp", "vvp.exe"])


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


# Permissive key=value parser. The previous fixed-order regex broke whenever
# the testbench omitted a field or reordered them. We now tolerate any
# subset/ordering of {test, vector, cycle, signal, expected, actual, phase}.
#
# Two flavors of value are accepted:
#   - "quoted strings" — may embed spaces; captured without the quotes
#   - bare tokens — non-greedy run of non-space chars terminated by
#     either whitespace, end-of-string, OR the next `<word>=` pair. The
#     `\w+=` lookahead is what protects against TB lines that forget the
#     space between kv pairs (e.g. `cycle=5signal=data_out`).
_FAIL_KV_PATTERN = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+?))(?=\s|$|\w+=)')

_INT_FIELDS = {"vector", "cycle"}


def _parse_fail_line(fl: str) -> dict:
    """Parse a [FAIL] line into a failure dict.

    Returns at minimum {"test": ..., "message": fl}; any of vector, cycle,
    signal, expected, actual, phase are added when present in the line.
    """
    result: dict = {"test": "verilog_tb", "message": fl}
    for k, quoted, bare in _FAIL_KV_PATTERN.findall(fl):
        v = quoted if quoted else bare
        if k in _INT_FIELDS:
            try:
                result[k] = int(v)
            except ValueError:
                result[k] = v
        else:
            result[k] = v
    return result


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


# Shared divergence search window — imported from rtl_utils so both
# iverilog_runner and timing_diagnostic read the same value.
_DIVERGENCE_SEARCH_WINDOW = DIVERGENCE_SEARCH_WINDOW


def _find_value_in_golden(
    golden_cycles: dict[int, dict[str, str]],
    signal: str,
    actual_raw: str,
    expected_cycle: int,
    search_window: int = _DIVERGENCE_SEARCH_WINDOW,
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


def _resolve_sim_timeout(
    cli_value: int | None,
    spec_path: str | None,
    rtl_dir: Path,
    default: int = 120,
) -> int:
    """Resolve the simulation timeout.

    Priority: --sim-timeout > spec.json constraints.verification.sim_timeout_s
              > default (120 s).

    spec.json is searched at:
      1. --spec-path (if given)
      2. <rtl_dir>/../docs/spec.json (project layout convention)
    """
    if cli_value is not None and cli_value > 0:
        return cli_value

    candidates = []
    if spec_path:
        candidates.append(Path(spec_path))
    candidates.append(rtl_dir.parent / "docs" / "spec.json")

    for spec_p in candidates:
        try:
            if spec_p.exists():
                spec = json.loads(spec_p.read_text(encoding="utf-8"))
                t = (
                    spec.get("constraints", {})
                        .get("verification", {})
                        .get("sim_timeout_s")
                )
                if isinstance(t, (int, float)) and t > 0:
                    return int(t)
        except (json.JSONDecodeError, OSError):
            continue

    return default


def _build_diff_summary(
    classified_failures: list[dict],
    num_tests: int,
    num_passed: int,
    num_failed: int,
) -> str:
    """Build a human-readable diff summary for appending to sim.log."""
    lines = [
        "",
        "=" * 60,
        "SIMULATION DIFF SUMMARY",
        f"Tests: {num_passed}/{num_tests} passed, {num_failed} failed",
        "=" * 60,
    ]
    for i, f in enumerate(classified_failures[:10]):
        cls = f.get("classification", "?")
        signal = f.get("signal", "?")
        cycle = f.get("cycle", "?")
        expected = f.get("expected", "?")
        actual = f.get("actual", "?")
        reasoning = f.get("reasoning", "")
        lines.append(
            f"  [{cls}] #{i+1} cycle={cycle} signal={signal} "
            f"expected={expected} actual={actual}"
        )
        if reasoning:
            lines.append(f"       {reasoning}")
    if len(classified_failures) > 10:
        lines.append(f"  ... and {len(classified_failures) - 10} more failure(s)")
    lines.append("=" * 60)
    lines.append("")
    return "\n".join(lines)


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
    parser.add_argument("--sim-timeout", type=int, default=None,
                        help="vvp simulation timeout in seconds. If omitted, "
                             "reads spec.json constraints.verification.sim_timeout_s "
                             "(searched relative to --rtl-dir/..), else falls back to 120.")
    parser.add_argument("--spec-path", default=None,
                        help="Optional spec.json path used to resolve --sim-timeout "
                             "when the flag itself is omitted.")
    parser.add_argument("--golden-model", default=None,
                        help="Path to golden_model.py for coverage analysis. "
                             "If provided, the runner compares exercised signals "
                             "against golden trace signals and reports coverage ratio.")
    args = parser.parse_args()

    if args.golden_check:
        result = golden_check(args.golden_check, verbose=args.verbose)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("passed") else 1)

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

    # Clean stale VCD files from previous runs to avoid mtime-based picker
    # picking a stale dump when the current run fails to produce one.
    for stale_vcd in build_dir.glob("*.vcd"):
        try:
            stale_vcd.unlink()
        except OSError as e:
            # Best-effort cleanup; downstream `ls -t` picks the newest. We
            # still surface the failure so a locked-file or perm-denied
            # situation isn't invisible when debugging stale VCDs.
            print(f"[iverilog_runner] could not remove stale {stale_vcd.name}: {e}",
                  file=sys.stderr)

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

    # Ensure EDA binary/lib paths are in PATH for DLL resolution on Windows.
    # eda_env.sh sets these in the shell, but subprocess needs explicit PATH.
    sim_env = os.environ.copy()
    eda_bin = os.environ.get("EDA_BIN", "")
    eda_lib = os.environ.get("EDA_LIB", "")
    existing_path = sim_env.get("PATH", "")
    existing_dirs = set(existing_path.split(os.pathsep))
    extra = [p for p in [eda_bin, eda_lib] if p and p not in existing_dirs]
    if extra:
        sim_env["PATH"] = os.pathsep.join(extra) + os.pathsep + existing_path
    try:
        result = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            cwd=str(build_dir),
            env=sim_env,
        )
        if result.returncode != 0:
            print(json.dumps({
                "tests": 0, "passed": 0, "failed": 0,
                "error": "iverilog compilation failed",
                "compile_stderr": result.stderr[:2000],
                "compile_stdout": result.stdout[:2000],
            }))
            if args.verbose:
                print("[iverilog_runner] COMPILE FAILED:", file=sys.stderr)
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
        print("[iverilog_runner] Compilation successful, running simulation...", file=sys.stderr)

    sim_timeout = _resolve_sim_timeout(args.sim_timeout, args.spec_path, rtl_dir)
    if args.verbose:
        print(f"[iverilog_runner] sim timeout: {sim_timeout}s", file=sys.stderr)

    # Run simulation with vvp
    sim_cmd = [vvp_exe, output_vvp]
    # VCD is generated by $dumpfile/$dumpvars in the testbench itself

    try:
        result = subprocess.run(
            sim_cmd,
            capture_output=True,
            text=True,
            cwd=str(build_dir),
            env=sim_env,
            timeout=sim_timeout,
        )

        sim_output = result.stdout + result.stderr

        # Save raw simulation output for post-mortem debug
        if args.save_raw_log:
            raw_log_path = Path(args.save_raw_log)
            raw_log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                raw_log_path.write_text(sim_output, encoding="utf-8")
            except OSError as e:
                print(f"[iverilog_runner] Warning: could not save raw log: {e}", file=sys.stderr)

        if args.verbose:
            print("[iverilog_runner] Simulation output:", file=sys.stderr)
            print(sim_output[:5000], file=sys.stderr)

    except subprocess.TimeoutExpired:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 1,
            "error": f"Simulation timed out after {sim_timeout} seconds "
                     f"(override with --sim-timeout or "
                     f"spec.json constraints.verification.sim_timeout_s)"
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

    # Coverage analysis: count exercised test vectors from log
    coverage_info = {}
    if args.golden_model:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("golden_model", args.golden_model)
            gm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gm)
            tv_count = len(getattr(gm, "TEST_VECTORS", []))
            exercised = len(pass_lines) + len(fail_lines)
            coverage_info = {
                "test_vectors_total": tv_count,
                "test_vectors_exercised": exercised,
                "coverage_ratio": round(exercised / tv_count, 2) if tv_count else None,
            }
        except Exception as e:
            print(f"[iverilog_runner] coverage analysis failed: {e}", file=sys.stderr)

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

    # Find VCD file — prefer module-specific name for parallel-sim safety,
    # fall back to most-recently-modified for backward compatibility.
    vcd_files = list(build_dir.glob("*.vcd"))
    module_vcd = build_dir / f"{args.module}.vcd"
    if module_vcd.exists():
        vcd_path = str(module_vcd)
    elif vcd_files:
        vcd_path = str(max(vcd_files, key=lambda p: p.stat().st_mtime))
    else:
        vcd_path = None

    if num_failed > 0 or not all_passed:
        classified = classify_failure(failures)
        result = {
            "tests": num_tests,
            "passed": num_passed,
            "failed": num_failed,
            "vcd_path": vcd_path,
            "failures": classified,
            "first_fail_cycle": first_fail_cycle,
            "coverage": coverage_info,
        }
        print(json.dumps(result))

        # Append inline diff summary to the raw sim log
        diff_summary = _build_diff_summary(classified, num_tests, num_passed, num_failed)
        if args.save_raw_log:
            raw_log_path = Path(args.save_raw_log)
            if raw_log_path.exists():
                with open(raw_log_path, "a", encoding="utf-8") as f:
                    f.write(diff_summary)
        # Also print summary to stderr for orchestrator visibility
        print(diff_summary, file=sys.stderr)

        sys.exit(1)
    else:
        result = {
            "tests": num_tests,
            "passed": num_passed,
            "failed": 0,
            "vcd_path": vcd_path,
            "coverage": coverage_info,
        }
        print(json.dumps(result))
        sys.exit(0)


if __name__ == "__main__":
    main()
