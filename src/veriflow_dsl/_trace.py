"""VeriFlow DSL trace comparison utilities.

Provides TraceDiff and diff_traces() for comparing golden model cycle traces
against RTL simulation traces (from VCD or cocotb).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["TraceDiff", "diff_traces"]


@dataclass
class TraceDiff:
    """Result of comparing two cycle-accurate traces.

    Attributes:
        first_divergence_cycle: cycle index where first mismatch was found
        first_divergence_signal: signal name that first mismatched
        expected: golden model value
        actual: RTL simulation value
        total_mismatches: total number of mismatched signals across all cycles
        classification: bug type classification ("A" data, "B" timing, "D" init)
    """
    first_divergence_cycle: int
    first_divergence_signal: str
    expected: int
    actual: int
    total_mismatches: int
    classification: str


def _classify(
    expected: int,
    actual: int,
    cycle: int,
    signal: str,
    golden: list[dict] | None = None,
    skip_signals: set[str] | None = None,
) -> str:
    """Classify a divergence into bug type A/B/D with direction.

    Classification rules (priority order):
        1. B (timing): correct value appears at a different cycle in the golden
           trace. Sub-classified as B_early (RTL value arrives earlier than
           golden expects) or B_late (RTL value arrives later).
        2. D (initialization): actual == 0 and expected != 0, AND no timing
           offset was found. This avoids masking genuine timing offsets where
           the "late" value happens to be 0.
        3. A (computation): default — value is simply wrong, no timing
           alignment found.

    This order (B before D) differs from the earlier implementation that
    prioritized D over B. Testing showed that D-first misclassified timing
    offsets as initialization errors whenever actual==0 (common when a
    registered signal arrives 1 cycle late).
    """
    skip = skip_signals or set()

    # Check Type B FIRST — timing offset detected by searching nearby
    # golden cycles for a match with the actual value.
    # Skip actual==0: 0 is the universal default/reset value and will match
    # trivially at any cycle, producing false timing-offset classifications.
    if golden is not None and actual != 0:
        search_window = 5
        for offset in range(-search_window, search_window + 1):
            if offset == 0:
                continue
            check_cycle = cycle + offset
            if 0 <= check_cycle < len(golden):
                g_entry = golden[check_cycle]
                if signal not in skip and signal in g_entry:
                    if g_entry[signal] == actual:
                        direction = "early" if offset > 0 else "late"
                        return f"B_{direction}"

    # Type D: initialization error — actual is 0 but golden expects non-zero.
    # Only classified as D when no timing offset was found (Type B checked
    # first). This avoids false D classifications for timing offsets where
    # the late signal happens to still be 0.
    if actual == 0 and expected != 0:
        return "D"

    # Default: Type A (computation error)
    return "A"


def diff_traces(
    golden: list[dict],
    rtl: list[dict],
    *,
    cycle_offset: int = 0,
    skip_signals: set[str] | None = None,
) -> TraceDiff | None:
    """Compare golden model trace against RTL trace, return first divergence.

    Args:
        golden: list of per-cycle dicts from golden model (CycleSimulator or
            design_spec.py compute(trace=True))
        rtl: list of per-cycle dicts from VCD/cocotb
        cycle_offset: number of golden trace cycles to skip at the start
            (for alignment with RTL timing)
        skip_signals: signal names to skip during comparison

    Returns:
        TraceDiff if a mismatch is found, None if traces are identical.
    """
    skip = skip_signals or set()
    total_mismatches = 0
    first_diff: TraceDiff | None = None
    golden_start = cycle_offset

    max_cycles = min(len(golden) - golden_start, len(rtl))

    for i in range(max_cycles):
        g_entry = golden[golden_start + i]
        r_entry = rtl[i]

        for sig_name in g_entry:
            if sig_name in skip:
                continue
            if sig_name not in r_entry:
                continue

            g_val = g_entry[sig_name]
            r_val = r_entry[sig_name]

            if isinstance(g_val, int) and isinstance(r_val, int):
                if g_val != r_val:
                    total_mismatches += 1
                    if first_diff is None:
                        first_diff = TraceDiff(
                            first_divergence_cycle=i,
                            first_divergence_signal=sig_name,
                            expected=g_val,
                            actual=r_val,
                            total_mismatches=0,
                            classification=_classify(g_val, r_val, i, sig_name, golden, skip),
                        )

    if first_diff is not None:
        first_diff.total_mismatches = total_mismatches
        return first_diff

    return None
