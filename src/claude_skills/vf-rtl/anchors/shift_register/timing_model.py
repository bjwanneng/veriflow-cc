#!/usr/bin/env python3
"""Anchor: 8-bit shift register with enable gating.

Demonstrates:
  - Single register updated via NBA (reg_next)
  - Enable-gated update (mux)
  - Concatenation for shift-in (cat / slice)

Python model  ->  Verilog mapping:
  shift_reg: RegT(8)     ->  reg [7:0] shift_reg
  shift_en : RegT(1)     ->  input wire shift_en
  data_in  : RegT(1)     ->  input wire data_in
  reg_next(shift_reg, ...)  ->  always @(posedge clk) shift_reg <= ...
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "veriflow_dsl"))

from veriflow_dsl import (
    RegT, WireT, RegAssign,
    reg_next, mux, cat, slice_,
    vf_block, from_timing_model, VerilogEmitter,
)


@vf_block(type="sequential")
def shift_register(
    *,
    shift_reg: RegT = RegT("shift_reg", 8),
    shift_en: RegT = RegT("shift_en", 1),
    data_in: RegT = RegT("data_in", 1),
) -> list[RegAssign]:
    """8-bit serial-in parallel-out shift register.

    When shift_en is high: shift left, LSB from data_in.
    When shift_en is low : hold current value.
    """
    # Combinational: construct next value
    shifted = cat(data_in, slice_(shift_reg, 6, 0))  # {data_in, shift_reg[6:0]}
    next_val = mux(shift_en, shifted, shift_reg)

    return [reg_next(shift_reg, next_val)]


def main():
    print("=" * 60)
    print("Anchor: shift_register")
    print("=" * 60)

    m = from_timing_model(shift_register)
    print(f"\n[adapter] Module: {m.name}")
    print(f"[adapter] Ports ({len(m.ports())}):")
    for p in m.ports():
        print(f"  {p.direction:6} [{p.width:2}] {p.name}")

    emitter = VerilogEmitter()
    verilog = emitter.emit(m)

    out_dir = os.path.dirname(__file__)
    v_path = os.path.join(out_dir, "module_from_tm.v")
    with open(v_path, "w") as f:
        f.write(verilog)

    print(f"\nEmitted: {v_path}")
    print(f"Size: {len(verilog)} chars")
    print()
    print("-" * 60)
    print(verilog)
    print("-" * 60)

    # Verify with iverilog
    import subprocess
    try:
        result = subprocess.run(
            ["iverilog", "-g2005", "-Wall", "-o", os.path.join(out_dir, "shift_register.vvp"), v_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print("\n[iverilog] PASS")
        else:
            print(f"\n[iverilog] FAIL:\n{result.stderr}")
            return 1
    except Exception as e:
        print(f"\n[iverilog] ERROR: {e}")
        return 1

    print("\n" + "=" * 60)
    print("ANCHOR OK: shift_register")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
