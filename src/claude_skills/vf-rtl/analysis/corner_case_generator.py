#!/usr/bin/env python3
"""Corner-case test vector generator for VeriFlow-CC.

Auto-generates boundary-VALUE test vectors from spec.json input ports:
- all-zeros
- all-ones (max unsigned)
- LSB-only (min non-zero)
- alternating 1-0 (0xAA..AA)
- MSB-only (sign bit / 2^(N-1))

These are per-port value patterns applied simultaneously to all inputs; the
consuming agent (vf-tb-gen) is responsible for protocol-legal stimulus and
for sequence scenarios (reset-mid-operation, backpressure/stall), which
cannot be derived from port widths alone.

Usage:
    python corner_case_generator.py --spec spec.json --output corner_cases.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Fallback for ports whose width cannot be parsed (e.g. parameterized
# "[W-1:0]" ranges — the parameter value is not resolvable from the spec
# text). Always warned on stderr; never silent.
_DEFAULT_WIDTH = 32


def _bitwidth_from_type(port_type: str, port_name: str = "") -> int:
    """Extract bit width from Verilog type like 'wire [31:0]'."""
    if "[" not in port_type or "]" not in port_type:
        return 1
    range_str = port_type.split("[", 1)[1].split("]", 1)[0]
    try:
        if ":" in range_str:
            high, low = (s.strip() for s in range_str.split(":", 1))
            return int(high, 0) - int(low, 0) + 1
        return int(range_str, 0) + 1
    except ValueError:
        print(f"[corner_case] WARNING: cannot parse width from type "
              f"{port_type!r} of port {port_name!r} — assuming "
              f"{_DEFAULT_WIDTH} bits", file=sys.stderr)
        return _DEFAULT_WIDTH


def generate_corner_cases(spec: dict) -> list[dict]:
    """Generate corner-case test vectors from spec.json ports."""
    cases = []
    modules = spec.get("modules", [])
    if isinstance(modules, dict):
        modules = list(modules.values())

    top_module = None
    for m in modules:
        if m.get("module_type") == "top":
            top_module = m
            break
    if not top_module:
        return cases

    input_ports = [
        p for p in top_module.get("ports", [])
        if p.get("direction") == "input" and p.get("name") not in ("clk", "rst", "rst_n")
    ]

    if not input_ports:
        return cases

    # Build per-port bit widths
    port_widths = {}
    for p in input_ports:
        port_widths[p["name"]] = _bitwidth_from_type(p.get("type", "wire [31:0]"), p["name"])

    # Each pattern below is DISTINCT. (The pre-dedup list had three duplicate
    # pairs — all_ones≡max_value, min_nonzero≡single_bit_hot_lsb,
    # single_bit_hot_msb≡half_range_msb_only — inflating the case count
    # without adding stimulus.)

    cases.append({
        "name": "all_zeros",
        "description": "All input ports driven with zero",
        "inputs": {p["name"]: 0 for p in input_ports},
    })

    cases.append({
        "name": "all_ones_max",
        "description": "All input ports at max unsigned value (2^N - 1)",
        "inputs": {name: (1 << width) - 1 for name, width in port_widths.items()},
    })

    cases.append({
        "name": "one_lsb_min_nonzero",
        "description": "LSB-only / minimum non-zero value (1) on all input ports",
        "inputs": {name: 1 for name in port_widths},
    })

    alt_ones = {}
    for name, width in port_widths.items():
        val = 0
        for i in range(width):
            if i % 2 == 1:
                val |= (1 << i)
        alt_ones[name] = val
    cases.append({
        "name": "alternating_1010",
        "description": "Alternating 1-0 pattern (0xAA...AA)",
        "inputs": alt_ones,
    })

    cases.append({
        "name": "one_msb_half_range",
        "description": "MSB-only value (2^(N-1)) — sign bit / half-range",
        "inputs": {name: 1 << (width - 1) for name, width in port_widths.items()},
    })

    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate corner-case test vectors from spec.json"
    )
    parser.add_argument("--spec", required=True, help="Path to spec.json")
    parser.add_argument("--output", "-o", required=True,
                        help="Output JSON file for corner cases")
    args = parser.parse_args(argv)

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"spec.json not found: {spec_path}", file=sys.stderr)
        return 2

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in {spec_path}: {e}", file=sys.stderr)
        return 2

    cases = generate_corner_cases(spec)

    output = {
        "source_spec": str(spec_path),
        "case_count": len(cases),
        "cases": cases,
    }

    out_path = Path(args.output)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"[corner_case] Generated {len(cases)} corner cases -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
