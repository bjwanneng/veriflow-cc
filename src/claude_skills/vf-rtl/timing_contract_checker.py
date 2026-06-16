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
import contextlib
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

        # Max pipeline_delay_cycles across paths involving this module
        max_delay = 0
        for conn in connectivity:
            src = conn.get("source", "")
            dst = conn.get("destination", "")
            tc = conn.get("timing_contract", {})
            delay = tc.get("pipeline_delay_cycles", 0)

            src_mod = src.split(".")[0] if "." in src else src
            dst_mod = dst.split(".")[0] if "." in dst else dst

            if dst_mod == mod_name or src_mod == mod_name:
                max_delay = max(max_delay, delay)

        if max_delay > 0 and latency < max_delay:
            errors.append(
                f"Module '{mod_name}': declared latency={latency} but "
                f"max connectivity delay={max_delay}"
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
    for _name, mod in _iter_modules(spec):
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


def check_timing_convention(spec: dict) -> tuple[list[str], list[str]]:
    """Check that timing_convention offset is consistent with pipeline delays.

    The golden_to_rtl_offset_cycles must be >= max(pipeline_delay_cycles)
    across all connectivity entries, otherwise the TB will misalign with RTL.

    Returns:
        (errors, warnings)
    """
    errors = []
    warnings = []

    convention = spec.get("timing_convention")
    if not convention:
        return errors, warnings

    offset = convention.get("golden_to_rtl_offset_cycles")
    if offset is None:
        warnings.append("timing_convention present but golden_to_rtl_offset_cycles not set")
        return errors, warnings

    connectivity = spec.get("module_connectivity", [])
    delays = [
        conn.get("timing_contract", {}).get("pipeline_delay_cycles", 0)
        for conn in connectivity
        if conn.get("timing_contract")
    ]

    if not delays:
        return errors, warnings

    max_delay = max(delays)
    if offset < max_delay:
        errors.append(
            f"golden_to_rtl_offset_cycles={offset} but "
            f"max pipeline_delay_cycles={max_delay} "
            f"(offset must be >= max delay)"
        )
    elif offset > max_delay:
        # Over-large offset: drive_inputs() will hold inputs for `offset`
        # cycles, advancing the DUT past golden cycle 1 before the compare
        # loop starts. The compare loop will then see stale matches or
        # spurious divergences. Recommend setting offset == max_delay.
        warnings.append(
            f"golden_to_rtl_offset_cycles={offset} exceeds "
            f"max pipeline_delay_cycles={max_delay} by {offset - max_delay} "
            f"cycle(s). drive_inputs() will over-hold and the comparison "
            f"loop will compare against stale golden entries. Set "
            f"timing_convention.golden_to_rtl_offset_cycles={max_delay}."
        )

    return errors, warnings


def check_fanout_skew(spec: dict) -> tuple[list[str], list[str]]:
    """Check fanout groups for delay skew between same-source signals.

    For each fanout_group, traces each signal through module_connectivity
    and accumulates pipeline_delay_cycles. Reports if the skew between
    any two signals exceeds max_delay_skew_cycles.

    Returns:
        (errors, warnings)
    """
    errors = []
    warnings = []

    fanout_groups = spec.get("fanout_groups", [])
    if not fanout_groups:
        return errors, warnings

    connectivity = spec.get("module_connectivity", [])

    for group in fanout_groups:
        group_name = group.get("name", "?")
        constraint = group.get("constraint", "")
        max_skew = group.get("max_delay_skew_cycles", 0)
        signals = group.get("signals", [])

        if not signals:
            continue

        # Accumulate delay for each signal along its connectivity path
        signal_delays = {}
        for sig in signals:
            sig_name = sig.get("name", "?")
            sig_path = sig.get("path", "")

            # Parse path: "module1.port1 -> module2.port2"
            path_parts = [p.strip() for p in sig_path.split("->")]
            total_delay = 0

            for conn in connectivity:
                src = conn.get("source", "")
                dst = conn.get("destination", "")
                tc = conn.get("timing_contract", {})
                delay = tc.get("pipeline_delay_cycles", 0) if tc else 0

                # Check if this connection is on the signal's path (exact matching)
                src_match = any(
                    f"{p.split('.')[0]}.{p.split('.')[-1]}" == src
                    or p.strip() == src
                    or src.startswith(p.strip() + ".")
                    for p in path_parts[:-1]
                )
                dst_match = any(
                    f"{p.split('.')[0]}.{p.split('.')[-1]}" == dst
                    or p.strip() == dst
                    or dst.startswith(p.strip() + ".")
                    for p in path_parts[1:]
                )

                if src_match or dst_match:
                    total_delay += delay

            signal_delays[sig_name] = total_delay

        # Check skew
        if len(signal_delays) < 2:
            continue

        delays = list(signal_delays.values())
        actual_skew = max(delays) - min(delays)

        if actual_skew > max_skew:
            detail = ", ".join(
                f"{name}={delay}" for name, delay in signal_delays.items()
            )
            errors.append(
                f"Fanout group '{group_name}' ({constraint}): "
                f"skew={actual_skew} cycle(s) exceeds max_delay_skew_cycles={max_skew}. "
                f"Signal delays: [{detail}]"
            )

    return errors, warnings


# ---------------------------------------------------------------------------
# Auto-fix helpers
# ---------------------------------------------------------------------------

def fix_spec(spec: dict) -> dict:
    """Apply automatic fixes to spec.json based on checker rules.

    Returns a deep-copied dict so the original is untouched.
    """
    import copy
    spec = copy.deepcopy(spec)
    fixes_log = []

    # ---- Fix 1: timing_contract consistency ----
    rules = {
        ("registered", "sequential"): (False, 1),
        ("combinational", "sequential"): (True, 0),
        ("registered", "combinational"): (False, 1),
        ("combinational", "combinational"): (True, 0),
    }

    for conn in spec.get("module_connectivity", []):
        tc = conn.get("timing_contract", {})
        if not tc:
            continue

        producer = tc.get("producer_type", "")
        consumer = tc.get("consumer_type", "")
        key = (producer, consumer)

        if key not in rules:
            continue

        expected_same_cycle, expected_delay = rules[key]
        src = conn.get("source", "?")
        dst = conn.get("destination", "?")

        # Fix same_cycle_visible
        same_cycle = tc.get("same_cycle_visible")
        if same_cycle is not None and same_cycle != expected_same_cycle:
            tc["same_cycle_visible"] = expected_same_cycle
            fixes_log.append(
                f"{src}->{dst}: same_cycle_visible {same_cycle} -> {expected_same_cycle}"
            )

        # Fix pipeline_delay_cycles
        delay = tc.get("pipeline_delay_cycles")
        if delay is not None:
            if expected_delay > 0 and delay >= expected_delay:
                pass  # already OK
            elif delay != expected_delay:
                tc["pipeline_delay_cycles"] = expected_delay
                fixes_log.append(
                    f"{src}->{dst}: pipeline_delay_cycles {delay} -> {expected_delay}"
                )
                # Also update visible_cycle / consumer_cycle when delay changes
                if expected_delay == 1:
                    tc["visible_cycle"] = "T+1"
                    tc["consumer_cycle"] = "T+1"

        # Fix contradiction: delay=0 + same_cycle=false. Re-read the CURRENT
        # values — Fix 1 above may have just bumped pipeline_delay_cycles (e.g.
        # 0->1 for a registered producer), so the `delay`/`same_cycle` locals
        # captured at the top of the loop are stale. Reading them fresh avoids
        # flipping same_cycle_visible on a contract whose delay is now non-zero
        # (which would re-introduce a delay>=1 & same_cycle=True inconsistency).
        cur_delay = tc.get("pipeline_delay_cycles")
        cur_same_cycle = tc.get("same_cycle_visible")
        if cur_delay == 0 and cur_same_cycle is False:
            tc["same_cycle_visible"] = True
            fixes_log.append(
                f"{src}->{dst}: fixed contradiction (delay=0 -> same_cycle=true)"
            )

    # ---- Fix 2: port semantic completeness ----
    for mod in _iter_modules(spec):
        mod_name, m = mod
        for port in m.get("ports", []):
            pname = port.get("name", "?")
            protocol = port.get("protocol", "")

            if protocol == "reset" and not port.get("reset_polarity"):
                port["reset_polarity"] = "active_high"
                fixes_log.append(
                    f"Module '{mod_name}' port '{pname}': added reset_polarity=active_high"
                )

            if protocol == "valid" and not port.get("handshake"):
                ack = port.get("ack_port", "")
                if ack:
                    port["handshake"] = "valid_ready"
                    fixes_log.append(
                        f"Module '{mod_name}' port '{pname}': added handshake=valid_ready"
                    )

    # ---- Fix 3: latency consistency ----
    connectivity = spec.get("module_connectivity", [])
    for mod_name, mod in _iter_modules(spec):
        ct = mod.get("cycle_timing", {})
        pt = ct.get("pipeline_timing", {})
        latency = pt.get("input_to_output_latency_cycles")

        if latency is None:
            continue

        max_delay = 0
        for conn in connectivity:
            src = conn.get("source", "")
            dst = conn.get("destination", "")
            tc = conn.get("timing_contract", {})
            delay = tc.get("pipeline_delay_cycles", 0)

            src_mod = src.split(".")[0] if "." in src else src
            dst_mod = dst.split(".")[0] if "." in dst else dst

            if dst_mod == mod_name or src_mod == mod_name:
                max_delay = max(max_delay, delay)

        if max_delay > 0 and latency < max_delay:
            pt["input_to_output_latency_cycles"] = max_delay
            fixes_log.append(
                f"Module '{mod_name}': latency {latency} -> {max_delay}"
            )

    return {"spec": spec, "fixes": fixes_log}


def check_cdc_paths(spec: dict) -> tuple[list[str], list[str]]:
    """Validate clock domain crossing (CDC) paths.

    Checks that:
    - If clock_domains is declared, all cdc_paths have valid synchronizers
    - Synchronizer type is one of: two_ff, fifo, handshake
    - Source and destination clock domains exist
    """
    errors = []
    warnings = []

    clock_domains = spec.get("clock_domains", [])
    cdc_paths = spec.get("cdc_paths", [])

    if not clock_domains:
        return errors, warnings

    domain_names = {d.get("name", "") for d in clock_domains}

    if not cdc_paths:
        warnings.append(
            "clock_domains declared but no cdc_paths specified. "
            "If design is single-clock, remove clock_domains."
        )
        return errors, warnings

    valid_sync_types = {"two_ff", "fifo", "handshake", "async_fifo"}

    for i, path in enumerate(cdc_paths):
        src_domain = path.get("source_clock", "")
        dst_domain = path.get("destination_clock", "")
        signal = path.get("signal", f"cdc_paths[{i}]")
        sync_type = path.get("synchronizer", "")

        if src_domain not in domain_names:
            errors.append(
                f"CDC path '{signal}': source_clock '{src_domain}' not declared "
                f"in clock_domains"
            )
        if dst_domain not in domain_names:
            errors.append(
                f"CDC path '{signal}': destination_clock '{dst_domain}' not declared "
                f"in clock_domains"
            )

        if not sync_type:
            errors.append(
                f"CDC path '{signal}': missing synchronizer type. "
                f"Must be one of: {valid_sync_types}"
            )
        elif sync_type not in valid_sync_types:
            errors.append(
                f"CDC path '{signal}': unknown synchronizer '{sync_type}'. "
                f"Must be one of: {valid_sync_types}"
            )

        if src_domain == dst_domain:
            warnings.append(
                f"CDC path '{signal}': source and destination are the same domain "
                f"('{src_domain}'). This is not a CDC path."
            )

    return errors, warnings


def _run_all_checks(spec: dict, golden_path: str | None) -> tuple[list[str], list[str]]:
    """Run all check functions and return accumulated (errors, warnings)."""
    all_errors = []
    all_warnings = []

    errors, warnings = check_spec_consistency(spec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = check_latency_consistency(spec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = check_port_semantic_completeness(spec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = check_timing_convention(spec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = check_fanout_skew(spec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = check_cdc_paths(spec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if golden_path:
        errors, warnings = check_golden_trace_alignment(spec, golden_path)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    return all_errors, all_warnings


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
    parser.add_argument("--fix", action="store_true",
                        help="Auto-fix spec.json errors in-place and re-check")
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

    # ------------------------------------------------------------------
    # --fix mode: auto-correct then re-check
    # ------------------------------------------------------------------
    if args.fix:
        fix_result = fix_spec(spec)
        fixes = fix_result["fixes"]
        fixed_spec = fix_result["spec"]

        # Re-check BEFORE writing to disk — avoids half-fixed state
        all_errors, all_warnings = _run_all_checks(fixed_spec, args.golden)
        result = {
            "passed": len(all_errors) == 0,
            "errors": all_errors,
            "warnings": all_warnings,
            "auto_fixed": fixes,
        }

        if fixes:
            # Only write if fixes were applied (even if re-check still finds issues,
            # the partial fix is better than no fix — user can iterate). Back up the
            # original first so a wrong auto-fix is recoverable.
            bak_path = spec_path.parent / (spec_path.name + ".bak")
            with contextlib.suppress(OSError):  # best-effort backup; don't block the fix
                bak_path.write_text(
                    spec_path.read_text(encoding="utf-8"), encoding="utf-8"
                )
            spec_path.write_text(json.dumps(fixed_spec, indent=2), encoding="utf-8")
            print(json.dumps({"fixed": True, "fixes_applied": fixes}, indent=2))
        else:
            print(json.dumps({"fixed": False, "message": "No auto-fixable issues found"}, indent=2))

        print(json.dumps(result, indent=2))

        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        sys.exit(0 if result["passed"] else 1)

    # ------------------------------------------------------------------
    # Normal mode: just check
    # ------------------------------------------------------------------
    all_errors, all_warnings = _run_all_checks(spec, args.golden)

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
