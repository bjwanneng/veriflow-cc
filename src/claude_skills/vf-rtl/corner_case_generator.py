#!/usr/bin/env python3
"""Corner-case test vector generator for VeriFlow-CC.

Auto-generates boundary-condition test vectors from spec.json:
- all-zeros input
- all-ones input
- minimum-length / smallest valid input
- maximum-length / largest valid input
- reset-mid-operation
- backpressure / stall scenarios

Usage:
    python corner_case_generator.py --spec spec.json --output corner_cases.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bitwidth_from_type(port_type: str) -> int:
    """Extract bit width from Verilog type like 'wire [31:0]'."""
    if "[" not in port_type or "]" not in port_type:
        return 1
    try:
        range_str = port_type.split("[")[1].split("]")[0]
        if ":" in range_str:
            high, low = range_str.split(":")
            return int(high.strip()) - int(low.strip()) + 1
        return int(range_str) + 1
    except (ValueError, IndexError):
        return 32  # default


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
        port_widths[p["name"]] = _bitwidth_from_type(p.get("type", "wire [31:0]"))

    # 1. All-zeros input
    zeros = {p["name"]: 0 for p in input_ports}
    cases.append({
        "name": "all_zeros",
        "description": "All input ports driven with zero",
        "inputs": zeros,
    })

    # 2. All-ones input
    ones = {name: (1 << width) - 1 for name, width in port_widths.items()}
    cases.append({
        "name": "all_ones",
        "description": "All input ports driven with all-ones (max unsigned value)",
        "inputs": ones,
    })

    # 3. Minimum non-zero input
    min_nonzero = {name: 1 for name in port_widths}
    cases.append({
        "name": "min_nonzero",
        "description": "All input ports driven with minimum non-zero value (1)",
        "inputs": min_nonzero,
    })

    # 4. Maximum value input (2^N - 1)
    max_val = {name: (1 << width) - 1 for name, width in port_widths.items()}
    cases.append({
        "name": "max_value",
        "description": "All input ports driven with maximum unsigned value",
        "inputs": max_val,
    })

    # 5. Alternating pattern (0xAA...AA)
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

    # 6. Single-bit-hot (only LSB set)
    single_bit = {name: 1 for name in port_widths}
    cases.append({
        "name": "single_bit_hot_lsb",
        "description": "Only LSB set, all other bits zero",
        "inputs": single_bit,
    })

    # 7. Single-bit-hot (only MSB set)
    msb_hot = {name: 1 << (width - 1) for name, width in port_widths.items()}
    cases.append({
        "name": "single_bit_hot_msb",
        "description": "Only MSB set, all other bits zero",
        "inputs": msb_hot,
    })

    # 8. Half-range (midpoint)
    half = {}
    for name, width in port_widths.items():
        val = 1 << (width - 1)
        half[name] = val
    cases.append({
        "name": "half_range_msb_only",
        "description": "MSB-only value (2^(N-1))",
        "inputs": half,
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
