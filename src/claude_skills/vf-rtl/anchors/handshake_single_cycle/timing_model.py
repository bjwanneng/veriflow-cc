#!/usr/bin/env python3
"""Anchor: single-cycle handshake.

Demonstrates:
  - One-shot pulse generation (valid = 1 for exactly 1 cycle)
  - Companion last signal
  - State held in a single-bit flag (sent_reg)

Python model ->  Verilog mapping:
  trigger   : RegT(1)  ->  input wire trigger
  sent_reg  : RegT(1)  ->  reg sent_reg (internal state)
  valid_reg : RegT(1)  ->  output wire valid  (registered in model)
  last_reg  : RegT(1)  ->  output wire last   (registered in model)

Note: In the Verilog reference, valid/last are combinational outputs
for the same-cycle semantics. The timing_model uses registers to stay
within the sequential protocol; vf-coder should translate to wire
outputs when the spec requires combinational visibility.
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
def handshake_single_cycle(
    *,
    sent_reg: RegT = RegT("sent_reg", 1),
    valid_reg: RegT = RegT("valid_reg", 1),
    last_reg: RegT = RegT("last_reg", 1),
    trigger: RegT = RegT("trigger", 1),
) -> list[RegAssign]:
    """Single-cycle pulse generator.

    When trigger is high and we have not yet sent:
        valid = 1, last = 1, sent = 1
    Otherwise:
        valid = 0, last = 0, sent = 0

    sent_reg ensures the pulse is exactly 1 cycle wide.
    """
    fire = trigger & ~sent_reg

    return [
        reg_next(sent_reg, fire),
        reg_next(valid_reg, fire),
        reg_next(last_reg, fire),
    ]


def main():
    print("=" * 60)
    print("Anchor: handshake_single_cycle")
    print("=" * 60)

    m = from_timing_model(handshake_single_cycle)
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
            ["iverilog", "-g2005", "-Wall", "-o", os.path.join(out_dir, "handshake_single_cycle.vvp"), v_path],
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
    print("ANCHOR OK: handshake_single_cycle")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
