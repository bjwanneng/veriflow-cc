"""Generate a markdown expected-trace table from golden_model.py.

Used by SKILL.md Stage 3 (verify_fix) to give the error-recovery loop a
per-cycle reference of golden register values, alongside the simulation log.

Delegates golden model loading to rtl_utils.load_golden_trace().

When `--vcd` is provided, emits a side-by-side markdown table comparing
golden expected values against VCD-recorded actual values per cycle.
Without `--vcd`, falls back to expected-only output (legacy behavior).

CLI:
  python expected_trace_gen.py \\
      --golden  workspace/docs/golden_model.py \\
      --cycles  16 \\
      --output  logs/expected_trace_golden.md \\
      [--vcd    workspace/sim_cocotb/<module>.vcd]   \\
      [--around <divergence_cycle>] [--window 6]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Invoked directly by SKILL.md Stage 3; imports across subdirs (rtl_utils in
# core/, vcd2table in this analysis/ dir). Put the skill root + every subdir on
# sys.path so bare imports resolve on direct invocation.
_SKILL_ROOT = Path(__file__).resolve().parent
while not (_SKILL_ROOT / "SKILL.md").exists() and _SKILL_ROOT.parent != _SKILL_ROOT:
    _SKILL_ROOT = _SKILL_ROOT.parent
for _d in [*_SKILL_ROOT.iterdir(), _SKILL_ROOT]:
    if _d.is_dir() and _d.name not in {"templates", "references", "docs", "__pycache__"} \
            and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))


def _load_golden(path: Path):
    """Load golden model module via rtl_utils canonical loader."""
    from rtl_utils import load_golden_trace
    return load_golden_trace(str(path))


def _fmt_val(v) -> str:
    """Format a Python value for a markdown table cell."""
    if isinstance(v, int):
        return f"0x{v:x}" if v > 9 else str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_fmt_val(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}:{_fmt_val(x)}" for k, x in v.items()) + "}"
    return str(v).replace("|", "\\|")  # markdown-escape


def _strip_reg_suffix(name: str) -> str:
    """Strip a Verilog ``_reg`` register suffix, matching vcd2table._strip_reg.

    Strips ``foo_reg`` -> ``foo`` but preserves double-underscore names like
    ``state__reg`` (some tools emit these; stripping would mangle to ``state_``).
    Keeps this tool consistent with vcd2table so the same signal resolves the
    same way in both the expected-trace and the VCD-derived table.
    """
    if name.endswith("_reg") and not name.endswith("__reg"):
        return name[:-4]
    return name


def _load_vcd_snapshots(vcd_path: Path):
    """Parse a VCD file and return ordered per-posedge state snapshots.

    Returns a list[dict[str, int|str]] indexed by cycle. Each entry maps
    SHORT signal names (e.g., "A_reg", stripped of module prefix) to the
    VCD value at that posedge. Returns [] if parsing fails.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from vcd2table import VCDParser, find_clk_signal, format_vcd_value
    except ImportError:
        return []

    parser = VCDParser()
    try:
        parser.parse(str(vcd_path))
    except Exception as e:
        print(f"[expected_trace_gen] VCD parse failed: {e}", file=sys.stderr)
        return []

    all_signals = set(parser.id_to_name.values())
    clk = find_clk_signal(all_signals)
    if not clk:
        return []

    # Walk timeline, snapshot at each posedge clk
    state: dict[str, str] = {}
    snapshots: list[dict[str, str]] = []
    for t in sorted(parser.changes.keys()):
        changes = parser.changes[t]
        state.update(changes)
        if clk in changes and changes[clk] == "1":
            snap = {}
            for full_name, val in state.items():
                short = full_name.split(".")[-1]
                snap[short] = format_vcd_value(val)
            snapshots.append(snap)
    return snapshots


def _normalize_actual_for_compare(actual_str: str) -> int | None:
    """Parse a VCD-format value into an int when possible, else None.

    Accepts: "32'h12345678", "0xabcd", "5", "1010" — returns the int.
    Returns None for x/z values or unparseable strings.
    """
    s = str(actual_str).strip().lower()
    if not s:
        return None
    # Strip Verilog width prefix: 32'h1234, 8'b1010, 8'd255
    if "'" in s:
        _, _, rest = s.partition("'")
        if rest.startswith("h"):
            body = rest[1:].replace("_", "")
            if any(c in "xz" for c in body):
                return None
            try:
                return int(body, 16)
            except ValueError:
                return None
        if rest.startswith("b"):
            body = rest[1:].replace("_", "")
            if any(c in "xz" for c in body):
                return None
            try:
                return int(body, 2)
            except ValueError:
                return None
        if rest.startswith("d"):
            try:
                return int(rest[1:].replace("_", ""), 10)
            except ValueError:
                return None
    # Hex
    if s.startswith("0x"):
        body = s[2:]
        if any(c in "xz" for c in body):
            return None
        try:
            return int(s, 16)
        except ValueError:
            return None
    # All-binary string (no x/z)
    if all(c in "01" for c in s):
        try:
            return int(s, 2)
        except ValueError:
            return None
    # Decimal
    try:
        return int(s, 10)
    except ValueError:
        return None


def generate_trace(
    golden_path: Path,
    cycles: int,
    output_path: Path,
    vcd_path: Path | None = None,
    around_cycle: int | None = None,
    window: int = 6,
    skip_cycles: int = 0,
) -> bool:
    """Run the golden model and write a markdown table to output_path.

    Returns True on success, False when no interface produced a trace.
    """
    mode = "diff" if vcd_path else "expected-only"
    print(f"[expected-trace] cycles={cycles} mode={mode} skip_cycles={skip_cycles}")

    trace = None
    try:
        cycles_dict = _load_golden(golden_path)
        if not cycles_dict:
            print("[expected-trace] could not generate trace — "
                  "golden_model.py interface not recognized")
            return False
        max_cycle = max(cycles_dict.keys())
        trace = [cycles_dict.get(i, {}) for i in range(max_cycle + 1)]
        print("[expected-trace] used rtl_utils.load_golden_trace()")
    except RuntimeError as e:
        print(f"[expected-trace] could not generate trace: {e}")
        return False

    actual_snapshots = []
    if vcd_path is not None:
        actual_snapshots = _load_vcd_snapshots(vcd_path)
        if not actual_snapshots:
            print(f"[expected-trace] WARN: VCD parse produced no snapshots: {vcd_path}")

    # Determine cycle range to emit
    if around_cycle is not None and around_cycle >= 0:
        lo = max(0, around_cycle - window)
        hi = min(len(trace), around_cycle + window + 1)
        cycle_range = range(lo, hi)
        emitted_label = f"cycles {lo}..{hi - 1} (±{window} around cycle {around_cycle})"
    else:
        cycle_range = range(skip_cycles, min(cycles + skip_cycles, len(trace)))
        emitted_label = f"cycles {skip_cycles}..{skip_cycles + len(list(range(skip_cycles, min(cycles + skip_cycles, len(trace))))) - 1}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        # Alignment header
        if skip_cycles > 0:
            f.write(f"Alignment: skipped golden cycles 0..{skip_cycles - 1} "
                    f"(matching cocotb RESET_CYCLE_SKIP={skip_cycles}). "
                    f"Cycle 0 below = golden cycle {skip_cycles} = cocotb compare cycle 0.\n\n")

        if vcd_path and actual_snapshots:
            f.write("## Cycle Diff (Golden vs VCD)\n\n")
            f.write(f"Emitted: {emitted_label}. Empty `actual` = signal not in VCD.\n\n")
            f.write("| cycle | signal | expected | actual | match |\n")
            f.write("|------:|--------|----------|--------|:-----:|\n")
            mismatch_count = 0
            for i in cycle_range:
                entry = trace[i] if i < len(trace) else {}
                if not isinstance(entry, dict):
                    f.write(f"| {i} | <non-dict> | {_fmt_val(entry)} | | |\n")
                    continue
                snap = actual_snapshots[i] if i < len(actual_snapshots) else {}
                for sig, expected_val in entry.items():
                    short_sig = sig.split(".")[-1]
                    base_sig = _strip_reg_suffix(short_sig)
                    # Explicit membership lookup (not an `or` chain): an `or`
                    # chain treats empty-string/falsy sentinels as "missing",
                    # which can drop a legitimate value. Try the short name,
                    # then the _reg-stripped base, then the base + "_reg".
                    if short_sig in snap:
                        actual_str = snap[short_sig]
                    elif base_sig in snap:
                        actual_str = snap[base_sig]
                    elif f"{base_sig}_reg" in snap:
                        actual_str = snap[f"{base_sig}_reg"]
                    else:
                        actual_str = ""
                    actual_int = _normalize_actual_for_compare(actual_str)
                    expected_int = expected_val if isinstance(expected_val, int) else None
                    if expected_int is not None and actual_int is not None:
                        match = "✓" if expected_int == actual_int else "✗"
                        if expected_int != actual_int:
                            mismatch_count += 1
                    else:
                        match = "?"
                    f.write(
                        f"| {i} | {sig} | {_fmt_val(expected_val)} "
                        f"| {actual_str or '_'} | {match} |\n"
                    )
            f.write(f"\n**Summary**: {mismatch_count} mismatched signal(s) "
                    f"across emitted range.\n")
            print(f"[expected-trace] -> {output_path} "
                  f"({len(list(cycle_range))} cycles, {mismatch_count} mismatches)")
        else:
            f.write("## Golden Model Expected Trace\n\n")
            f.write("| cycle | signals |\n")
            f.write("|------:|---------|\n")
            for i in cycle_range:
                entry = trace[i] if i < len(trace) else {}
                if not isinstance(entry, dict):
                    f.write(f"| {i} | <non-dict entry: {type(entry).__name__}> |\n")
                    continue
                signals = " ".join(f"{k}={_fmt_val(v)}" for k, v in entry.items())
                f.write(f"| {i} | {signals} |\n")
            print(f"[expected-trace] -> {output_path} ({len(trace)} cycles)")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate expected_trace_golden.md")
    ap.add_argument("--golden", required=True, help="Path to golden_model.py")
    ap.add_argument("--cycles", type=int, default=16,
                    help="Max cycles to record in expected-only mode (default 16)")
    ap.add_argument("--output", required=True, help="Destination .md file")
    ap.add_argument("--vcd", default=None,
                    help="Optional VCD file. When set, emits side-by-side expected/actual diff.")
    ap.add_argument("--around", type=int, default=None,
                    help="Center the emitted cycle range on this cycle (e.g., the divergence cycle).")
    ap.add_argument("--window", type=int, default=6,
                    help="Cycles to emit on each side of --around (default 6).")
    ap.add_argument("--skip-cycles", type=int, default=0,
                    help="Skip first N golden cycles to align with cocotb RESET_CYCLE_SKIP (default 0).")
    args = ap.parse_args(argv)

    generate_trace(
        Path(args.golden).resolve(),
        args.cycles,
        Path(args.output).resolve(),
        vcd_path=Path(args.vcd).resolve() if args.vcd else None,
        around_cycle=args.around,
        window=args.window,
        skip_cycles=args.skip_cycles,
    )
    # We always exit 0; a missing trace is a warning, not a hard error.
    return 0


if __name__ == "__main__":
    sys.exit(main())
