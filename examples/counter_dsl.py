#!/usr/bin/env python3
"""Counter example: DSL -> Verilog emitter end-to-end (W1-D1).

Demonstrates that migrated veriflow_dsl can emit synthesizable Verilog-2005
and that iverilog accepts the output.
"""

import sys
import os
import subprocess

# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veriflow_dsl import Module, Signal, Const, Mux
from veriflow_dsl import VerilogEmitter


def build_counter() -> Module:
    """Build an 8-bit up-counter with synchronous reset and enable."""
    m = Module("counter")

    # Ports
    clk = Signal(1, name="clk")
    rst = Signal(1, name="rst")
    en = Signal(1, name="en")
    count = Signal(8, name="count", reset=0)

    m.add_input(clk)
    m.add_input(rst)
    m.add_input(en)
    m.add_output(count)
    m.add_signal(count)

    # Sequential logic: count <= en ? count + 1 : count
    m.d.sync += count.eq(Mux(en, count + Const(1, 8), count))

    return m


def emit_and_verify() -> str:
    """Emit Verilog and verify with iverilog syntax check."""
    m = build_counter()
    emitter = VerilogEmitter()
    verilog = emitter.emit(m)

    # Write output
    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    v_path = os.path.join(out_dir, "counter.v")
    with open(v_path, "w") as f:
        f.write(verilog)

    print(f"Emitted: {v_path}")
    print(f"Size: {len(verilog)} chars")
    print()
    print("=" * 60)
    print(verilog)
    print("=" * 60)

    # iverilog syntax check
    try:
        result = subprocess.run(
            ["iverilog", "-g2005", "-o", os.path.join(out_dir, "counter.vvp"), v_path],
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

    return verilog


if __name__ == "__main__":
    emit_and_verify()
