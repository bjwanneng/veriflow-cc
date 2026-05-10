#!/usr/bin/env python3
"""Anchor: 3-stage pipeline register with valid following data flow.

Demonstrates:
  - Multi-register group updated simultaneously
  - Valid signal propagating with data
  - Bubble handling (invalid data passes 0)

Python model -> Verilog mapping:
  data_0/1/2_reg : RegT(32) -> reg [31:0] data_0/1/2_reg
  valid_0/1/2_reg: RegT(1)  -> reg        valid_0/1/2_reg
  data_in[31:0]  : RegT(32) -> input wire [31:0] data_in
  valid_in       : RegT(1)  -> input wire valid_in
  data_out[31:0] : RegT(32) -> output wire [31:0] data_out
  valid_out      : RegT(1)  -> output wire valid_out
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "veriflow_dsl"))

from veriflow_dsl import (
    RegT, WireT, RegAssign,
    reg_next, mux,
    vf_block, from_timing_model, VerilogEmitter,
)


@vf_block(type="sequential")
def pipeline_register(
    *,
    data_0_reg: RegT = RegT("data_0_reg", 32),
    data_1_reg: RegT = RegT("data_1_reg", 32),
    data_2_reg: RegT = RegT("data_2_reg", 32),
    valid_0_reg: RegT = RegT("valid_0_reg", 1),
    valid_1_reg: RegT = RegT("valid_1_reg", 1),
    valid_2_reg: RegT = RegT("valid_2_reg", 1),
    data_in: RegT = RegT("data_in", 32),
    valid_in: RegT = RegT("valid_in", 1),
) -> list[RegAssign]:
    """3-stage pipeline.

    Each stage advances when its input is valid.
    Bubble (= invalid) data is replaced with 0.
    """
    # Stage 0 captures input
    next_data_0  = mux(valid_in, data_in, 0)
    next_valid_0 = valid_in

    # Stage 1 captures stage 0
    next_data_1  = mux(valid_0_reg, data_0_reg, 0)
    next_valid_1 = valid_0_reg

    # Stage 2 captures stage 1
    next_data_2  = mux(valid_1_reg, data_1_reg, 0)
    next_valid_2 = valid_1_reg

    return [
        reg_next(data_0_reg, next_data_0),
        reg_next(valid_0_reg, next_valid_0),
        reg_next(data_1_reg, next_data_1),
        reg_next(valid_1_reg, next_valid_1),
        reg_next(data_2_reg, next_data_2),
        reg_next(valid_2_reg, next_valid_2),
    ]


def main():
    print("=" * 60)
    print("Anchor: pipeline_register")
    print("=" * 60)

    m = from_timing_model(pipeline_register)
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

    import subprocess
    try:
        result = subprocess.run(
            ["iverilog", "-g2005", "-Wall", "-o", os.path.join(out_dir, "pipeline_register.vvp"), v_path],
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
    print("ANCHOR OK: pipeline_register")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
