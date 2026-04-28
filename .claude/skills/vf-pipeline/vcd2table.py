#!/usr/bin/env python3
"""vcd2table.py — Convert a VCD file to a cycle-accurate text table for LLM analysis.

Usage:
    python3 vcd2table.py <vcd_file> [options]

Options:
    --sim-log <path>        sim.log or sim_<module>.log — extract failing signal names
    --timing-yaml <path>    timing_model.yaml — annotate assertion violations
    --signals <s1,s2,...>   comma-separated list of extra signals to always include
    --window <N>            cycles around each failure to show (default: 15)
    --module <name>         only show signals from this module scope
    --output <path>         write table to file instead of stdout

Output:
    A text table written to stdout (or --output), formatted for direct LLM reading.
    Columns: Cycle | <signal1> | <signal2> | ... | NOTES
    Rows: one per posedge clk
    NOTES column: flags timing_model assertion violations and [FAIL] markers.
"""

import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict


# ─── VCD Parser ───────────────────────────────────────────────────────────────

class VCDParser:
    """Minimal VCD parser. Handles scalar and vector signals."""

    def __init__(self):
        self.signals = {}       # id → {name, width, scope}
        self.id_to_name = {}    # id → full_name
        self.changes = defaultdict(dict)  # time → {full_name: value}
        self.timescale = "1ns"
        self._scope_stack = []

    def parse(self, path: str):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        # Split into tokens
        tokens = iter(text.split())
        current_time = 0

        try:
            tok = next(tokens)
            while True:
                if tok == "$timescale":
                    ts_parts = []
                    tok = next(tokens)
                    while tok != "$end":
                        ts_parts.append(tok)
                        tok = next(tokens)
                    self.timescale = " ".join(ts_parts)

                elif tok == "$scope":
                    scope_type = next(tokens)
                    scope_name = next(tokens)
                    self._scope_stack.append(scope_name)
                    next(tokens)  # $end

                elif tok == "$upscope":
                    if self._scope_stack:
                        self._scope_stack.pop()
                    next(tokens)  # $end

                elif tok == "$var":
                    var_type = next(tokens)
                    width = int(next(tokens))
                    var_id = next(tokens)
                    var_name = next(tokens)
                    # skip bit-select or $end
                    nxt = next(tokens)
                    if nxt != "$end":
                        next(tokens)  # $end
                    scope = ".".join(self._scope_stack)
                    full_name = f"{scope}.{var_name}" if scope else var_name
                    self.signals[var_id] = {
                        "name": var_name,
                        "full_name": full_name,
                        "width": width,
                        "scope": scope,
                    }
                    self.id_to_name[var_id] = full_name

                elif tok == "$dumpvars" or tok == "$dumpall":
                    tok = next(tokens)
                    while tok != "$end":
                        self._parse_value_change(tok, current_time)
                        tok = next(tokens)

                elif tok.startswith("#"):
                    current_time = int(tok[1:])

                elif tok[0] in "01xXzZ":
                    # Scalar: 0/1/x/z followed by id
                    val = tok[0].lower()
                    var_id = tok[1:]
                    if var_id in self.id_to_name:
                        self.changes[current_time][self.id_to_name[var_id]] = val

                elif tok[0] in "bBrR":
                    # Vector: b<value> <id>
                    val = tok[1:]
                    var_id = next(tokens)
                    if var_id in self.id_to_name:
                        self.changes[current_time][self.id_to_name[var_id]] = val

                tok = next(tokens)

        except StopIteration:
            pass

        return self


    def _parse_value_change(self, tok, time):
        if tok[0] in "01xXzZ" and len(tok) > 1:
            val = tok[0].lower()
            var_id = tok[1:]
            if var_id in self.id_to_name:
                self.changes[time][self.id_to_name[var_id]] = val
        elif tok[0] in "bBrR":
            pass  # handled in main loop with next token


# ─── Signal Selection ─────────────────────────────────────────────────────────

def extract_failing_signals_from_log(log_path: str) -> list[str]:
    """Parse sim.log / sim_<module>.log for signal names in [FAIL] lines."""
    signals = []
    if not Path(log_path).exists():
        return signals

    text = Path(log_path).read_text(encoding="utf-8", errors="replace")

    # Match patterns like: [FAIL] cycle=5 expected data_out=0xFF got 0x00
    # or: [FAIL] Test 3: state_reg expected IDLE got CALC
    fail_lines = [l for l in text.splitlines() if re.search(r'\[FAIL\]|FAILED:', l)]

    for line in fail_lines:
        # Extract identifiers that look like signal names (snake_case words)
        words = re.findall(r'\b([a-z][a-z0-9_]+(?:_reg|_next|_out|_in|_valid|_ready|_en|_flag)?)\b', line)
        signals.extend(words)

    # Remove common non-signal words
    noise = {"expected", "got", "test", "cycle", "failed", "assert", "module", "at", "in"}
    return [s for s in dict.fromkeys(signals) if s not in noise]


def extract_timing_assertions(timing_yaml_path: str) -> list[dict]:
    """Parse timing_model.yaml assertions into structured form.

    Returns list of {name, description, assertions: [str], stimulus: [dict]}
    """
    if not Path(timing_yaml_path).exists():
        return []

    text = Path(timing_yaml_path).read_text(encoding="utf-8", errors="replace")
    scenarios = []

    # Simple YAML parser for our known structure
    current = None
    in_assertions = False
    in_stimulus = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:"):
            if current:
                scenarios.append(current)
            current = {"name": stripped[7:].strip(), "assertions": [], "stimulus": []}
            in_assertions = False
            in_stimulus = False
        elif current and stripped.startswith("assertions:"):
            in_assertions = True
            in_stimulus = False
        elif current and stripped.startswith("stimulus:"):
            in_stimulus = True
            in_assertions = False
        elif current and in_assertions and stripped.startswith("- "):
            current["assertions"].append(stripped[2:].strip().strip('"'))
        elif current and in_stimulus and stripped.startswith("- {"):
            current["stimulus"].append(stripped[2:])

    if current:
        scenarios.append(current)

    return scenarios


def parse_assertion(assertion_str: str) -> dict | None:
    """Parse SVA-style assertion string into {signal, delay_min, delay_max, expected}.

    Supports: "signal_A |-> ##N signal_B" and "condition |-> ##[min:max] expected"
    Returns None if unparseable.
    """
    m = re.match(r'(.+?)\s*\|->\s*##(\[[\d:]+\]|\d+)\s*(.+)', assertion_str)
    if not m:
        return None
    antecedent = m.group(1).strip()
    delay_str = m.group(2).strip()
    consequent = m.group(3).strip()

    if delay_str.startswith("["):
        parts = delay_str[1:-1].split(":")
        delay_min, delay_max = int(parts[0]), int(parts[1])
    else:
        delay_min = delay_max = int(delay_str)

    return {
        "antecedent": antecedent,
        "consequent": consequent,
        "delay_min": delay_min,
        "delay_max": delay_max,
    }


# ─── Waveform Table Builder ───────────────────────────────────────────────────

def find_clk_signal(all_signals: set[str]) -> str | None:
    for name in sorted(all_signals):
        basename = name.split(".")[-1]
        if basename in ("clk", "clock", "clk_i"):
            return name
    return None


def find_rst_signal(all_signals: set[str]) -> str | None:
    for name in sorted(all_signals):
        basename = name.split(".")[-1]
        if basename in ("rst", "reset", "rst_i", "rst_n"):
            return name
    return None


def find_fsm_signals(all_signals: set[str]) -> list[str]:
    fsm_signals = []
    for name in sorted(all_signals):
        basename = name.split(".")[-1]
        if re.search(r'state|fsm|phase|mode', basename, re.IGNORECASE):
            fsm_signals.append(name)
    return fsm_signals


def build_cycle_table(
    vcd: VCDParser,
    include_signals: list[str],
    window_cycles: list[tuple[int, int]],  # [(start_cycle, end_cycle), ...]
    annotations: dict[int, list[str]],     # cycle → [annotation strings]
    clk_name: str,
) -> str:
    """Build a text cycle table from VCD data.

    Returns formatted string.
    """
    if not include_signals:
        return "(no signals to display)\n"

    # Build timeline: sort all timestamps, find posedge clk
    all_times = sorted(vcd.changes.keys())
    if not all_times:
        return "(VCD has no signal changes)\n"

    # Reconstruct signal state across all time steps
    current_state: dict[str, str] = {}
    cycle_snapshots: list[tuple[int, dict[str, str]]] = []  # (cycle_num, state_at_posedge)
    cycle_num = -1

    for t in all_times:
        changes = vcd.changes[t]
        current_state.update(changes)

        # Detect posedge clk
        if clk_name in changes and changes[clk_name] == "1":
            cycle_num += 1
            cycle_snapshots.append((cycle_num, dict(current_state)))

    if not cycle_snapshots:
        return "(No clock edges found in VCD)\n"

    # Determine which cycles to show based on window
    if window_cycles:
        show_cycles = set()
        for start, end in window_cycles:
            for c in range(max(0, start), min(end + 1, len(cycle_snapshots))):
                show_cycles.add(c)
    else:
        show_cycles = set(range(len(cycle_snapshots)))

    if not show_cycles:
        return "(No cycles in display window)\n"

    # Shorten signal names — strip common scope prefix
    def short_name(name: str) -> str:
        parts = name.split(".")
        return parts[-1] if len(parts) > 1 else name

    col_names = ["Cycle"] + [short_name(s) for s in include_signals] + ["NOTES"]

    # Collect rows
    rows = []
    for cycle_num, state in cycle_snapshots:
        if cycle_num not in show_cycles:
            continue

        row = [str(cycle_num)]
        for sig in include_signals:
            val = state.get(sig, "?")
            # Format binary vectors as hex
            if len(val) > 4 and all(c in "01xzXZ" for c in val):
                try:
                    hex_val = hex(int(val.replace("x", "0").replace("z", "0"), 2))
                    val = hex_val
                except ValueError:
                    pass
            row.append(val)

        notes = annotations.get(cycle_num, [])
        row.append(" | ".join(notes) if notes else "")
        rows.append(row)

    # Calculate column widths
    col_widths = [max(len(col_names[i]), max((len(r[i]) for r in rows), default=0))
                  for i in range(len(col_names))]

    # Format header
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header = "|" + "|".join(f" {col_names[i]:<{col_widths[i]}} " for i in range(len(col_names))) + "|"

    lines = [sep, header, sep]
    for row in rows:
        padded = [f" {row[i]:<{col_widths[i]}} " for i in range(len(col_names))]
        lines.append("|" + "|".join(padded) + "|")
    lines.append(sep)

    return "\n".join(lines) + "\n"


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Convert VCD to LLM-readable cycle table")
    parser.add_argument("vcd_file", help="Path to .vcd file")
    parser.add_argument("--sim-log", help="sim.log path — extract failing signal names")
    parser.add_argument("--timing-yaml", help="timing_model.yaml — annotate assertion violations")
    parser.add_argument("--signals", help="Extra signals to always include (comma-separated)")
    parser.add_argument("--window", type=int, default=15, help="Cycles around each failure (default 15)")
    parser.add_argument("--module", help="Filter signals to this module scope")
    parser.add_argument("--output", help="Write output to file instead of stdout")
    args = parser.parse_args()

    if not Path(args.vcd_file).exists():
        print(f"ERROR: VCD file not found: {args.vcd_file}", file=sys.stderr)
        sys.exit(1)

    # 1. Parse VCD
    print(f"[vcd2table] Parsing {args.vcd_file}...", file=sys.stderr)
    vcd = VCDParser().parse(args.vcd_file)

    all_signal_names = set(vcd.id_to_name.values())
    if not all_signal_names:
        print("ERROR: No signals found in VCD file", file=sys.stderr)
        sys.exit(1)

    print(f"[vcd2table] Found {len(all_signal_names)} signals, "
          f"{len(vcd.changes)} time steps", file=sys.stderr)

    # 2. Find clk and rst
    clk_name = find_clk_signal(all_signal_names)
    if not clk_name:
        print("ERROR: Could not find clock signal (clk/clock/clk_i)", file=sys.stderr)
        sys.exit(1)

    rst_name = find_rst_signal(all_signal_names)
    fsm_signals = find_fsm_signals(all_signal_names)

    # 3. Determine signals to show
    include_signals = []
    if rst_name:
        include_signals.append(rst_name)

    # FSM signals always included
    include_signals.extend(fsm_signals[:3])  # cap at 3 FSM signals

    # Signals from failing assertions in sim.log
    if args.sim_log:
        failing_sigs = extract_failing_signals_from_log(args.sim_log)
        print(f"[vcd2table] Failing signals from log: {failing_sigs}", file=sys.stderr)
        for sig_basename in failing_sigs:
            # Find full name matching this basename
            matches = [n for n in all_signal_names if n.split(".")[-1] == sig_basename]
            if args.module:
                matches = [n for n in matches if args.module in n]
            include_signals.extend(matches[:2])  # cap at 2 matches per name

    # Extra signals from --signals flag
    if args.signals:
        for sig_basename in args.signals.split(","):
            sig_basename = sig_basename.strip()
            matches = [n for n in all_signal_names if n.split(".")[-1] == sig_basename]
            include_signals.extend(matches[:2])

    # Deduplicate, preserve order
    seen = set()
    include_signals = [s for s in include_signals if not (s in seen or seen.add(s))]

    if not include_signals:
        # Fallback: show all top-level port-like signals
        include_signals = sorted(
            [n for n in all_signal_names if n.split(".")[-1] not in ("clk", "clock")],
        )[:12]
        print(f"[vcd2table] No specific signals identified — showing first 12", file=sys.stderr)

    print(f"[vcd2table] Displaying {len(include_signals)} signals: "
          f"{[s.split('.')[-1] for s in include_signals]}", file=sys.stderr)

    # 4. Find failure cycles from sim.log
    fail_cycles: list[int] = []
    if args.sim_log and Path(args.sim_log).exists():
        log_text = Path(args.sim_log).read_text(encoding="utf-8", errors="replace")
        for line in log_text.splitlines():
            m = re.search(r'cycle[=:\s]+(\d+)', line, re.IGNORECASE)
            if m and re.search(r'\[FAIL\]|FAILED:', line):
                fail_cycles.append(int(m.group(1)))

    # 5. Build annotations from timing_model.yaml assertions
    annotations: dict[int, list[str]] = defaultdict(list)

    timing_scenarios = []
    if args.timing_yaml:
        timing_scenarios = extract_timing_assertions(args.timing_yaml)

    # Mark fail cycles in annotations
    for fc in fail_cycles:
        annotations[fc].append("[FAIL]")

    # 6. Determine display windows
    if fail_cycles:
        window_cycles = [(max(0, fc - args.window // 2), fc + args.window // 2)
                         for fc in fail_cycles]
    else:
        # No specific failures found — show first 50 cycles
        window_cycles = [(0, 49)]

    # 7. Build table
    table = build_cycle_table(vcd, include_signals, window_cycles, annotations, clk_name)

    # 8. Build header summary
    output_parts = []
    output_parts.append("=" * 72)
    output_parts.append("VCD WAVEFORM TABLE — for LLM timing analysis")
    output_parts.append(f"VCD file  : {args.vcd_file}")
    output_parts.append(f"Timescale : {vcd.timescale}")
    output_parts.append(f"Clock     : {clk_name}")
    output_parts.append(f"Signals   : {', '.join(s.split('.')[-1] for s in include_signals)}")
    if fail_cycles:
        output_parts.append(f"Fail cycles: {fail_cycles}  (window ±{args.window//2} cycles shown)")
    else:
        output_parts.append("No [FAIL] cycles detected — showing first 50 cycles")
    output_parts.append("=" * 72)
    output_parts.append("")

    # Timing assertion summary
    if timing_scenarios:
        output_parts.append("TIMING ASSERTIONS (from timing_model.yaml):")
        for sc in timing_scenarios:
            output_parts.append(f"  Scenario: {sc['name']}")
            for a in sc["assertions"]:
                output_parts.append(f"    {a}")
        output_parts.append("")

    output_parts.append(table)

    # 9. Guidance for LLM
    if fail_cycles:
        output_parts.append("")
        output_parts.append("DIAGNOSIS HINTS:")
        output_parts.append("  1. Look at the [FAIL] row — note the cycle number.")
        output_parts.append("  2. Trace the failing signal backwards: when did it last change?")
        output_parts.append("  3. Check FSM state at [FAIL] cycle — is it the expected state?")
        output_parts.append("  4. Compare with timing_model.yaml assertions above.")
        output_parts.append("  5. Common causes: off-by-one pipeline stage, reset not clearing"
                             " output register, handshake held too long/short.")

    final_output = "\n".join(output_parts)

    # 10. Write output
    if args.output:
        Path(args.output).write_text(final_output, encoding="utf-8")
        print(f"[vcd2table] Written to {args.output}", file=sys.stderr)
    else:
        print(final_output)


if __name__ == "__main__":
    main()
