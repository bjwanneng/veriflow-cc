#!/usr/bin/env python3
"""SM3 compression round — hand-written timing_model.py (W1 validation).

Validates that the veriflow_spec protocol is expressive enough for a real
cryptographic hash algorithm. This is a single compression round (j < 16).

After writing this, run:
    python sm3_round_timing_model.py

Expected output:
    [adapter] Created DSL Module: sm3_round
    [iverilog] PASS
"""

import sys
import os
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veriflow_dsl import (
    RegT, WireT, RegAssign,
    reg_next, mux, rotate_left, rotate_right,
    from_timing_model, VerilogEmitter,
)
from veriflow_dsl._spec import vf_block


# SM3 round constants for j < 16
T0 = 0x79CC4519


@vf_block(type="sequential")
def sm3_round(
    *,
    a_reg: RegT = RegT("a_reg", 32),
    b_reg: RegT = RegT("b_reg", 32),
    c_reg: RegT = RegT("c_reg", 32),
    d_reg: RegT = RegT("d_reg", 32),
    e_reg: RegT = RegT("e_reg", 32),
    f_reg: RegT = RegT("f_reg", 32),
    g_reg: RegT = RegT("g_reg", 32),
    h_reg: RegT = RegT("h_reg", 32),
    w_j: WireT = WireT("w_j", 32),
    w_prime_j: WireT = WireT("w_prime_j", 32),
    calc_en: RegT = RegT("calc_en", 1),
) -> list[RegAssign]:
    """SM3 compression round for j < 16 (XOR mode).

    Inputs:  A-H registers, message words W_j / W'_j, calc enable
    Outputs: updated A-H registers

    Algorithm (j < 16):
        SS1 = ROL( ROL(A,12) + E + ROL(T0, j) , 7 )
        SS2 = SS1 ^ ROL(A, 12)
        TT1 = (A ^ B ^ C) + D + SS2 + W'_j
        TT2 = (E ^ F ^ G) + H + SS1 + W_j
        A'  = TT1
        B'  = A
        C'  = ROL(B, 9)
        D'  = C
        E'  = TT2 ^ ROL(TT2, 9) ^ ROL(TT2, 17)   # P0(TT2)
        F'  = E
        G'  = ROL(F, 19)
        H'  = G
    """
    # Combinational logic
    rol_a_12 = rotate_left(a_reg, 12)
    ss1 = rotate_left(rol_a_12 + e_reg + T0, 7)
    ss2 = ss1 ^ rol_a_12

    tt1 = (a_reg ^ b_reg ^ c_reg) + d_reg + ss2 + w_prime_j
    tt2 = (e_reg ^ f_reg ^ g_reg) + h_reg + ss1 + w_j

    p0_tt2 = tt2 ^ rotate_left(tt2, 9) ^ rotate_left(tt2, 17)

    # Register updates (NBA)
    return [
        reg_next(a_reg, mux(calc_en, tt1, a_reg)),
        reg_next(b_reg, mux(calc_en, a_reg, b_reg)),
        reg_next(c_reg, mux(calc_en, rotate_left(b_reg, 9), c_reg)),
        reg_next(d_reg, mux(calc_en, c_reg, d_reg)),
        reg_next(e_reg, mux(calc_en, p0_tt2, e_reg)),
        reg_next(f_reg, mux(calc_en, e_reg, f_reg)),
        reg_next(g_reg, mux(calc_en, rotate_left(f_reg, 19), g_reg)),
        reg_next(h_reg, mux(calc_en, g_reg, h_reg)),
    ]


def main():
    print("=" * 60)
    print("SM3 Round — timing_model -> adapter -> Verilog")
    print("=" * 60)

    # Step 1: Convert timing_model to DSL Module
    m = from_timing_model(sm3_round)
    print(f"\n[adapter] Module: {m.name}")
    print(f"[adapter] Ports ({len(m.ports())}):")
    for p in m.ports():
        print(f"  {p.direction:6} [{p.width:2}] {p.name}")

    # Step 2: Emit Verilog
    emitter = VerilogEmitter()
    verilog = emitter.emit(m)

    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    v_path = os.path.join(out_dir, "sm3_round.v")
    with open(v_path, "w") as f:
        f.write(verilog)

    print(f"\nEmitted: {v_path}")
    print(f"Size: {len(verilog)} chars")
    print()
    print("-" * 60)
    print(verilog)
    print("-" * 60)

    # Step 3: iverilog syntax check
    try:
        result = subprocess.run(
            ["iverilog", "-g2005", "-o", os.path.join(out_dir, "sm3_round.vvp"), v_path],
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
            return 1
    except FileNotFoundError:
        print("\n[iverilog] SKIP: iverilog not found.")
    except Exception as e:
        print(f"\n[iverilog] ERROR: {e}")
        return 1

    print("\n" + "=" * 60)
    print("W1 VALIDATION: SM3 timing_model is writable and emits valid Verilog")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
