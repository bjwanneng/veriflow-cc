#!/usr/bin/env python3
"""Anchor: hold-until-ack handshake.

Demonstrates:
  - Valid stays high from req arrival until ack is seen
  - Single-bit pending flag (not a full FSM)
  - Combinational set/clear logic on the same register

Python model ->  Verilog mapping:
  req       : RegT(1)  ->  input wire req
  ack       : RegT(1)  ->  input wire ack
  pending   : RegT(1)  ->  reg pending (internal state)
  valid_reg : RegT(1)  ->  output wire valid (registered in model)

Note: In the Verilog reference, valid is combinational (= pending)
for same-cycle visibility. The timing_model uses a register to stay
within the sequential protocol.
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
def handshake_hold_until_ack(
    *,
    pending: RegT = RegT("pending", 1),
    valid_reg: RegT = RegT("valid_reg", 1),
    req: RegT = RegT("req", 1),
    ack: RegT = RegT("ack", 1),
) -> list[RegAssign]:
    """Hold-until-ack handshake.

    - When req rises and not pending: set pending.
    - When ack rises and pending    : clear pending.
    - valid is simply pending (active while waiting for ack).
    """
    # Set on new request, clear on ack
    set_pending = req & ~pending
    clr_pending = ack & pending
    next_pending = set_pending | (pending & ~clr_pending)

    return [
        reg_next(pending, next_pending),
        reg_next(valid_reg, pending),
    ]


def main():
    print("=" * 60)
    print("Anchor: handshake_hold_until_ack")
    print("=" * 60)

    m = from_timing_model(handshake_hold_until_ack)
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
            ["iverilog", "-g2005", "-Wall", "-o", os.path.join(out_dir, "handshake_hold_until_ack.vvp"), v_path],
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
    print("ANCHOR OK: handshake_hold_until_ack")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
