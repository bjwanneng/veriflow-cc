#!/usr/bin/env python3
"""Counter example via timing_model -> adapter -> DSL emitter (W1-D1 stretch)."""

import sys
import os
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veriflow_dsl import RegT, reg_next, mux, from_timing_model, VerilogEmitter
from veriflow_dsl._spec import vf_block, RegAssign


@vf_block(type="sequential")
def counter(
    *,
    count_reg: RegT = RegT("count_reg", 8),
    en: RegT = RegT("en", 1),
) -> list[RegAssign]:
    """8-bit counter with enable — timing_model style.

    Parameters are RegT with default values carrying width.
    Returns list[RegAssign] via reg_next().
    """
    return [reg_next(count_reg, mux(en, count_reg + 1, count_reg))]


def main():
    # Step 1: timing_model function -> DSL Module
    m = from_timing_model(counter)
    print(f"[adapter] Created DSL Module: {m.name}")
    print(f"[adapter] Ports: {[p.name for p in m.ports()]}")
    print(f"[adapter] Signals: {list(m.signals.keys())}")

    # Step 2: DSL Module -> Verilog
    emitter = VerilogEmitter()
    verilog = emitter.emit(m)

    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    v_path = os.path.join(out_dir, "counter_from_tm.v")
    with open(v_path, "w") as f:
        f.write(verilog)

    print(f"\nEmitted: {v_path}")
    print(f"Size: {len(verilog)} chars")
    print()
    print("=" * 60)
    print(verilog)
    print("=" * 60)

    # Step 3: iverilog syntax check
    try:
        result = subprocess.run(
            ["iverilog", "-g2005", "-o", os.path.join(out_dir, "counter_from_tm.vvp"), v_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print("\n[iverilog] PASS: Verilog syntax is valid.")
        else:
            print(f"\n[iverilog] FAIL: exit code {result.returncode}")
            print(result.stdout)
            print(result.stderr)
    except FileNotFoundError:
        print("\n[iverilog] SKIP: iverilog not found in PATH.")
    except Exception as e:
        print(f"\n[iverilog] ERROR: {e}")


if __name__ == "__main__":
    main()
