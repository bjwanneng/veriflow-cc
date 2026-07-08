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
import traceback
from pathlib import Path
from typing import Optional

from rtl_utils import collect_rtl_sources
import contextlib


def _find_docs_dir(tb_dir: Path) -> Path | None:
    """Find the workspace docs directory containing spec.json and golden_model.py.

    Searches in order:
      1. <tb_dir>/../docs/  (canonical layout: workspace/tb + workspace/docs)
      2. Walk up from tb_dir looking for docs/golden_model.py
      3. $PROJECT_DIR/workspace/docs/
    Returns the docs Path if found, else None.
    """
    # 1. Canonical layout
    candidate = tb_dir.parent / "docs"
    if (candidate / "golden_model.py").exists() and (candidate / "spec.json").exists():
        return candidate

    # 2. Walk up from tb_dir
    current = tb_dir.parent
    for _ in range(5):  # max 5 levels up
        candidate = current / "docs"
        if (candidate / "golden_model.py").exists() and (candidate / "spec.json").exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    # 3. $PROJECT_DIR/workspace/docs/
    project_dir = os.environ.get("PROJECT_DIR", "")
    if project_dir:
        candidate = Path(project_dir) / "workspace" / "docs"
        if (candidate / "golden_model.py").exists() and (candidate / "spec.json").exists():
            return candidate

    return None


def check_environment():
    """Verify cocotb is importable. Exit 2 if not."""
    try:
        import cocotb  # noqa: F401 — importability is the test itself
        import cocotb_tools.runner  # noqa: F401
    except ImportError as e:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": f"cocotb not available: {e}",
            "hint": "Install with: pip install cocotb"
        }))
        sys.exit(2)


def find_test_module(tb_dir: Path, module_name: str,
                     test_file_override: Optional[str] = None) -> str:
    """Find the cocotb test module.

    Args:
        tb_dir: Directory containing test files.
        module_name: Top-level module name (used for default test file lookup).
        test_file_override: If set, use this file path instead of the default
            test_<module>.py naming convention. Can be an absolute path or
            relative to tb_dir. The module name (without .py) is extracted
            from the filename and returned.

    Returns:
        The Python module name (e.g., "test_sm3_core" or "test_sm3_debug").
    """
    if test_file_override:
        # Resolve the override path
        override_path = Path(test_file_override)
        if not override_path.is_absolute():
            override_path = tb_dir / override_path
        if not override_path.exists():
            print(json.dumps({
                "tests": 0, "passed": 0, "failed": 0,
                "error": f"Test file not found: {override_path}"
            }))
            sys.exit(2)
        # Return the module name derived from the filename
        return override_path.stem
    # Default: look for test_<module>.py
    test_file = tb_dir / f"test_{module_name}.py"
    if not test_file.exists():
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": f"Test file not found: {test_file}"
        }))
        sys.exit(2)
    return f"test_{module_name}"


def _build_cocotb_diff_summary(
    failures: list[dict],
    num_tests: int,
    num_passed: int,
    num_failed: int,
) -> str:
    """Build a human-readable diff summary from cocotb xUnit failures."""
    lines = [
        "",
        "=" * 60,
        "COCOTB DIFF SUMMARY",
        f"Tests: {num_passed}/{num_tests} passed, {num_failed} failed",
        "=" * 60,
    ]
    for i, f in enumerate(failures[:10]):
        test_name = f.get("test", "?")
        msg = f.get("message", "")
        lines.append(f"  #{i+1} test={test_name}")
        if msg:
            # Show the first 3 lines of the message to capture full
            # expected/actual/xor diff data (no truncation — debug data
            # must be complete, never guess from truncated values).
            msg_lines = msg.split("\n")[:3]
            for ml in msg_lines:
                lines.append(f"     {ml}")
    if len(failures) > 10:
        lines.append(f"  ... and {len(failures) - 10} more failure(s)")
    lines.append("=" * 60)
    lines.append("")
    return "\n".join(lines)


def _try_timing_diagnostic(
    failures: list[dict],
    tb_dir: Path,
    build_dir: Path,
) -> dict | None:
    """Auto-run timing_diagnostic.diagnose() on the cocotb failures.

    Writes failure messages to <build_dir>/cocotb_failures.log so the existing
    log-scanning diagnose() can find FIRST DIVERGENCE patterns. Looks for
    spec.json and golden_model.py at <tb_dir>/../docs/ (the canonical
    workspace layout). Returns a dict with the diagnosis, or None if no
    diagnosis could be produced (no divergence pattern, missing files, etc.).

    Failure to produce a diagnosis is silent — it is a "no extra hint"
    outcome, not an error. The cocotb failure stays the source of truth.
    """
    if not failures:
        return None

    # Concatenate every failure's message + traceback into a single log blob
    blob_lines: list[str] = []
    for f in failures:
        msg = f.get("message", "") or ""
        tb = f.get("traceback", "") or ""
        if msg:
            blob_lines.append(msg)
        if tb:
            blob_lines.append(tb)
    blob = "\n".join(blob_lines)
    if not blob.strip():
        return None

    log_path = build_dir / "cocotb_failures.log"
    try:
        log_path.write_text(blob, encoding="utf-8")
    except OSError:
        return None

    # Find docs dir with fallback search
    docs_dir = _find_docs_dir(tb_dir)
    if docs_dir is None:
        # Cannot run timing_diagnostic without golden model and spec.
        # Fall through to degraded diagnosis below.
        pass
    else:
        golden_path = docs_dir / "golden_model.py"
        spec_path = docs_dir / "spec.json"

        try:
            from timing_diagnostic import diagnose
        except ImportError:
            golden_path = None  # type: ignore
        else:
            try:
                diagnosis = diagnose(log_path, golden_path, spec_path)
            except Exception:
                diagnosis = None

            if diagnosis is not None:
                # Run bug-pattern matcher over the classified signals (best effort)
                pattern_matches: list[dict] = []
                try:
                    from bug_pattern_match import match_patterns
                    divs_for_match = [
                        {
                            "signal": s.signal,
                            "classification": s.classification,
                            "offset_cycles": s.offset_cycles,
                            "expected": s.expected_value,
                            "actual": s.actual_value,
                            "cycle": diagnosis.divergence.cycle,
                        }
                        for s in diagnosis.all_signals
                    ]
                    pattern_matches = [m.to_dict() for m in match_patterns(divs_for_match)]
                except Exception:
                    pattern_matches = []

                return {
                    "divergence": {
                        "cycle": diagnosis.divergence.cycle,
                        "signal": diagnosis.divergence.signal,
                        "expected": f"0x{diagnosis.divergence.expected:x}",
                        "actual": f"0x{diagnosis.divergence.actual:x}",
                        "degraded": diagnosis.divergence.degraded,
                    },
                    "signal_classifications": [
                        {
                            "signal": s.signal,
                            "classification": s.classification,
                            "offset_cycles": s.offset_cycles,
                            "expected": f"0x{s.expected_value:x}",
                            "actual": f"0x{s.actual_value:x}",
                        }
                        for s in diagnosis.all_signals
                    ],
                    "timing_contract_context": diagnosis.timing_contract_context,
                    "fix_suggestion": diagnosis.fix_suggestion,
                    "severity": diagnosis.severity,
                    "pattern_matches": pattern_matches,
                    "log_path": str(log_path),
                }

    # Degraded diagnosis: no FIRST DIVERGENCE found or docs unavailable.
    # Extract structured info from failure messages so Stage 3 has something
    # actionable instead of a blank slate.
    fix_lines = []
    for f in failures:
        test_name = f.get("test", "?")
        msg = f.get("message", "")
        if "Timeout waiting for ready" in msg:
            fix_lines.append(
                f"Test '{test_name}': DUT never asserted ready — check reset "
                f"initialization and FSM IDLE state."
            )
        elif "drive_inputs() was never called" in msg:
            fix_lines.append(
                f"Test '{test_name}': no stimulus delivered — codegen did not "
                f"fill in the drive_inputs() call in this test."
            )
        elif "GOLDEN_TO_PORT is empty" in msg:
            fix_lines.append(
                f"Test '{test_name}': port mapping not populated — codegen "
                f"did not fill in GOLDEN_TO_PORT from spec.json."
            )
        elif "ZERO signals were compared" in msg or "no signals compared" in msg.lower():
            fix_lines.append(
                f"Test '{test_name}': golden trace signal names don't match "
                f"DUT hierarchy — check naming convention (_reg suffix, module prefix)."
            )
        elif msg:
            fix_lines.append(f"Test '{test_name}': {msg[:200]}")

    return {
        "degraded": True,
        "divergence": {"cycle": None, "signal": None,
                       "expected": None, "actual": None, "degraded": True},
        "fix_suggestion": (
            "No FIRST DIVERGENCE pattern found in cocotb output.\n"
            + ("\n".join(fix_lines) if fix_lines else
               "Tests failed before per-cycle comparison started. "
               "Read logs/cocotb.log for full traceback.")
        ),
        "severity": "medium",
        "log_path": str(log_path),
    }


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
    parser.add_argument("--no-vcd", dest="vcd", action="store_false",
                        help="Disable VCD waveform dump (default: enabled)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed per-test results")
    parser.add_argument("--test-file", default=None,
                        help="Override the default test_<module>.py with a specific "
                             "test file (absolute path or relative to --tb-dir). "
                             "Useful for running debug/alternative test files.")
    parser.set_defaults(vcd=True)
    args = parser.parse_args()

    # Phase 0: Check cocotb is importable
    check_environment()

    # Lazy imports after env check
    from cocotb_tools.runner import Icarus, get_results

    rtl_dir = Path(args.rtl_dir).resolve()
    tb_dir = Path(args.tb_dir).resolve()
    build_dir = Path(args.build_dir).resolve()
    module_name = args.module
    test_module = find_test_module(tb_dir, module_name, args.test_file)

    build_dir.mkdir(parents=True, exist_ok=True)

    # Clean stale VCD files from previous runs
    for stale_vcd in build_dir.glob("*.vcd"):
        with contextlib.suppress(OSError):
            stale_vcd.unlink()

    rtl_sources = collect_rtl_sources(rtl_dir)

    # ── Auto-detect VERILOG_PARAMS from test file ──────────────────────
    # Test files can define: VERILOG_PARAMS = {"PARAM_NAME": value, ...}
    # These are passed as iverilog -P<module>.<param>=<value> build args.
    build_args = []
    test_file_path = tb_dir / f"{test_module}.py"
    if not test_file_path.exists():
        for candidate in tb_dir.glob(f"test_{module_name}*.py"):
            test_file_path = candidate
            break
    if test_file_path.exists():
        import re as _re
        src_text = test_file_path.read_text(encoding="utf-8", errors="replace")
        m = _re.search(r'VERILOG_PARAMS\s*=\s*\{([^}]+)\}', src_text)
        if m:
            params_str = m.group(1)
            for pm in _re.finditer(r'"(\w+)"\s*:\s*(\d+)', params_str):
                pname, pval = pm.group(1), pm.group(2)
                flag = f"-P{module_name}.{pname}={pval}"
                build_args.append(flag)
            if build_args and args.verbose:
                print(f"[cocotb_runner] Verilog params: {build_args}", file=sys.stderr)

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
    # Set cocotb test timeout (default 120s) to prevent infinite hangs
    if "COCOTB_TIMEOUT" not in runner.env:
        runner.env["COCOTB_TIMEOUT"] = "120"
    # Tell the TB where to dump functional coverage (read back into the result).
    runner.env.setdefault("COVERAGE_FILE", str(Path(build_dir) / "coverage.json"))

    # ── Build ──────────────────────────────────────────────────────────
    if args.verbose:
        print(f"[cocotb_runner] Building {module_name}...", file=sys.stderr)

    try:
        runner.build(
            sources=rtl_sources,
            hdl_toplevel=module_name,
            build_dir=str(build_dir),
            build_args=build_args,
            waves=args.vcd,
        )
    except Exception as e:
        traceback.print_exc()
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
        traceback.print_exc()
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
    # Pick VCD file — prefer module-specific name for parallel-sim safety,
    # fall back to most-recently-modified for backward compatibility.
    vcd_files = list(build_dir.glob("*.vcd"))
    module_vcd = build_dir / f"{module_name}.vcd"
    if module_vcd.exists():
        vcd_path = str(module_vcd)
    elif vcd_files:
        vcd_path = str(max(vcd_files, key=lambda p: p.stat().st_mtime))
    else:
        vcd_path = None
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

    # ── Functional coverage (coverage-driven verification) ──────────────
    # The TB dumps coverage.json (COVERAGE_FILE) at exit; surface it so
    # coverage_analyzer can score it in Stage 3.
    coverage_path = Path(build_dir) / "coverage.json"
    if coverage_path.exists():
        result["coverage_path"] = str(coverage_path)
        with contextlib.suppress(json.JSONDecodeError, OSError):
            result["coverage"] = json.loads(coverage_path.read_text(encoding="utf-8"))

    # ── Alignment info (SLOW-3: single source of truth for cycle mapping) ──
    # Emitted on failure so the orchestrator knows exactly how cocotb cycles
    # map to golden model cycles without re-reading multiple source files.
    if num_failed > 0:
        drive_phase = None
        try:
            # Read DRIVE_PHASE_CYCLES from the test file if possible
            test_file = tb_dir / f"test_{module_name}.py"
            if test_file.exists():
                src = test_file.read_text(encoding="utf-8", errors="replace")
                import re as _re
                m = _re.search(r'DRIVE_PHASE_CYCLES\s*=\s*(\d+)', src)
                if m:
                    drive_phase = int(m.group(1))
        except Exception:
            pass
        result["alignment_info"] = {
            "reset_cycle_skip": 1,
            "drive_phase_cycles": drive_phase,
            "note": (
                "cocotb compare cycle 0 = golden cycle 1 (after RESET_CYCLE_SKIP=1). "
                "DRIVE_PHASE_CYCLES is consumed inside drive_inputs() before compare loop."
            ),
        }

    # ── Auto-run timing_diagnostic on failure ─────────────────────────
    # The whole point of this auto-wiring: when a cycle-level mismatch is
    # found, do NOT make the orchestrator guess about timing offsets vs
    # algorithm errors — the diagnostic gives a deterministic classification
    # (A/B_late/B_early/D) and a concrete fix suggestion. The runner remains
    # silent if there is no FIRST DIVERGENCE pattern or the inputs are
    # missing, so this is a strict additive hint.
    diagnosis = None
    if num_failed > 0:
        diagnosis = _try_timing_diagnostic(failures, tb_dir, build_dir)
        if diagnosis is not None:
            result["timing_diagnosis"] = diagnosis

    print(json.dumps(result))

    # Print inline diff summary to stderr for orchestrator visibility
    if num_failed > 0 and failures:
        diff_summary = _build_cocotb_diff_summary(failures, num_tests, num_passed, num_failed)
        print(diff_summary, file=sys.stderr)

    if diagnosis is not None:
        diag_lines = [
            "",
            "=" * 60,
            "TIMING DIAGNOSIS",
            "=" * 60,
            f"  cycle    : {diagnosis['divergence']['cycle']}",
            f"  signal   : {diagnosis['divergence']['signal']}",
            f"  expected : {diagnosis['divergence']['expected']}",
            f"  actual   : {diagnosis['divergence']['actual']}",
            f"  severity : {diagnosis['severity']}",
        ]
        for s in diagnosis.get("signal_classifications", [])[:5]:
            diag_lines.append(
                f"  class    : {s['signal']} -> {s['classification']} "
                f"(offset={s['offset_cycles']}, exp={s['expected']}, act={s['actual']})"
            )
        fix = diagnosis.get("fix_suggestion", "")
        if fix:
            diag_lines.append("-" * 60)
            diag_lines.append("FIX SUGGESTION:")
            for line in fix.split("\n"):
                diag_lines.append(f"  {line}")
        pattern_matches = diagnosis.get("pattern_matches", []) or []
        if pattern_matches:
            diag_lines.append("-" * 60)
            diag_lines.append(
                f"MATCHED BUG PATTERNS ({len(pattern_matches)}) — see bug_patterns.md:"
            )
            for m in pattern_matches[:5]:
                diag_lines.append(
                    f"  P{m['pattern_id']:02d} [{m['confidence']:.0%}] {m['title']}"
                )
                diag_lines.append(f"    why : {m['reason']}")
                diag_lines.append(f"    rule: {m['prevention_rule']}")
        diag_lines.append("=" * 60)
        print("\n".join(diag_lines), file=sys.stderr)

    if num_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
