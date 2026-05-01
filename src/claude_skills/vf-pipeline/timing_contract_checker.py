#!/usr/bin/env python3
"""Timing contract checker for VeriFlow-CC pipeline.

Validates spec.json timing contracts and golden model trace alignment
between Stage 1 (spec_golden) and Stage 2 (codegen).

This is a PRE-VERIFICATION tool — it catches timing contradictions
BEFORE RTL is generated, not after simulation fails.

Usage:
    python timing_contract_checker.py \\
        --spec workspace/docs/spec.json \\
        [--golden workspace/docs/golden_model.py] \\
        [--output logs/timing_check.json]

Exit codes:
    0 -- all checks passed
    1 -- one or more errors found
    2 -- environment/file error
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def _iter_modules(spec: dict):
    """Yield (module_name, module_spec) pairs from spec.modules."""
    modules = spec.get("modules", [])
    if isinstance(modules, dict):
        for name, m in modules.items():
            yield name, m
    elif isinstance(modules, list):
        for m in modules:
            name = m.get("module_name", "?")
            yield name, m


def check_spec_consistency(spec: dict) -> tuple[list[str], list[str]]:
    """Check timing_contract fields for internal consistency.

    Validates the producer_type/consumer_type lookup table:
        registered   + sequential   -> same_cycle=false, delay >= 1
        combinational + sequential  -> same_cycle=true,  delay == 0
        registered   + combinational -> same_cycle=false, delay >= 1
        combinational + combinational -> same_cycle=true, delay == 0

    Returns:
        (errors, warnings)
    """
    errors = []
    warnings = []

    connectivity = spec.get("module_connectivity", [])
    if not connectivity:
        warnings.append("No module_connectivity entries -- skipping timing contract checks")
        return errors, warnings

    for conn in connectivity:
        src = conn.get("source", "?")
        dst = conn.get("destination", "?")
        tc = conn.get("timing_contract", {})

        if not tc:
            warnings.append(f"No timing_contract for {src} -> {dst}")
            continue

        producer = tc.get("producer_type", "")
        consumer = tc.get("consumer_type", "")
        same_cycle = tc.get("same_cycle_visible")
        delay = tc.get("pipeline_delay_cycles")
        bypass_req = tc.get("bypass_required", False)
        bypass_sig = tc.get("bypass_signal", "")

        # Lookup table rules
        rules = {
            ("registered", "sequential"): (False, 1),
            ("combinational", "sequential"): (True, 0),
            ("registered", "combinational"): (False, 1),
            ("combinational", "combinational"): (True, 0),
        }

        key = (producer, consumer)
        if key in rules:
            expected_same_cycle, expected_delay = rules[key]

            if same_cycle is not None and same_cycle != expected_same_cycle:
                errors.append(
                    f"{src}->{dst}: {producer}+{consumer} but "
                    f"same_cycle_visible={same_cycle} (should be {expected_same_cycle})"
                )

            if delay is not None and delay != expected_delay:
                # For rules with expected_delay > 0 (registered producer), delay >= expected is OK
                if expected_delay > 0 and delay >= expected_delay:
                    pass  # valid: e.g., registered producer with delay=2 is fine
                else:
                    errors.append(
                        f"{src}->{dst}: {producer}+{consumer} but "
                        f"pipeline_delay_cycles={delay} (should be {expected_delay})"
                    )

        # bypass_required=true but bypass_signal is empty
        if bypass_req and not bypass_sig:
            errors.append(
                f"{src}->{dst}: bypass_required=true but bypass_signal is empty"
            )

        # pipeline_delay_cycles=0 but same_cycle_visible=false -> contradiction
        if delay == 0 and same_cycle is False:
            errors.append(
                f"{src}->{dst}: pipeline_delay_cycles=0 but "
                f"same_cycle_visible=false (contradiction)"
            )

    return errors, warnings


def check_latency_consistency(spec: dict) -> tuple[list[str], list[str]]:
    """Check module latency against connectivity pipeline_delay_cycles.

    Returns:
        (errors, warnings)
    """
    errors = []
    warnings = []

    connectivity = spec.get("module_connectivity", [])

    for mod_name, mod in _iter_modules(spec):
        ct = mod.get("cycle_timing", {})
        pt = ct.get("pipeline_timing", {})
        latency = pt.get("input_to_output_latency_cycles")

        if latency is None:
            continue

        # Sum pipeline_delay_cycles on paths involving this module
        delay_sum = 0
        for conn in connectivity:
            src = conn.get("source", "")
            dst = conn.get("destination", "")
            tc = conn.get("timing_contract", {})
            delay = tc.get("pipeline_delay_cycles", 0)

            src_mod = src.split(".")[0] if "." in src else src
            dst_mod = dst.split(".")[0] if "." in dst else dst

            if dst_mod == mod_name or src_mod == mod_name:
                delay_sum += delay

        if delay_sum > 0 and latency < delay_sum:
            errors.append(
                f"Module '{mod_name}': declared latency={latency} but "
                f"sum of connectivity delays={delay_sum}"
            )

    return errors, warnings


def check_port_semantic_completeness(spec: dict) -> tuple[list[str], list[str]]:
    """Check that ports with protocol fields have required companion fields.

    Returns:
        (errors, warnings)
    """
    errors = []

    for mod_name, mod in _iter_modules(spec):
        ports = mod.get("ports", [])
        for port in ports:
            pname = port.get("name", "?")
            protocol = port.get("protocol", "")

            if protocol == "reset" and not port.get("reset_polarity"):
                errors.append(
                    f"Module '{mod_name}' port '{pname}': "
                    f"protocol=reset but missing reset_polarity"
                )

            if protocol == "valid" and not port.get("handshake"):
                errors.append(
                    f"Module '{mod_name}' port '{pname}': "
                    f"protocol=valid but missing handshake"
                )

    return errors, []


def check_golden_trace_alignment(
    spec: dict,
    golden_path: str,
) -> tuple[list[str], list[str]]:
    """Run golden model and check trace alignment with spec.

    Returns:
        (errors, warnings)
    """
    errors = []
    warnings = []

    golden_path = str(Path(golden_path).resolve())
    if not Path(golden_path).exists():
        warnings.append(f"Golden model not found: {golden_path}")
        return errors, warnings

    # Import and run golden model
    golden_cycles = {}
    try:
        spec_mod = importlib.util.spec_from_file_location("golden_model", golden_path)
        if spec_mod and spec_mod.loader:
            mod = importlib.util.module_from_spec(spec_mod)
            spec_mod.loader.exec_module(mod)
            if hasattr(mod, "run"):
                try:
                    golden_data = mod.run(test_vector_index=0)
                except TypeError:
                    golden_data = mod.run()

                if isinstance(golden_data, list):
                    for i, entry in enumerate(golden_data):
                        if isinstance(entry, dict):
                            golden_cycles[i] = entry
    except Exception as e:
        errors.append(f"Golden model execution error: {e}")
        return errors, warnings

    if not golden_cycles:
        errors.append("Golden model produced no parseable cycle data")
        return errors, warnings

    # Check trace length vs declared latency
    for mod_name, mod in _iter_modules(spec):
        ct = mod.get("cycle_timing", {})
        pt = ct.get("pipeline_timing", {})
        latency = pt.get("input_to_output_latency_cycles")

        if latency is not None and len(golden_cycles) > latency:
            warnings.append(
                f"Module '{mod_name}': golden trace has {len(golden_cycles)} cycles "
                f"but declared latency={latency}"
            )

    # Check output signals in trace match spec port names
    all_port_names = set()
    for mod_name, mod in _iter_modules(spec):
        for port in mod.get("ports", []):
            all_port_names.add(port.get("name", ""))

    trace_signals = set()
    for cycle_data in golden_cycles.values():
        trace_signals.update(cycle_data.keys())

    unmatched = trace_signals - all_port_names
    if unmatched:
        warnings.append(
            f"Golden trace signals not in spec ports: {sorted(unmatched)}"
        )

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(
        description="Timing contract checker for VeriFlow-CC pipeline"
    )
    parser.add_argument("--spec", required=True,
                        help="Path to spec.json")
    parser.add_argument("--golden",
                        help="Path to golden_model.py (optional)")
    parser.add_argument("--output",
                        help="Write JSON result to this file path")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.exists():
        result = {"passed": False, "errors": [f"spec.json not found: {spec_path}"], "warnings": []}
        print(json.dumps(result))
        sys.exit(2)

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        result = {"passed": False, "errors": [f"Cannot parse spec.json: {e}"], "warnings": []}
        print(json.dumps(result))
        sys.exit(2)

    all_errors = []
    all_warnings = []

    # Run all checks
    errors, warnings = check_spec_consistency(spec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = check_latency_consistency(spec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = check_port_semantic_completeness(spec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if args.golden:
        errors, warnings = check_golden_trace_alignment(spec, args.golden)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    result = {
        "passed": len(all_errors) == 0,
        "errors": all_errors,
        "warnings": all_warnings,
    }

    print(json.dumps(result, indent=2))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
