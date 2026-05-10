# Anchor: barrel_shifter_var_n

32-bit variable left rotation using a 5-stage barrel shifter.

## When to use this anchor

- Module contains a variable rotation (rotation amount is a signal, not a constant).
- e.g. cryptographic algorithms (ChaCha20 quarter-round), CRC calculators.

## Python -> Verilog mapping

| Python (timing_model.py) | Verilog (module.v) | Note |
|---|---|---|
| `data: RegT(32)` | `input wire [31:0] data` | Data to rotate |
| `shift_amount: RegT(5)` | `input wire [4:0] shift_amount` | Rotation amount |
| `mux(cond, rotate_left(x, N), x)` | `if (shift_amount[k]) s_k = {x[W-1-N:0], x[W-1:W-N]}; else s_k = x;` | Stage k rotates by 2^k |
| `return s4` | `assign rotated = s4;` | Final output |

## Key pattern

**Variable rotation MUST use barrel shifter.** Verilog-2005 does not support variable part-select like `data[shift_amount+:32]`. The correct implementation uses log2(W) stages, each conditionally rotating by 2^k bits.

For 32-bit data:
- Stage 0: rotate by 1  (2^0)
- Stage 1: rotate by 2  (2^1)
- Stage 2: rotate by 4  (2^2)
- Stage 3: rotate by 8  (2^3)
- Stage 4: rotate by 16 (2^4)

Total rotation = sum of selected stages = any value 0..31.

## Files

- `timing_model.py` — veriflow_spec combinational model (reference for vf-coder)
- `module.v` — hand-written Verilog-2005 barrel shifter
