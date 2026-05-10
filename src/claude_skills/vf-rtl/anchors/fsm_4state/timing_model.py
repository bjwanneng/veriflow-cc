#!/usr/bin/env python3
"""Anchor: 4-state FSM (IDLE / LOAD / PROCESS / DONE).

Demonstrates:
  - State register updated via NBA
  - Next-state logic expressed as nested mux (case-like)
  - Output decode from current state
  - localparam-style state encoding

Python model -> Verilog mapping:
  state_reg: RegT(2)   -> reg [1:0] state_reg
  start: RegT(1)       -> input wire start
  done_signal: RegT(1) -> input wire done_signal
  load_en: RegT(1)     -> output wire load_en (registered in model)
  process_en: RegT(1)  -> output wire process_en (registered in model)
  done_out: RegT(1)    -> output wire done_out (registered in model)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "veriflow_dsl"))

from veriflow_dsl import (
    RegT, WireT, RegAssign,
    reg_next, mux,
    vf_block, from_timing_model, VerilogEmitter,
)

# State encoding (matches Verilog localparam)
IDLE    = 0
LOAD    = 1
PROCESS = 2
DONE    = 3


@vf_block(type="sequential")
def fsm_4state(
    *,
    state_reg: RegT = RegT("state_reg", 2),
    load_en: RegT = RegT("load_en", 1),
    process_en: RegT = RegT("process_en", 1),
    done_out: RegT = RegT("done_out", 1),
    start: RegT = RegT("start", 1),
    done_signal: RegT = RegT("done_signal", 1),
) -> list[RegAssign]:
    """4-state FSM: IDLE -> LOAD -> PROCESS -> DONE -> IDLE.

    Outputs are decoded from current state (Moore machine).
    """
    # Next-state logic (nested mux = case statement)
    next_state = mux(
        state_reg == IDLE,
        mux(start, LOAD, IDLE),
        mux(
            state_reg == LOAD,
            LOAD,  # stay in LOAD until externally told to move
            mux(
                state_reg == PROCESS,
                mux(done_signal, DONE, PROCESS),
                DONE,  # DONE state (stay until reset or explicit clear)
            ),
        ),
    )

    # Output decode (Moore: outputs depend only on state)
    next_load_en    = (state_reg == LOAD)
    next_process_en = (state_reg == PROCESS)
    next_done_out   = (state_reg == DONE)

    return [
        reg_next(state_reg, next_state),
        reg_next(load_en, next_load_en),
        reg_next(process_en, next_process_en),
        reg_next(done_out, next_done_out),
    ]


def main():
    print("=" * 60)
    print("Anchor: fsm_4state")
    print("=" * 60)

    m = from_timing_model(fsm_4state)
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
            ["iverilog", "-g2005", "-Wall", "-o", os.path.join(out_dir, "fsm_4state.vvp"), v_path],
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
    print("ANCHOR OK: fsm_4state")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
