"""Shared utilities for VeriFlow-CC RTL pipeline tools.

Provides common functionality used by iverilog_runner.py, cocotb_runner.py,
vcd2table.py, timing_diagnostic.py, timing_contract_checker.py, and state.py.
"""

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


# Single source of truth for the ±N-cycle search window used by the failure
# classifier and timing diagnostics. Living here (not in timing_diagnostic.py)
# lets iverilog_runner import it without a try/except fallback that could
# silently drift if timing_diagnostic ever gets renamed or moved.
DIVERGENCE_SEARCH_WINDOW: int = 8


def find_executable(names: list[str]) -> str:
    """Find an executable by name, checking EDA_BIN then PATH.

    Args:
        names: Candidate executable names (e.g., ["iverilog", "iverilog.exe"]).
    Returns:
        Absolute path to the executable, or empty string if not found.
    """
    eda_bin = os.environ.get("EDA_BIN", "")
    if eda_bin:
        for name in names:
            p = Path(eda_bin) / name
            if p.exists():
                return str(p)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ""


def collect_rtl_sources(rtl_dir: Path) -> list[str]:
    """Find all Verilog source files in rtl_dir.

    Args:
        rtl_dir: Directory to search for *.v files.
    Returns:
        Sorted list of absolute paths as strings.
    Raises:
        SystemExit(2): If no .v files are found.
    """
    sources = sorted(rtl_dir.glob("*.v"))
    if not sources:
        print(json.dumps({
            "tests": 0, "passed": 0, "failed": 0,
            "error": f"No .v files found in {rtl_dir}"
        }))
        sys.exit(2)
    return [str(s) for s in sources]


def load_golden_trace(golden_path: str, test_vector_index: int = 0) -> dict[int, dict[str, Any]]:
    """Load and run a golden model, returning per-cycle trace data.

    Supports three golden model interfaces:
      1. run(test_vector_index=N) -> list[dict]
      2. run() -> list[dict]
      3. compute(inputs, trace=True) returning a trace (uses TEST_VECTORS)

    Args:
        golden_path: Path to golden_model.py.
        test_vector_index: Which test vector to use (default 0).
    Returns:
        Dict mapping cycle_number -> {signal_name: value}.
    Raises:
        RuntimeError: If the golden model cannot be loaded or produces no data.
    """
    golden_path = str(Path(golden_path).resolve())
    if not Path(golden_path).exists():
        raise RuntimeError(f"Golden model not found: {golden_path}")

    spec = importlib.util.spec_from_file_location("golden_model", golden_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot create module spec for {golden_path}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Interface 1: run(test_vector_index=N) or run(N) or run()
    if hasattr(mod, "run"):
        try:
            data = mod.run(test_vector_index=test_vector_index)
        except TypeError:
            try:
                data = mod.run(test_vector_index)
            except TypeError:
                data = mod.run()

        if isinstance(data, list):
            cycles = {}
            for i, entry in enumerate(data):
                if isinstance(entry, dict):
                    cycles[i] = entry
            if cycles:
                return cycles

    # Interface 2: compute(inputs, trace=True) with TEST_VECTORS
    if hasattr(mod, "compute") and hasattr(mod, "TEST_VECTORS"):
        tv = mod.TEST_VECTORS[test_vector_index] if test_vector_index < len(mod.TEST_VECTORS) else mod.TEST_VECTORS[0]
        inputs = tv.get("inputs", tv)
        try:
            trace = mod.compute(inputs, trace=True)
            if isinstance(trace, list):
                cycles = {}
                for i, entry in enumerate(trace):
                    if isinstance(entry, dict):
                        cycles[i] = entry
                if cycles:
                    return cycles
            elif isinstance(trace, dict):
                return {0: trace}
        except (TypeError, Exception):
            pass

    # Interface 3: simulate(inputs, trace=True) with TEST_VECTORS
    if hasattr(mod, "simulate") and hasattr(mod, "TEST_VECTORS"):
        tv = mod.TEST_VECTORS[test_vector_index] if test_vector_index < len(mod.TEST_VECTORS) else mod.TEST_VECTORS[0]
        inputs = tv.get("inputs", tv)
        try:
            trace = mod.simulate(inputs, trace=True)
            if isinstance(trace, list):
                cycles = {}
                for i, entry in enumerate(trace):
                    if isinstance(entry, dict):
                        cycles[i] = entry
                if cycles:
                    return cycles
        except (TypeError, Exception):
            pass

    raise RuntimeError(
        "Golden model produced no parseable cycle data. "
        "Expected run() -> list[dict] or compute(inputs, trace=True)."
    )
