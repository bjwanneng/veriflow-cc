"""veriflow_dsl.trace_export — Markdown trace exporter.

Runs a DSL Module (or @vf_block function) through CycleSimulator and
formats the per-cycle snapshot list as a markdown table that can be
embedded in LLM prompts.

Public API:
    export_trace(module, *, cycles, inputs=None) -> str
    export_trace_for_block(block_func, *, cycles, inputs=None) -> str

CLI:
    python -m veriflow_dsl.trace_export \
        --timing-model <path> --block <name> --cycles N \
        [--inputs inputs.json] --output trace.md

Width-based formatting:
    1 bit       -> "0" / "1"  (no prefix)
    2-7 bit     -> decimal
    >= 8 bit    -> hex with 0x prefix, zero-padded to ceil(width/4) digits
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from ._module import Module
from ._simulator import CycleSimulator
from ._spec import vf_block as _vf_block_marker  # noqa: F401 — for clarity
from ._adapter import from_timing_model

__all__ = ["export_trace", "export_trace_for_block"]


# ---------------------------------------------------------------------------
# Value formatting
# ---------------------------------------------------------------------------

def _format_value(value: int, width: int) -> str:
    """Format an integer value according to its bit width.

    1 bit: '0' or '1'.
    2-7 bit: decimal.
    >= 8 bit: hex, zero-padded to width/4 digits, prefixed with '0x'.
    """
    masked = value & ((1 << width) - 1)
    if width == 1:
        return "1" if masked else "0"
    if width < 8:
        return str(masked)
    hex_digits = (width + 3) // 4
    return f"0x{masked:0{hex_digits}x}"


# ---------------------------------------------------------------------------
# Column ordering
# ---------------------------------------------------------------------------

def _column_order(analysis: dict) -> list[str]:
    """Order columns deterministically: registers first, then comb wires,
    then inputs. This matches how a designer would read a waveform.
    """
    sigs: dict[str, dict] = analysis["signals"]

    regs: list[str] = []
    wires: list[str] = []
    inputs: list[str] = []

    for name, info in sigs.items():
        if info["direction"] == "input":
            inputs.append(name)
        elif info["timing"] == "reg_next":
            regs.append(name)
        else:
            wires.append(name)

    return regs + wires + inputs


# ---------------------------------------------------------------------------
# Markdown table builder
# ---------------------------------------------------------------------------

def _build_meta_block(module: Module, cycles: int) -> str:
    """Header lines describing the module and signal widths."""
    analysis = module.analyze()
    sigs = analysis["signals"]

    regs = [(n, sigs[n]["width"]) for n in sigs
            if sigs[n]["direction"] != "input" and sigs[n]["timing"] == "reg_next"]
    wires = [(n, sigs[n]["width"]) for n in sigs
             if sigs[n]["direction"] != "input" and sigs[n]["timing"] != "reg_next"]
    inputs = [(n, sigs[n]["width"]) for n in sigs
              if sigs[n]["direction"] == "input"]

    lines = [f"## {module.name} — {cycles}-cycle trace", ""]
    if regs:
        reg_str = ", ".join(f"{n}[{w}]" for n, w in regs)
        lines.append(f"- registers: {reg_str}")
    if wires:
        wire_str = ", ".join(f"{n}[{w}]" for n, w in wires)
        lines.append(f"- wires: {wire_str}")
    if inputs:
        in_str = ", ".join(f"{n}[{w}]" for n, w in inputs)
        lines.append(f"- inputs: {in_str}")
    lines.append("")
    return "\n".join(lines)


def _build_table(module: Module, trace: list[dict[str, int]]) -> str:
    """Build the markdown table from a CycleSimulator trace."""
    analysis = module.analyze()
    sigs = analysis["signals"]
    columns = _column_order(analysis)

    header_cells = ["cycle"] + columns
    sep_cells = ["---:"] + [
        ("---:" if sigs[c]["width"] > 1 else ":---:") for c in columns
    ]

    lines = []
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("|" + "|".join(sep_cells) + "|")

    for cycle, snap in enumerate(trace):
        row = [str(cycle)]
        for col in columns:
            width = sigs[col]["width"]
            row.append(_format_value(snap.get(col, 0), width))
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_trace(
    module: Module,
    *,
    cycles: int,
    inputs: list[dict[str, int]] | None = None,
) -> str:
    """Run *module* for *cycles* and return a markdown trace string.

    Args:
        module: a veriflow_dsl Module ready for simulation.
        cycles: number of clock cycles to record.
        inputs: optional list of input dicts, one per cycle.
            If omitted or shorter than *cycles*, missing cycles drive 0
            on every input port.

    Returns:
        Markdown string with a meta block followed by a cycle-indexed table.
    """
    if cycles <= 0:
        raise ValueError(f"cycles must be > 0, got {cycles}")

    sim = CycleSimulator(module)
    trace = sim.run(cycles, inputs)

    meta = _build_meta_block(module, cycles)
    table = _build_table(module, trace)
    return meta + table + "\n"


def export_trace_for_block(
    block_func,
    *,
    cycles: int,
    inputs: list[dict[str, int]] | None = None,
) -> str:
    """Adapter: take a @vf_block function, build a Module, return markdown trace."""
    if not hasattr(block_func, "_vf_block_type"):
        raise TypeError(
            f"{block_func.__name__} must be decorated with @vf_block"
        )
    module = from_timing_model(block_func)
    return export_trace(module, cycles=cycles, inputs=inputs)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_block_from_file(tm_path: Path, block_name: str):
    """Import a timing_model.py file and return the named @vf_block function."""
    spec = importlib.util.spec_from_file_location(
        f"_vf_tm_{tm_path.stem}", str(tm_path),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load timing model from {tm_path}")
    module_obj = importlib.util.module_from_spec(spec)
    # Make the file's directory importable in case it has sibling helpers
    sys.path.insert(0, str(tm_path.parent))
    try:
        spec.loader.exec_module(module_obj)
    finally:
        if str(tm_path.parent) in sys.path:
            sys.path.remove(str(tm_path.parent))
    if not hasattr(module_obj, block_name):
        raise AttributeError(
            f"{tm_path} does not define a function named {block_name!r}"
        )
    return getattr(module_obj, block_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="veriflow_dsl.trace_export",
        description="Export a DSL @vf_block function as a markdown trace.",
    )
    parser.add_argument("--timing-model", required=True,
                        help="Path to a timing_model.py defining @vf_block functions.")
    parser.add_argument("--block", required=True,
                        help="Name of the @vf_block function to simulate.")
    parser.add_argument("--cycles", type=int, default=8,
                        help="Number of cycles to simulate (default 8).")
    parser.add_argument("--inputs",
                        help="Path to a JSON file: list[dict[str,int]] of per-cycle inputs.")
    parser.add_argument("--output", required=True,
                        help="Path to write the markdown trace.")

    args = parser.parse_args(argv)

    tm_path = Path(args.timing_model)
    if not tm_path.is_file():
        print(f"Error: --timing-model {tm_path} not found", file=sys.stderr)
        return 2

    block_func = _load_block_from_file(tm_path, args.block)

    inputs: list[dict[str, int]] | None = None
    if args.inputs:
        inputs_path = Path(args.inputs)
        if not inputs_path.is_file():
            print(f"Error: --inputs {inputs_path} not found", file=sys.stderr)
            return 2
        inputs = json.loads(inputs_path.read_text())
        if not isinstance(inputs, list):
            print(f"Error: --inputs file must contain a JSON list", file=sys.stderr)
            return 2

    md = export_trace_for_block(block_func, cycles=args.cycles, inputs=inputs)
    Path(args.output).write_text(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
