# Anchor: hash_round_one_cycle

SM3 compression round (j < 16, XOR mode) — algorithmic single-cycle iteration.

## When to use this anchor

- Module performs a single round of a cryptographic hash or similar iterative algorithm.
- Multiple registers are updated simultaneously based on complex combinational logic.
- Contains rotations, additions, and XORs chained together.
- Examples: SM3, SHA-256, ChaCha20 quarter-round.

## Python -> Verilog mapping

| Python (timing_model.py) | Verilog (module.v) | Note |
|---|---|---|
| `a_reg..h_reg: RegT(32)` | `reg [31:0] a_reg_reg..h_reg_reg` | 8 state registers |
| `rotate_left(x, n)` | `{x[W-1-n:0], x[W-1:W-n]}` | Bit-slice concatenation |
| `tt1 = (a^b^c) + d + ss2 + w_prime_j` | `assign tt1 = ...` | Combinational intermediate |
| `reg_next(a_reg, mux(calc_en, tt1, a_reg))` | `a_reg_reg <= calc_en ? tt1 : a_reg_reg` | Enable-gated update |

## Key pattern

**Register group simultaneous update:** All 8 registers (A-H) are updated in the same `always @(posedge clk)` block. Each new value is computed from the OLD values (NBA semantics), so the order of assignments does not matter.

**Complex expression decomposition:** The SM3 round has nested expressions like `ROL(ROL(A,12) + E + T0, 7)`. In Verilog, this requires intermediate wires because:
1. The sum `ROL(A,12) + E + T0` overflows 32 bits (34-bit result)
2. Verilog-2005 does not allow part-select on expression results

The hand-written Verilog explicitly declares `ss1_sum` (34-bit) and `ss1` (34-bit rotated), then truncates to 32 bits where needed.

**Enable gating:** The entire round is gated by `calc_en`. When low, all registers hold their values. This is expressed as `mux(calc_en, new_value, old_value)` in Python and `calc_en ? new_value : old_value` in Verilog.

## Files

- `timing_model.py` — veriflow_spec sequential model
- `module.v` — hand-written Verilog-2005 with explicit intermediates
