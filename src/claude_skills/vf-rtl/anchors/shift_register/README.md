# Anchor: shift_register

8-bit serial-in parallel-out shift register with enable gating.

## When to use this anchor

- Module contains a shift register, FIFO pointer, or any "shift left / right per cycle" logic.
- Has a `shift_en` or `enable` signal that gates the shift.

## Python -> Verilog mapping

| Python (timing_model.py) | Verilog (module.v) | Note |
|---|---|---|
| `shift_reg: RegT(8)` | `reg [7:0] shift_reg_reg` | Registered output |
| `shift_en: RegT(1)` | `input wire shift_en` | Enable input |
| `data_in: RegT(1)` | `input wire data_in` | Serial data input |
| `cat(data_in, slice_(shift_reg, 6, 0))` | `{data_in, shift_reg_reg[6:0]}` | Concatenation for shift-in |
| `mux(shift_en, shifted, shift_reg)` | `if (shift_en) ... else ...` | Enable gating |
| `reg_next(shift_reg, next_val)` | `always @(posedge clk) shift_reg_reg <= ...` | NBA update |

## Key pattern

**Concatenation for shift:** The new LSB comes from `data_in`, the upper 7 bits come from the old register shifted right by 1 (i.e. `[6:0]`). In Verilog this is `{data_in, shift_reg_reg[6:0]}`.

**Enable gating:** Use `mux(en, new_value, old_value)` in Python, which maps to an `if/else` in the sequential block.

## Files

- `timing_model.py` — veriflow_spec protocol model
- `module.v` — hand-written Verilog-2005
