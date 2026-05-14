"""Timing Diagnostic Tool for VeriFlow-CC.

Analyzes cocotb FIRST DIVERGENCE reports against golden model traces
and spec.json timing contracts to produce precise fix instructions.

Usage:
    python timing_diagnostic.py \\
        --log logs/cocotb.log \\
        --golden workspace/docs/golden_model.py \\
        --spec workspace/docs/spec.json \\
        [--output logs/timing_diagnostic.json]

Exit codes:
    0 = diagnosis successful
    1 = no divergence found in log
    2 = file/environment error
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Ensure same-directory siblings (rtl_utils) are importable when this script
# is invoked directly (e.g. `python timing_diagnostic.py ...`).
sys.path.insert(0, str(Path(__file__).parent))

from rtl_utils import DIVERGENCE_SEARCH_WINDOW  # noqa: E402


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Divergence:
    cycle: int
    signal: str
    expected: int
    actual: int
    degraded: bool = False  # True when parsed from vcd2table without full signal/value data


@dataclass
class SignalDiagnosis:
    signal: str
    classification: str   # "A" | "B_late" | "B_early" | "D"
    offset_cycles: int = 0
    expected_value: int = 0
    actual_value: int = 0


@dataclass
class TimingDiagnosis:
    divergence: Divergence
    all_signals: list[SignalDiagnosis] = field(default_factory=list)
    timing_contract_context: list[dict] = field(default_factory=list)
    fix_suggestion: str = ""
    severity: str = "high"


# ---------------------------------------------------------------------------
# Step 1: Parse FIRST DIVERGENCE from cocotb log
# ---------------------------------------------------------------------------

_DIV_PATTERNS = [
    # INTERNAL — pinpoints the exact register. Matches multi-line format:
    #   [INTERNAL] FIRST DIVERGENCE at cycle=N signal=S (width=Wb)[ kind=K]:
    #     expected = 0xHHHH
    #     actual   = 0xHHHH
    re.compile(
        r'\[INTERNAL\]\s+FIRST\s+DIVERGENCE\s+at\s+cycle=(\d+)\s+'
        r'signal=(\S+)\s+\(width=\d+b\)(?:\s+kind=\S+)?:\s*\n'
        r'\s+expected\s*=\s*(0x[0-9a-fA-F]+)\s*\n'
        r'\s+actual\s*=\s*(0x[0-9a-fA-F]+)'
    ),
    # LAYERED — same multi-line format without kind= tag
    re.compile(
        r'\[LAYERED\]\s+FIRST\s+DIVERGENCE\s+at\s+cycle=(\d+)\s+'
        r'signal=(\S+)\s+\(width=\d+b\):\s*\n'
        r'\s+expected\s*=\s*(0x[0-9a-fA-F]+)\s*\n'
        r'\s+actual\s*=\s*(0x[0-9a-fA-F]+)'
    ),
    # Verilog testbench [FAIL] single-line format emitted by
    # SAMPLE_REGISTERED_OUTPUT / SAMPLE_PULSE_OUTPUT macros in
    # tb_integration_template.v. Width/kind/xor are present but not all
    # required by the regex — only cycle, signal, expected, actual are
    # consumed by the diagnostic core.
    re.compile(
        r'\[FAIL\]\s+test=\S+\s+cycle=(\d+)\s+signal=(\S+)'
        r'(?:\s+kind=\S+)?(?:\s+width=\d+b)?'
        r'\s+expected=(0x[0-9a-fA-F]+)\s+actual=(0x[0-9a-fA-F]+)'
    ),
    # vcd2table FIRST DIVERGENCE SUMMARY (rich format with all fields):
    #   FIRST DIVERGENCE SUMMARY: cycle=N signal=S golden=0xHHH rtl=0xHHH type=T
    re.compile(
        r'FIRST\s+DIVERGENCE\s+SUMMARY:\s+'
        r'cycle=(\d+)\s+signal=(\S+)\s+'
        r'golden=(0x[0-9a-fA-F]+|\d+)\s+rtl=(0x[0-9a-fA-F]+|\d+)',
        re.IGNORECASE,
    ),
    # vcd2table basic format (only cycle — degraded, no signal/value data):
    #   FIRST DIVERGENCE: cycle N
    re.compile(
        r'FIRST\s+DIVERGENCE:\s+cycle\s+(\d+)',
        re.IGNORECASE,
    ),
]


def parse_divergence(log_path: Path) -> Divergence | None:
    """Extract FIRST DIVERGENCE from cocotb or vcd2table log."""
    log_text = log_path.read_text(encoding="utf-8", errors="replace")

    for pattern in _DIV_PATTERNS:
        match = pattern.search(log_text)
        if match:
            groups = match.groups()
            cycle = int(groups[0])

            # vcd2table basic format: only cycle captured (1 group)
            if len(groups) == 1:
                return Divergence(
                    cycle=cycle,
                    signal="unknown_from_vcd2table",
                    expected=0,
                    actual=0,
                    degraded=True,
                )

            # Full formats (INTERNAL, LAYERED, Verilog, vcd2table SUMMARY): 4 groups
            signal = groups[1] if len(groups) > 1 else "unknown"
            expected_raw = groups[2] if len(groups) > 2 else "0"
            actual_raw = groups[3] if len(groups) > 3 else "0"

            expected = int(expected_raw, 16) if expected_raw.startswith("0x") else int(expected_raw, 0)
            actual = int(actual_raw, 16) if actual_raw.startswith("0x") else int(actual_raw, 0)

            return Divergence(
                cycle=cycle,
                signal=signal,
                expected=expected,
                actual=actual,
            )

    return None


# ---------------------------------------------------------------------------
# Step 2: Load golden model trace
# ---------------------------------------------------------------------------

def load_golden_trace(golden_path: Path) -> list[dict[str, int]]:
    """Import golden model and obtain its per-cycle trace.

    Delegates to rtl_utils.load_golden_trace_as_list() for the actual loading.
    Returns [] on failure.
    """
    from rtl_utils import load_golden_trace_as_list as _load
    try:
        return _load(str(golden_path), test_vector_index=0)
    except RuntimeError:
        return []


# ---------------------------------------------------------------------------
# Step 3: Classify all mismatched signals
# ---------------------------------------------------------------------------

WINDOW = DIVERGENCE_SEARCH_WINDOW  # ±N cycles, sourced from rtl_utils


def _classify_signal(
    signal: str,
    cycle: int,
    expected: int,
    actual: int,
    golden_trace: list[dict[str, int]],
) -> SignalDiagnosis:
    """Classify a single signal mismatch.

    Uses the divergence info (expected vs actual) to search the golden trace
    for timing offsets:
    - B_late: actual matches golden at cycle-offset (RTL shows old value)
    - B_early: actual matches golden at cycle+offset (RTL jumps ahead)
    - D: actual=0 and expected!=0 (initialization)
    - A: none of the above (computation)
    """
    if expected == actual:
        return SignalDiagnosis(signal, "unclassifiable", 0, expected, actual)

    for offset in range(1, WINDOW + 1):
        # B_late: actual value matches what golden had offset cycles ago
        # (RTL is behind — still showing the old value)
        earlier = cycle - offset
        if earlier >= 0 and earlier < len(golden_trace):
            if golden_trace[earlier].get(signal) == actual:
                return SignalDiagnosis(signal, "B_late", offset, expected, actual)

        # B_early: actual value matches what golden will have offset cycles later
        # (RTL is ahead — already showing the future value)
        later = cycle + offset
        if later < len(golden_trace):
            if golden_trace[later].get(signal) == actual:
                return SignalDiagnosis(signal, "B_early", offset, expected, actual)

    # D: actual is 0 when expected is non-zero
    if actual == 0 and expected != 0:
        return SignalDiagnosis(signal, "D", 0, expected, actual)

    return SignalDiagnosis(signal, "A", 0, expected, actual)


def classify_all_signals(
    divergence: Divergence,
    golden_trace: list[dict[str, int]],
) -> list[SignalDiagnosis]:
    """Classify the diverged signal against the golden trace.

    Returns a single-element list containing the classification of the
    signal reported by cocotb's FIRST DIVERGENCE.

    Note (was a bug previously): we DO NOT fabricate classifications for
    other signals at the divergence cycle. cocotb stops at the first
    divergence, so we have no observation for the other signals — assuming
    they match (`actual = expected`) produces noise that misleads the LLM
    fix step. If you need full per-signal classification, read the VCD with
    `vcd2table.py` to obtain the real values.
    """
    cycle = divergence.cycle
    expected = divergence.expected
    actual = divergence.actual

    if golden_trace and 0 <= cycle < len(golden_trace):
        diag = _classify_signal(
            divergence.signal, cycle, expected, actual, golden_trace
        )
    elif divergence.degraded:
        # Degraded divergence with no golden trace — cannot classify meaningfully.
        diag = SignalDiagnosis(divergence.signal, "unclassifiable", 0, expected, actual)
    else:
        # Out of trace range — fall back to D/A heuristic.
        if actual == 0 and expected != 0:
            diag = SignalDiagnosis(divergence.signal, "D", 0, expected, actual)
        else:
            diag = SignalDiagnosis(divergence.signal, "A", 0, expected, actual)

    return [diag]


# ---------------------------------------------------------------------------
# Step 4: Correlate with timing_contract
# ---------------------------------------------------------------------------

def find_timing_context(signal_name: str, spec: dict) -> list[dict]:
    """Find all timing_contract edges involving this signal."""
    context = []
    connectivity = spec.get("module_connectivity", [])
    fanout_groups = spec.get("fanout_groups", [])

    for conn in connectivity:
        src = conn.get("source", "")
        dst = conn.get("destination", "")
        tc = conn.get("timing_contract", {})
        port_name = signal_name.replace("_reg", "").replace("_next", "")

        if port_name in src or port_name in dst:
            context.append({
                "source": src,
                "destination": dst,
                "pipeline_delay": tc.get("pipeline_delay_cycles", 0),
                "producer_type": tc.get("producer_type", ""),
                "consumer_type": tc.get("consumer_type", ""),
                "same_cycle_visible": tc.get("same_cycle_visible", ""),
            })

    # Check fanout groups
    for group in fanout_groups:
        signals = group.get("signals", [])
        for sig in signals:
            if port_name in sig.get("name", "") or port_name in sig.get("path", ""):
                context.append({
                    "fanout_group": group.get("name", ""),
                    "constraint": group.get("constraint", ""),
                    "max_delay_skew_cycles": group.get("max_delay_skew_cycles", 0),
                    "note": f"Signal is part of fanout group '{group.get('name')}'",
                })
                break

    return context


# ---------------------------------------------------------------------------
# Step 5: Generate fix suggestion
# ---------------------------------------------------------------------------

def _generate_fix(diagnosis: TimingDiagnosis, spec: dict) -> str:
    """Generate human-readable fix suggestion."""
    div = diagnosis.divergence
    timing = diagnosis.timing_contract_context
    convention = spec.get("timing_convention", {})
    offset = convention.get("golden_to_rtl_offset_cycles", "not set")

    # Find the primary classification
    b_signals = [s for s in diagnosis.all_signals if s.classification.startswith("B_")]
    a_signals = [s for s in diagnosis.all_signals if s.classification == "A"]
    d_signals = [s for s in diagnosis.all_signals if s.classification == "D"]
    u_signals = [s for s in diagnosis.all_signals if s.classification == "unclassifiable"]

    lines = []

    if u_signals:
        for s in u_signals[:3]:
            lines.append(
                f"Signal '{s.signal}' has INCOMPLETE divergence data at cycle {div.cycle}: "
                f"expected=0x{s.expected_value:x}, actual=0x{s.actual_value:x} (values identical or missing)."
            )
        lines.append("")
        lines.append("The divergence was parsed from a degraded source (vcd2table basic format)")
        lines.append("that does not include signal name or value details.")
        lines.append("Fix: Re-run simulation with cocotb INTERNAL mode for accurate per-signal classification.")
        if diagnosis.divergence.degraded:
            lines.append("     (This diagnosis was produced from a vcd2table log without FIRST DIVERGENCE SUMMARY.)")

    elif b_signals:
        for s in b_signals[:3]:  # top 3
            direction = "late" if s.classification == "B_late" else "early"
            lines.append(
                f"Signal '{s.signal}' is {s.offset_cycles} cycle(s) {direction} "
                f"(expected 0x{s.expected_value:x}, got 0x{s.actual_value:x} at cycle {div.cycle})."
            )
        lines.append("")

        if timing:
            lines.append("Related timing_contract edges:")
            for tc in timing[:5]:
                if "source" in tc:
                    lines.append(f"  {tc['source']} -> {tc['destination']}: delay={tc['pipeline_delay']} cycles")
                elif "fanout_group" in tc:
                    lines.append(f"  Fanout group '{tc['fanout_group']}': max_skew={tc['max_delay_skew_cycles']}")
            lines.append("")

        if any("fanout_group" in tc for tc in timing):
            lines.append("Fix options:")
            lines.append("  1. Adjust register stages to equalize delays across the fanout group.")
            lines.append("  2. Add combinational bypass for the later signal.")
            lines.append("  3. Separate the signals into different cycles (sequential assertion).")
        else:
            lines.append("Fix options:")
            lines.append("  1. Add/remove a register stage to align timing.")
            lines.append("  2. Add combinational bypass (_next wire) if same-cycle visibility is needed.")
            lines.append(f"  3. Check DRIVE_PHASE_CYCLES (currently: golden_to_rtl_offset_cycles={offset}).")

    elif a_signals:
        for s in a_signals[:3]:
            lines.append(
                f"Signal '{s.signal}' has computation error at cycle {div.cycle}: "
                f"expected 0x{s.expected_value:x}, got 0x{s.actual_value:x}."
            )
        lines.append("")
        lines.append("Fix: Check the algorithm logic for this signal. Compare golden_model.py")
        lines.append("     with the RTL at the cycle before the first divergence.")

    elif d_signals:
        for s in d_signals[:3]:
            lines.append(
                f"Signal '{s.signal}' is uninitialized at cycle {div.cycle}: "
                f"expected 0x{s.expected_value:x}, got 0x{s.actual_value:x}."
            )
        lines.append("")
        lines.append("Fix: Check register initialization (reset values). The signal may need")
        lines.append("     a non-zero reset value or earlier initialization.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def diagnose(
    log_path: Path,
    golden_path: Path,
    spec_path: Path,
) -> TimingDiagnosis | None:
    """Run full timing diagnosis.

    Returns TimingDiagnosis or None if no divergence found.
    """
    # Step 1: Parse divergence
    div = parse_divergence(log_path)
    if div is None:
        return None

    # Step 2: Load golden trace
    golden_trace = load_golden_trace(golden_path)

    # Step 3: Classify signals
    all_signals = classify_all_signals(div, golden_trace) if golden_trace else [
        SignalDiagnosis(div.signal, "A", expected_value=div.expected, actual_value=div.actual)
    ]

    # Step 4: Load spec and find timing context
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[timing_diagnostic] Cannot read spec.json: {e}", file=sys.stderr)
        return None
    timing_context = find_timing_context(div.signal, spec)

    # Step 5: Build diagnosis
    diagnosis = TimingDiagnosis(
        divergence=div,
        all_signals=all_signals,
        timing_contract_context=timing_context,
    )
    diagnosis.fix_suggestion = _generate_fix(diagnosis, spec)

    # Determine severity
    u_signals = [s for s in all_signals if s.classification == "unclassifiable"]
    b_signals = [s for s in all_signals if s.classification.startswith("B_")]
    if u_signals:
        diagnosis.severity = "low"  # degraded data — cannot act on it reliably
    elif b_signals:
        diagnosis.severity = "high"
    else:
        diagnosis.severity = "medium"

    return diagnosis


def main() -> int:
    parser = argparse.ArgumentParser(description="VeriFlow Timing Diagnostic Tool")
    parser.add_argument("--log", required=True, help="Path to cocotb/sim log")
    parser.add_argument("--golden", required=True, help="Path to golden_model.py")
    parser.add_argument("--spec", required=True, help="Path to spec.json")
    parser.add_argument("--output", help="Write JSON result to this file")
    args = parser.parse_args()

    log_path = Path(args.log)
    golden_path = Path(args.golden)
    spec_path = Path(args.spec)

    for p, name in [(log_path, "log"), (golden_path, "golden"), (spec_path, "spec")]:
        if not p.exists():
            print(f"Error: {name} file not found: {p}", file=sys.stderr)
            return 2

    result = diagnose(log_path, golden_path, spec_path)

    if result is None:
        print("No FIRST DIVERGENCE found in log. Cannot diagnose.")
        return 1

    # Format output
    output = {
        "divergence": {
            "cycle": result.divergence.cycle,
            "signal": result.divergence.signal,
            "expected": f"0x{result.divergence.expected:x}",
            "actual": f"0x{result.divergence.actual:x}",
            "degraded": result.divergence.degraded,
        },
        "signal_classifications": [
            {
                "signal": s.signal,
                "classification": s.classification,
                "offset_cycles": s.offset_cycles,
                "expected": f"0x{s.expected_value:x}",
                "actual": f"0x{s.actual_value:x}",
            }
            for s in result.all_signals
            if s.classification not in ("A",) or s.signal == result.divergence.signal
        ],
        "timing_contract_context": result.timing_contract_context,
        "fix_suggestion": result.fix_suggestion,
        "severity": result.severity,
    }

    print(json.dumps(output, indent=2))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
