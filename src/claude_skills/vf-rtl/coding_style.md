# Verilog-2005 Coding Style (Condensed for AI Translation Path)

**Context**: vf-coder translates golden_model.py algorithms + spec.json timing contracts into
Verilog-2005. This document covers rules for AI-translated modules.

## 1. File Structure

```verilog
`resetall
`timescale 1ns / 1ps
`default_nettype none

module xxx #( ... )( ... );
// ... body ...
endmodule

`resetall
```

- One module per file; filename matches module name.
- ASCII only, UNIX line endings.

## 2. Formatting

4-space indent, max 100 chars per line. No tabs.
`begin` on same line as keyword. `end` on new line; `end else begin` on one line.

## 3. Naming

| Construct | Style |
|-----------|-------|
| Modules/instances | `lower_snake_case` |
| Signals | `lower_snake_case` — whole words |
| parameter/localparam | `ALL_CAPS` |

Signal suffixes: `_reg` (clocked state), `_next` (combinational next-state).

## 4. Clock and Reset

- Main clock: `clk`. Additional: `clk_<domain>`.
- **Synchronous active-high** reset named `rst`. Place `if (rst)` at the **beginning** of sequential block (reset-first + else). This guarantees reset takes priority over `_next` assignments.

```verilog
always @(posedge clk) begin
    if (rst) begin
        state_reg <= STATE_IDLE;
    end else begin
        state_reg <= state_next;
    end
end
```

## 5. Module Declaration

Verilog-2001 ANSI style. Clocks first, then reset, then all others.
Declare `wire` type on all ports explicitly.

## 6. Signal Declarations

| Driven by | Declare as |
|-----------|------------|
| `always` block | `reg` |
| `assign` / combinational | `wire` |

Assign initial values to all `reg` at declaration: `reg [7:0] data_reg = {8{1'b0}};`.

## 7. Two-Block Separation

```verilog
always @* begin           // combinational — blocking (=)
    state_next = state_reg;
    // defaults at top, then conditional logic
end

always @(posedge clk) begin // sequential — non-blocking (<=)
    state_reg <= state_next;
    if (rst) state_reg <= STATE_IDLE;
end
```

- Default values at top of `always @*` prevents latches.
- **MUST NOT** mix `=` and `<=` in same block.
- **One reg, one always block**: every `reg` must be driven by exactly one
  `always` block. Multiple always blocks writing the same `reg` causes
  undefined simulation behavior and synthesis "multiple drivers" errors.
  All register logic (FSM state, counters, control flags, data pipeline)
  goes in the single `always @(posedge clk)` block.

## 8. FSM Structure

1. `localparam` with explicit width for state encoding.
2. Combinational block: next-state decode + output, defaults at top.
3. Sequential block: state register + reset.
4. Latch signals that must persist across states (e.g. `is_last`, `count_reg`)
   are updated inside the same `always @(posedge clk)` block using
   `if (state_reg == X && condition) signal_reg <= value` — never in a
   separate always block.

```verilog
localparam [1:0] STATE_IDLE = 2'd0, STATE_WORK = 2'd1, STATE_DONE = 2'd2;
reg [1:0] state_reg = STATE_IDLE, state_next;
```

## 9. Output Ports

`output wire` + internal `_reg` + `assign`. **MUST NOT** use `output reg`.

## 10. Case Statements

- `default` branch **required**.
- No `casex`, `full_case`, or `parallel_case`.

## 11. Module Instantiation

Named port connections only. Each on its own line.

## 12. Number Literals

Always explicit widths: `4'd4`, `8'h2a`, `1'b0`.
Use `{WIDTH{1'b0}}` for parameterized zero.

## 13. Handshake

- `hold_until_ack`: valid stays HIGH until ack.
- `single_cycle`: valid HIGH for exactly one cycle.
- **Back-pressure (`ready`) must be combinational output**: `assign ready = !fifo_full;`
  — never `reg ready` with NBA delay. The upstream source must see the current state
  in the same cycle. `valid` may be registered (spec-driven), but `ready` must not.

## 14. Memory Arrays

Declare: `reg [DATA_WIDTH-1:0] mem[(2**ADDR_WIDTH)-1:0]`.
Terminal condition: `< DEPTH`. Prefer index masking.

## 15. ABSOLUTE BANS

| FORBIDDEN | Use instead |
|-----------|------------|
| SystemVerilog (`logic`, `always_ff`, `always_comb`, `enum`, `struct`) | `wire`/`reg`, `always @*`/`always @(posedge)`, `localparam` |
| `casex` | `case` or `casez` with `?` |
| `defparam` | named port connections |
| `output reg` | `output wire` + `_reg` |
| Blocking `=` in `always @(posedge clk)` | Non-blocking `<=` |
| Two always blocks driving the same `reg` | All register logic in one `always @(posedge clk)` block |
| `#delay` in synthesizable code | Remove |
| Asynchronous/active-low reset | Synchronous `rst` |
| Latches | Flip-flops with defaults |

## 16. Datapath Pipeline Registers

When spec.json specifies `pipeline_stages > 1` or `pipeline_delay_cycles > 1`,
the combinational datapath MUST be broken into registered stages. A fully
combinational chain from input to a single output register violates the timing
contract if `pipeline_stages` indicates intermediate registers are expected.

**Rule**: Between any two `always @(posedge clk)` registers, the combinational
logic depth MUST NOT exceed 12 LUT levels. If it does, insert an intermediate
pipeline register.

**Common pattern — parallel multiplier + adder tree**:
  Stage 1: input registers (data sampling, line buffer, window)
  Stage 2: multiplier output registers (**CRITICAL** — do NOT skip)
  Stage 3: adder tree → output register

```verilog
// Stage 2: multiplier pipeline registers
reg signed [16:0] prod_reg [0:8];
reg             prod_valid_reg;
always @(posedge clk) begin
    if (rst) begin
        prod_valid_reg <= 1'b0;
        for (i = 0; i < 9; i = i + 1)
            prod_reg[i] <= 17'sd0;
    end else if (mac_en) begin
        prod_valid_reg <= 1'b1;
        prod_reg[0] <= prod_0;  // ... prod_reg[8] <= prod_8;
    end else begin
        prod_valid_reg <= 1'b0;
    end
end

// Stage 3: adder tree (combinational from prod_reg)
wire signed [19:0] mac_result = prod_reg[0] + ... + prod_reg[8];
```

**Key**: `valid` and `data` MUST travel through the same number of pipeline
stages, otherwise they drift apart (see Mini-pattern C in vf-coder.md).

## 17. Division and Modulo in Synthesizable Code

AVOID `/` and `%` operators in synthesizable code unless the divisor is a
compile-time constant. Synthesis tools infer full divider circuits for
variable divisors, which are expensive and slow.

| Divisor type | Safe pattern |
|---|---|
| Power of 2 constant | `value >> N` or `value[N-1:0]` |
| Small constant with known range | Expand to conditional: `if (stride == 2) bit_check else 1` |
| Variable (signal-dependent) | Redesign to avoid division; use lookup or counter |

```verilog
// BAD: variable modulo — infers full divider
if ((out_y % stride_val) == 0) ...

// GOOD: known stride range (1 or 2) — expand conditionally
if (stride_reg == 1'b0 || out_y[0] == 1'b0) ...

// BAD: variable division for bounds check
if ((out_y / stride_val) < out_h) ...

// GOOD: equivalent check without division
if (out_y < out_h * stride_val) ...  // multiply by small constant is cheap
```

## 18. Code Hygiene Before Writing

Before writing the final .v file, verify:

1. **No dead signals**: Every declared `_next` or `_reg` signal must be read
   by at least one other statement. `grep` each signal name in the file.
2. **No stale comments**: Comments must match the code. If code was refactored
   (e.g., a condition flipped, a signal renamed), update the comment or remove it.
3. **No placeholder values**: Remove `{N{1'b0}}` placeholders and half-written
   expressions. Every line must be production-ready.
4. **No redundant counters**: If two counters track the same thing (e.g.,
   `pipe_cnt_next` and `pipe_cycle_reg`), keep only one.

## 19. Rotating Line Buffer Depth

When partitioning a streaming window extractor into rotating line buffers, the
number of physical buffers must be large enough that a row is **never overwritten
while still being read** for window assembly.

**Principle**: For a K×K window with P rows of padding on the top edge, a given
image row R is read for the last time when the output reaches row `R + (K-1)/2`.
The next row that maps to the same physical buffer is row `R + NUM_BUFS`.
Conflict occurs when `(R + NUM_BUFS) * WIDTH  ≤  (R + (K-1)/2 + ... ) * WIDTH — ...` .

Rather than memorizing numbers, **derive the minimum buffer count from the read
lifespan vs. write schedule**:

1. Determine when row R is last read (depends on window size, padding, output stride)
2. Determine when row `R + NUM_BUFS` is first written (depends on input rate)
3. Require: `first_write_cycle(R + NUM_BUFS)  >  last_read_cycle(R)`

If the design uses a **streaming fill-then-flush** FSM (all rows buffered before
output begins), the same analysis applies to the flush phase.

**Common cases** (derived from the analysis above, for reference):
- K=3, valid-only output (no padding): 3 buffers suffice for any HEIGHT
- K=3, full-padding (output size = input size): 4 buffers required for HEIGHT ≥ 4

Use `buf_idx = row % NUM_BUFS`. When NUM_BUFS is a power of 2, `row[$clog2(NUM_BUFS)-1:0]` works.

## 20. Cross-Module Timing (from spec.json timing_contract)

When translating from golden_model.py + spec.json:
- Input port with `pipeline_delay_cycles > 0` → caller provides registered output → `input wire`
- Input port with `same_cycle_visible=true` → combinational → `input wire`
- Internal combinational signal → `wire` + `assign` or `always @*`
- Internal register (holds state across cycles) → `reg` + `always @(posedge clk) <=`
- Co-asserted enables: independent `if` blocks, NOT `if/else if`
- Finalize states: read `_reg` only, never `_next` combinational wires
