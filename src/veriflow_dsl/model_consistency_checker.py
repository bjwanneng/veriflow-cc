"""Model Consistency Checker — pre-codegen validation.

Compares timing_model.py (structural NBA model) against golden_model.py
(algorithmic reference) for the same inputs. Runs BEFORE codegen so
timing/algorithmic disagreements are caught before RTL generation.

Usage:
    from veriflow_dsl.model_consistency_checker import check_consistency
    report = check_consistency(
        timing_model_path="workspace/docs/timing_model.py",
        golden_model_path="workspace/docs/golden_model.py",
        spec_path="workspace/docs/spec.json",
        block_name="counter",
        num_cycles=16,
    )
    if not report.passed:
        for err in report.errors:
            print(err.message)
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._adapter import from_timing_model
from ._simulator import CycleSimulator


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConsistencyError:
    """A single mismatch between timing_model and golden_model."""
    category: str  # "algorithmic" | "timing" | "missing_port" | "latency"
    cycle: int | None
    signal: str | None
    timing_value: int | None
    golden_value: int | None
    message: str


@dataclass
class ConsistencyReport:
    """Result of a consistency check."""
    passed: bool
    errors: list[ConsistencyError] = field(default_factory=list)
    timing_model_trace: list[dict[str, int]] = field(default_factory=list)
    golden_model_trace: list[dict[str, int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_module(path: Path) -> Any:
    """Dynamically load a Python file as a module."""
    spec = importlib.util.spec_from_file_location(
        f"_vf_check_{path.stem}", str(path)
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        if str(path.parent) in sys.path:
            sys.path.remove(str(path.parent))
    return module


def _load_spec(spec_path: Path) -> dict:
    """Load and return spec.json as a dict."""
    with open(spec_path) as f:
        return json.load(f)


def _get_module_spec(spec: dict, block_name: str) -> dict | None:
    """Find the module spec matching block_name."""
    modules = spec.get("modules", [])
    if isinstance(modules, dict):
        modules = [{"module_name": k, **v} for k, v in modules.items()]
    for m in modules:
        if m.get("module_name") == block_name:
            return m
    return None


def _generate_inputs(input_ports: list[dict], num_cycles: int, seed: int = 42) -> list[dict[str, int]]:
    """Generate a sequence of per-cycle input dicts.

    For each input port, generates random values within its bit width.
    """
    rng = random.Random(seed)
    sequence: list[dict[str, int]] = []
    for _ in range(num_cycles):
        cycle_inputs = {}
        for port in input_ports:
            name = port["name"]
            width = port.get("width", 1)
            max_val = (1 << width) - 1 if width < 64 else (1 << 32) - 1
            cycle_inputs[name] = rng.randint(0, max_val)
        sequence.append(cycle_inputs)
    return sequence


def _run_timing_model(timing_model_path: Path, block_name: str, input_sequence: list[dict]) -> list[dict]:
    """Load timing_model.py, adapt the @vf_block, run CycleSimulator."""
    tm_module = _load_module(timing_model_path)
    if not hasattr(tm_module, block_name):
        raise ValueError(f"{timing_model_path} has no function named {block_name!r}")
    block_func = getattr(tm_module, block_name)
    if not hasattr(block_func, "_vf_block_type"):
        raise TypeError(f"{block_name} is not decorated with @vf_block")

    module = from_timing_model(block_func)
    sim = CycleSimulator(module)

    # Filter input_sequence to only include signals recognised by the module
    # (e.g. clk/rst declared in spec.json but absent from timing_model params)
    analysis = module.analyze()
    known_inputs = set(analysis.get("input_ports", {}).keys())
    filtered = [
        {k: v for k, v in cycle.items() if k in known_inputs}
        for cycle in input_sequence
    ]
    return sim.run(len(filtered), filtered)


def _run_golden_model(golden_model_path: Path, input_sequence: list[dict], num_cycles: int) -> list[dict] | None:
    """Try to run golden_model.py and return a trace.

    Tries multiple input formats:
      1. compute({port: [v1, v2, ...]}, trace=True)  — per-cycle sequence
      2. compute({port: scalar}, trace=True)         — constant input
      3. compute({port_sequence: [v1, v2, ...]}, trace=True) — legacy _sequence suffix
      4. run(0)                                      — built-in test vector
    """
    gm_module = _load_module(golden_model_path)

    # Build per-cycle sequences from input_sequence
    sequences = {}
    if input_sequence:
        for port in input_sequence[0].keys():
            sequences[port] = [cycle[port] for cycle in input_sequence]

    # Format 1: per-cycle sequences per port
    if sequences and hasattr(gm_module, "compute"):
        try:
            result = gm_module.compute(sequences, trace=True)
            if isinstance(result, list):
                return result
        except Exception as e:
            print(f"[model_consistency] compute(sequences) failed: {e}", file=sys.stderr)

    # Format 3: legacy _sequence suffix
    if sequences and hasattr(gm_module, "compute"):
        legacy = {f"{k}_sequence": v for k, v in sequences.items()}
        try:
            result = gm_module.compute(legacy, trace=True)
            if isinstance(result, list):
                return result
        except Exception as e:
            print(f"[model_consistency] compute(legacy_sequences) failed: {e}", file=sys.stderr)

    # Format 2: scalar inputs (constant across all cycles)
    if input_sequence and hasattr(gm_module, "compute"):
        scalar_inputs = input_sequence[0]
        try:
            result = gm_module.compute(scalar_inputs, trace=True)
            if isinstance(result, list):
                return result
        except Exception as e:
            print(f"[model_consistency] compute(scalar) failed: {e}", file=sys.stderr)

    # Format 4: built-in test vector via run()
    if hasattr(gm_module, "run"):
        try:
            return gm_module.run(0)
        except Exception as e:
            print(f"[model_consistency] run(0) failed: {e}", file=sys.stderr)

    return None


def _compare_traces(
    tm_trace: list[dict],
    gm_trace: list[dict],
    output_ports: list[str],
    max_latency_shift: int = 2,
) -> list[ConsistencyError]:
    """Compare two traces and classify mismatches."""
    errors: list[ConsistencyError] = []

    if not tm_trace or not gm_trace:
        errors.append(
            ConsistencyError(
                category="timing",
                cycle=None,
                signal=None,
                timing_value=None,
                golden_value=None,
                message="Empty trace: timing_model or golden_model produced no cycles",
            )
        )
        return errors

    # Check for trace length mismatch first
    if len(tm_trace) != len(gm_trace):
        errors.append(
            ConsistencyError(
                category="timing",
                cycle=None,
                signal=None,
                timing_value=len(tm_trace),
                golden_value=len(gm_trace),
                message=(
                    f"Trace length mismatch: timing_model={len(tm_trace)} cycles, "
                    f"golden_model={len(gm_trace)} cycles. "
                    f"Pipeline delay or reset modeling may differ."
                ),
            )
        )

    # Check for missing ports in golden model
    gm_keys = set()
    for cycle in gm_trace:
        gm_keys.update(cycle.keys())

    for port in output_ports:
        if port not in gm_keys:
            errors.append(
                ConsistencyError(
                    category="missing_port",
                    cycle=None,
                    signal=port,
                    timing_value=None,
                    golden_value=None,
                    message=f"Output port '{port}' declared in spec.json but missing from golden_model trace",
                )
            )

    if errors and all(e.category in ("missing_port", "timing") for e in errors):
        return errors

    # For each output port, try to find the best alignment
    for port in output_ports:
        if port not in gm_keys:
            continue

        tm_vals = [cycle.get(port, 0) for cycle in tm_trace]
        gm_vals = [cycle.get(port, 0) for cycle in gm_trace]

        # Try different shifts to detect latency mismatch
        best_shift = 0
        best_match_count = 0
        for shift in range(-max_latency_shift, max_latency_shift + 1):
            match_count = 0
            for i in range(len(tm_trace)):
                gm_idx = i + shift
                if 0 <= gm_idx < len(gm_vals):
                    if tm_vals[i] == gm_vals[gm_idx]:
                        match_count += 1
            if match_count > best_match_count:
                best_match_count = match_count
                best_shift = shift

        total_comparable = min(len(tm_trace), len(gm_trace))
        if total_comparable == 0:
            continue

        match_rate = best_match_count / total_comparable

        if best_shift != 0 and match_rate >= 0.8:
            errors.append(
                ConsistencyError(
                    category="timing",
                    cycle=None,
                    signal=port,
                    timing_value=None,
                    golden_value=None,
                    message=(
                        f"Output '{port}' appears shifted by {best_shift} cycle(s) "
                        f"(match_rate={match_rate:.1%}). "
                        f"Check pipeline_delay_cycles in spec.json."
                    ),
                )
            )
            continue

        # Compare cycle-by-cycle with no shift
        for cycle_idx in range(min(len(tm_trace), len(gm_trace))):
            tm_val = tm_vals[cycle_idx]
            gm_val = gm_vals[cycle_idx]
            if tm_val != gm_val:
                errors.append(
                    ConsistencyError(
                        category="algorithmic",
                        cycle=cycle_idx,
                        signal=port,
                        timing_value=tm_val,
                        golden_value=gm_val,
                        message=(
                            f"Cycle {cycle_idx}, '{port}': "
                            f"timing_model=0x{tm_val:x}, golden_model=0x{gm_val:x}"
                        ),
                    )
                )

    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_consistency(
    timing_model_path: Path | str,
    golden_model_path: Path | str,
    spec_path: Path | str,
    block_name: str,
    num_cycles: int = 16,
    seed: int = 42,
) -> ConsistencyReport:
    """Compare timing_model.py against golden_model.py for consistency.

    Args:
        timing_model_path: Path to timing_model.py
        golden_model_path: Path to golden_model.py
        spec_path: Path to spec.json
        block_name: Name of the @vf_block function to check
        num_cycles: Number of cycles to simulate
        seed: Random seed for input generation (deterministic)

    Returns:
        ConsistencyReport with passed flag and list of errors.
    """
    timing_model_path = Path(timing_model_path)
    golden_model_path = Path(golden_model_path)
    spec_path = Path(spec_path)

    for p in (timing_model_path, golden_model_path, spec_path):
        if not p.exists():
            return ConsistencyReport(
                passed=False,
                errors=[
                    ConsistencyError(
                        category="timing",
                        cycle=None,
                        signal=None,
                        timing_value=None,
                        golden_value=None,
                        message=f"File not found: {p}",
                    )
                ],
            )

    spec = _load_spec(spec_path)
    module_spec = _get_module_spec(spec, block_name)
    if module_spec is None:
        return ConsistencyReport(
            passed=False,
            errors=[
                ConsistencyError(
                    category="timing",
                    cycle=None,
                    signal=None,
                    timing_value=None,
                    golden_value=None,
                    message=f"Module '{block_name}' not found in spec.json",
                )
            ],
        )

    ports = module_spec.get("ports", [])
    input_ports = [p for p in ports if p.get("direction", "input") == "input"]
    output_ports = [p["name"] for p in ports if p.get("direction") == "output"]

    # Generate deterministic inputs
    input_sequence = _generate_inputs(input_ports, num_cycles, seed=seed)

    # Run timing model
    try:
        tm_trace = _run_timing_model(timing_model_path, block_name, input_sequence)
    except Exception as e:
        return ConsistencyReport(
            passed=False,
            errors=[
                ConsistencyError(
                    category="timing",
                    cycle=None,
                    signal=None,
                    timing_value=None,
                    golden_value=None,
                    message=f"timing_model simulation failed: {e}",
                )
            ],
        )

    # Run golden model
    gm_trace = _run_golden_model(golden_model_path, input_sequence, num_cycles)
    if gm_trace is None:
        return ConsistencyReport(
            passed=False,
            errors=[
                ConsistencyError(
                    category="timing",
                    cycle=None,
                    signal=None,
                    timing_value=None,
                    golden_value=None,
                    message=(
                        "golden_model simulation failed: could not invoke compute() or run(). "
                        "Ensure golden_model.py has compute(inputs, trace=True) or run(0)."
                    ),
                )
            ],
        )

    # Compare
    errors = _compare_traces(tm_trace, gm_trace, output_ports)

    return ConsistencyReport(
        passed=len(errors) == 0,
        errors=errors,
        timing_model_trace=tm_trace,
        golden_model_trace=gm_trace,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check consistency between timing_model.py and golden_model.py"
    )
    parser.add_argument("--timing-model", required=True, help="Path to timing_model.py")
    parser.add_argument("--golden", required=True, help="Path to golden_model.py")
    parser.add_argument("--spec", required=True, help="Path to spec.json")
    parser.add_argument("--block", required=True, help="@vf_block function name")
    parser.add_argument("--cycles", type=int, default=16, help="Number of cycles to simulate")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    args = parser.parse_args(argv)

    report = check_consistency(
        timing_model_path=args.timing_model,
        golden_model_path=args.golden,
        spec_path=args.spec,
        block_name=args.block,
        num_cycles=args.cycles,
    )

    if args.json:
        import json as _json
        print(
            _json.dumps(
                {
                    "passed": report.passed,
                    "errors": [
                        {
                            "category": e.category,
                            "cycle": e.cycle,
                            "signal": e.signal,
                            "timing_value": e.timing_value,
                            "golden_value": e.golden_value,
                            "message": e.message,
                        }
                        for e in report.errors
                    ],
                },
                indent=2,
            )
        )
    else:
        if report.passed:
            print("PASS: timing_model and golden_model are consistent.")
        else:
            print(f"FAIL: {len(report.errors)} mismatch(es) found:")
            for e in report.errors:
                print(f"  [{e.category}] {e.message}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    import argparse

    sys.exit(main())
