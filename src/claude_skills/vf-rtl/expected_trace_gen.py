"""Generate a markdown expected-trace table from golden_model.py.

Used by SKILL.md Stage 3 (verify_fix) to give the error-recovery loop a
per-cycle reference of golden register values, alongside the simulation log.

Tries three golden_model.py interfaces, in order:
  1. compute(inputs, trace=True) + TEST_VECTORS[0]
  2. run(0) -> list[dict]
  3. simulate(inputs, trace=True) + TEST_VECTORS[0]

The first successful call wins. Missing or unrecognized interfaces are not
fatal — we print a diagnostic line and exit 0 without producing the file.

CLI:
  python expected_trace_gen.py \\
      --golden  workspace/docs/golden_model.py \\
      --cycles  16 \\
      --output  logs/expected_trace_golden.md
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def _load_golden(path: Path):
    spec = importlib.util.spec_from_file_location("_gm", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load golden module at {path}")
    gm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gm)
    return gm


def _fmt_val(v) -> str:
    """Format a Python value for a markdown table cell."""
    if isinstance(v, int):
        return f"0x{v:x}" if v > 9 else str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_fmt_val(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}:{_fmt_val(x)}" for k, x in v.items()) + "}"
    return str(v).replace("|", "\\|")  # markdown-escape


def _try_compute(gm):
    if hasattr(gm, "compute") and hasattr(gm, "TEST_VECTORS"):
        tv = gm.TEST_VECTORS[0]
        inputs = tv.get("inputs", tv)
        return gm.compute(inputs, trace=True), "gm.compute(inputs, trace=True)"
    return None, None


def _try_run(gm):
    if hasattr(gm, "run"):
        return gm.run(0), "gm.run(0)"
    return None, None


def _try_simulate(gm):
    if hasattr(gm, "simulate") and hasattr(gm, "TEST_VECTORS"):
        tv = gm.TEST_VECTORS[0]
        inputs = tv.get("inputs", tv)
        return gm.simulate(inputs, trace=True), "gm.simulate(inputs, trace=True)"
    return None, None


def generate_trace(golden_path: Path, cycles: int, output_path: Path) -> bool:
    """Run the golden model and write a markdown table to output_path.

    Returns True on success, False when no interface produced a trace.
    """
    gm = _load_golden(golden_path)
    print(f"[expected-trace] cycles={cycles}")

    trace = None
    for attempt in (_try_compute, _try_run, _try_simulate):
        try:
            t, label = attempt(gm)
        except Exception as e:
            print(f"[expected-trace] {attempt.__name__} failed: {e}")
            continue
        if t is not None:
            trace = t
            print(f"[expected-trace] used {label}")
            break

    if trace is None:
        print("[expected-trace] could not generate trace — "
              "golden_model.py interface not recognized")
        return False

    if not isinstance(trace, list):
        print(f"[expected-trace] WARN: trace is {type(trace).__name__}, not list — "
              "golden_model.py may have returned the final dict instead of per-cycle "
              "records. Skipping expected_trace_golden.md generation.")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        f.write("## Golden Model Expected Trace\n\n")
        f.write("| cycle | signals |\n")
        f.write("|------:|---------|\n")
        for i, entry in enumerate(trace[:cycles]):
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
                    help="Max cycles to record (default 16)")
    ap.add_argument("--output", required=True, help="Destination .md file")
    args = ap.parse_args(argv)

    generate_trace(
        Path(args.golden).resolve(),
        args.cycles,
        Path(args.output).resolve(),
    )
    # We always exit 0; a missing trace is a warning, not a hard error.
    return 0


if __name__ == "__main__":
    sys.exit(main())
