# Verilog-2005 Coding Style (Condensed)

## 1. File Structure

```verilog
// -----------------------------------------------------------------------------
// File   : <filename>.v
// Author : <author>
// Date   : YYYY-MM-DD
// -----------------------------------------------------------------------------
// Description: <one-line purpose>
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module xxx #( ... )( ... );
// ... body ...
endmodule

`resetall
```

Rules:
- One module per file; filename matches module name.
- `` `define `` macros inside module body are **PROHIBITED**.
- ASCII only, UNIX line endings (`\n`).

## 2. Formatting

| Rule | Value |
|------|-------|
| Indentation | 4 spaces |
| Max line length | 100 characters |
| Tabs | **PROHIBITED** |

- `begin` on the same line as the preceding keyword.
- `end` starts a new line; `end else begin` on one line.
- Single-line `if` permitted only if the entire statement fits on one line.
- Tabular alignment for port expressions in instantiations and consecutive `assign`.

## 3. Naming

| Construct | Style |
|-----------|-------|
| Modules | `lower_snake_case` |
| Instances | `lower_snake_case` with `_inst` suffix |
| Signals | `lower_snake_case` — whole words, no abbreviations |
| parameter | `ALL_CAPS` |
| localparam | `ALL_CAPS` |

Signal names must **NOT** end with `_<number>` (e.g. `foo_1`).

## 4. Signal Suffixes

| Suffix | Meaning |
|--------|---------|
| `_reg` | Register (clocked current state) |
| `_next` | Combinational next-state signal |
| `_pipe_reg` | Pipeline stage register |
| `temp_` (prefix) | Temporary / skid-buffer register |

Declare `_reg` and its `_next` on the same line, comma-separated.

```verilog
reg [1:0] state_reg = STATE_IDLE, state_next;
reg       ready_reg = 1'b0, ready_next;
```

## 5. Clocks

Main clock is named exactly `clk`. Additional clocks: `clk_<domain>`.

## 6. Reset Strategy [CRITICAL]

**MUST** use **synchronous active-high** reset named `rst`.
**MUST NOT** use asynchronous or active-low reset.

Place the `if (rst)` block at the **end** of the sequential `always` block, leveraging last-assignment-wins:

```verilog
always @(posedge clk) begin
    state_reg   <= state_next;
    ready_reg   <= ready_next;

    if (rst) begin
        state_reg   <= STATE_IDLE;
        ready_reg   <= 1'b0;
    end
end
```

Reset only control-path signals (state, valid, ready). Pure datapath may skip reset to reduce fanout.

## 7. Module Declaration

Use Verilog-2001 ANSI style. Parameter block and port block are **separate**, each with `(` on its own line.

```verilog
module my_mod #
(
    parameter DATA_WIDTH = 32
)
(
    input  wire                  clk,
    input  wire                  rst,
    input  wire [DATA_WIDTH-1:0] data_in,
    output wire [DATA_WIDTH-1:0] data_out
);
```

- Port order: clocks first → reset → all others.
- **MUST** explicitly declare `wire` type on all ports.
- **MUST** vertically align direction, type, width, and name.

## 8. Parameters

- `parameter` for user-tunable values; `localparam` for derived constants.
- **MUST NOT** use `` `define `` or `defparam`.
- **SHOULD** validate critical constraints in an `initial begin` block.

## 9. Signal Declarations [CRITICAL]

| Driven by | Declare as |
|-----------|------------|
| `always` block | `reg` |
| `assign` / combinational | `wire` |

**MUST NOT** drive a `reg` with `assign`. **MUST NOT** drive a `wire` with `always`.

**MUST** assign initial values to all `reg` variables at declaration:

```verilog
reg [DATA_WIDTH-1:0] data_reg = {DATA_WIDTH{1'b0}}, data_next;
```

For parameterized widths, use the replication operator `{WIDTH{1'b0}}`, not `0`.

## 10. Output Port Driving [CRITICAL]

All `output` ports are declared as `output wire` and driven via `assign` from internal `_reg` signals.
**MUST NOT** use `output reg` or assign outputs directly in `always` blocks.

```verilog
output wire                  data_out,
// ...
reg  [DATA_WIDTH-1:0] data_out_reg = {DATA_WIDTH{1'b0}};
assign data_out = data_out_reg;
```

## 11. Two-Block Logic Separation [CRITICAL]

**MUST** separate combinational and sequential logic into distinct `always` blocks.

```verilog
// Block 1: combinational — compute all _next signals
always @* begin
    state_next = state_reg;
    // ... conditional logic ...
end

// Block 2: sequential — register sampling
always @(posedge clk) begin
    state_reg <= state_next;

    if (rst) begin
        state_reg <= STATE_IDLE;
    end
end
```

- Combinational blocks (`always @*`): **blocking (`=`) only**.
- Sequential blocks (`always @(posedge clk)`): **non-blocking (`<=`) only**.
- **MUST NOT** mix `=` and `<=` for the same signal in the same `always` block.
- Sensitivity list: use `always @*` (without parentheses). **MUST NOT** use explicit sensitivity lists or `always @(*)`.

### Memory array write rule

Memory array writes MUST use combinational address pre-computation to avoid iverilog NBA address evaluation race:

```verilog
wire [ADDR_W-1:0] write_addr;
assign write_addr = addr_next;

always @(posedge clk) begin
    if (wr_en)
        ram[write_addr] <= wdata;
end
```

### Blocking assignment in sequential blocks [PROHIBITED]

Using `=` inside `always @(posedge clk)` causes simulation-synthesis mismatch. **PROHIBITED**.

## 12. Latch Elimination

**MUST** assign default values to all outputs at the **top** of every `always @*` block, before any conditional branches.

```verilog
always @* begin
    state_next   = state_reg;
    mem_wr_en    = 1'b0;

    case (state_reg)
        STATE_IDLE: begin
            // override only what changes
        end
        default: ;
    endcase
end
```

## 13. Case Statements

- Use `case` for exact matching; `casez` with `?` for wildcard matching.
- **MUST** always include a `default` branch.
- **MUST NOT** use `casex`, `full_case`, or `parallel_case` pragmas.

### Single driver rule

Any `_next` signal is assigned in exactly one `always @*` block.
Any `_reg` signal is assigned in exactly one `always @(posedge clk)` block.

## 14. Finite State Machines

Three required components:

1. `localparam` with explicit width for state encoding.
2. Combinational `always @*` block — next-state decode and outputs, with defaults at top.
3. Sequential `always @(posedge clk)` block — state register only (+ reset at end).

Glitch-prone outputs (memory write enables, load strobes) **MUST** be registered:

```verilog
always @(posedge clk) begin
    mem_wr_en_reg <= mem_wr_en;  // glitch-free
end
```

State encoding example:

```verilog
localparam [1:0]
    STATE_IDLE  = 2'd0,
    STATE_WORK  = 2'd1,
    STATE_DONE  = 2'd2;

reg [1:0] state_reg = STATE_IDLE, state_next;
```

## 15. Module Instantiation

- **MUST** use named port connections exclusively — no positional arguments.
- Each connection on its own line; all declared ports must appear.
- Unconnected outputs: `.output_port()`; unused inputs: `.unused_input_port(8'd0)`.
- **MUST NOT** use `defparam`; no recursive instantiation.

## 16. Generate Constructs

- Name every generated block (`lower_snake_case`).
- Declare `genvar` **outside** the `generate` block.
- All `generate for` loop `begin` blocks must have a named label.

```verilog
genvar ii;
generate
    for (ii = 0; ii < NUM; ii = ii + 1) begin : my_block
        // ...
    end
endgenerate
```

## 17. Memory Arrays

Declare: `reg [DATA_WIDTH-1:0] mem[(2**ADDR_WIDTH)-1:0]`.
**MUST NOT** initialize memory at declaration or clear it in the reset block.

### Array index bounds

- Terminal condition **MUST** be `< DEPTH` or `<= DEPTH - 1`, never `<= DEPTH`.
- Prefer index masking: `ram[cnt[ADDR_W-1:0]]`.

## 18. Number Literals [CRITICAL]

- **MUST** always be explicit about widths: `4'd4`, `8'h2a`, `1'b0`.
- **MUST** use `{WIDTH{1'b0}}` for parameterized-width zero.
- Hex digit count **MUST** equal `ceil(width/4)`.

### Bit-slice rotation (ROL/ROR)

ROL using concatenation is a common silent bug. Verify widths:

```verilog
// CORRECT — 25 + 7 = 32 bits
assign rol7 = {x[24:0], x[31:25]};

// WRONG — 25 + 25 = 50 bits, silently truncated
assign rol7_wrong = {x[24:0], x[31:7]};
```

### Unsized literals in width-critical expressions

Use **unsized** integer literals as shift amounts:

```verilog
// WRONG — 5'd32 overflows 5-bit field
rol32 = (x << 5'd32) | (x >> (5'd32 - n));

// CORRECT
rol32 = (x << n) | (x >> (32 - n));
```

## 19. Signed Arithmetic

Use `$signed()` for unsigned-to-signed conversion.

## 20. Handshake

- `hold_until_ack`: `valid` stays HIGH until `ready` acknowledges. Do **NOT** pulse.
- `single_cycle`: `valid` is HIGH for exactly one cycle, then auto-deasserts.

## 21. Prohibited Constructs [CRITICAL]

| Construct | Status |
|-----------|--------|
| SystemVerilog (`logic`, `always_ff`, `always_comb`, `interface`, `unique case`) | **PROHIBITED** |
| `casex` | **PROHIBITED** |
| `full_case` / `parallel_case` pragmas | **PROHIBITED** |
| `defparam` | **PROHIBITED** |
| Recursive module instantiation | **PROHIBITED** |
| `#delay` in synthesizable code | **PROHIBITED** |
| Implicit net declarations | **PROHIBITED** |
| Latches | **PROHIBITED** — use flip-flops |
| 3-state (`Z`) for on-chip muxing | **PROHIBITED** |
| `$display`, `$finish`, `$monitor` in synthesizable code | **PROHIBITED** |
| Placeholder code (`// TODO`, empty module bodies) | **PROHIBITED** |
| `output reg` | **PROHIBITED** — use `output wire` + `_reg` |
| Explicit sensitivity lists (`always @(a or b)`) | **PROHIBITED** — use `always @*` |
| Asynchronous / active-low reset (`rst_n`) | **PROHIBITED** — use synchronous `rst` |
| Blocking assignment (`=`) in sequential blocks | **PROHIBITED** — use `<=` |

## 22. Pipeline Timing [CRITICAL]

Before writing any multi-cycle module, build a **cycle-accurate timing table**:

```
Cycle | FSM State | load_en | calc_en | register_X | output_valid
------|-----------|---------|---------|------------|------------
  0   | IDLE      |    0    |    0    |     -      |      0
  1   | LOAD      |    1    |    0    |  input     |      0
  2   | CALC[0]   |    0    |    1    |  computed  |      0
 ...  | CALC[N-1] |    0    |    1    |  computed  |      0
 N+1  | DONE      |    0    |    0    |  result    |      1
```

Key rules:
1. Register values update at `posedge clk`. The new value is visible starting the **next** clock edge.
2. A control signal asserted on cycle N produces its first effect on cycle N+1.
3. Counter range: count from 0 to N-1, producing exactly N assertions.
4. FSM state transitions and control signal assertions must be in the same `always` block.

## 23. Cross-Module & Algorithm Rules [CRITICAL]

### 23.1 Combinational bypass

When a signal must be produced and consumed in the same clock cycle, expose the producer's next-state value as a wire:

```verilog
wire flag_next;
assign flag_next = (input_valid && ready) ? input_flag : flag_reg;

always @(posedge clk) begin
    flag_reg <= flag_next;
end

// Consumer reads flag_next (combinational), not flag_reg
u_submodule (.flag_i(flag_next));
```

**WARNING**: Do **NOT** use `@(negedge clk)` — creates half-cycle paths and simulation-synthesis mismatch.

### 23.2 Hold-until-used signals

Signals arriving as short pulses but consumed many cycles later must be latched:

```verilog
always @(posedge clk) begin
    if (rst)
        done_latched_reg <= 1'b0;
    else if (complete_flag)
        done_latched_reg <= 1'b0;
    else if (input_valid && fsm_ready)
        done_latched_reg <= done_flag;
end
```

### 23.3 Counter range consistency

All modules sharing a counter must agree on range: `0` to `N-1` (N values).

### 23.4 Shift register alignment

`fill_en` and `shift_en` **MUST NOT** be co-asserted. The FSM must provide separate LOAD and PROCESS cycles.

### 23.5 Shift register replenishment

When a shift register shifts every active cycle, the next-element injected at the tail **MUST NOT** be gated to zero by a step counter condition. Replenishment must be unconditional.

### 23.6 Output trace-back

For each output port, list all registers in the output expression. Verify each has a correct initial value for the first operational cycle — NOT just "reset to 0". If `output = A ^ B`, both A and B must be initialized.

### 23.7 Merkle-Damgård dual initialization

For iterated hash cores: both working registers (A-H) AND chaining registers (V0-V7) must be re-initialized to IV when starting a new message.

```verilog
// CORRECT
if (is_first_block) begin
    A_reg <= IV0;  ...  H_reg <= IV7;
    V0    <= IV0;  ...  V7    <= IV7;
end
```

### 23.8 Finalize-state register read

DONE/finalize states **MUST** use `_reg` values only. **NEVER** use `_new` combinational wires in finalize states.

```verilog
// CORRECT — DONE reads registered values
STATE_DONE: begin
    hash_out_reg <= {V0 ^ A_reg, V1 ^ B_reg, ...};
end

// WRONG — reads combinational next-state
STATE_DONE: begin
    hash_out_reg <= {V0 ^ a_new, ...};  // BUG: a_new = round N+1 result
end
```

### 23.9 Co-asserted enables

If two enable signals are co-asserted by the same FSM state, they **MUST** appear in independent `if` blocks, NOT in `if/else if`:

```verilog
// WRONG
if (load_en) begin ... end
else if (calc_en) begin ... end

// CORRECT
if (load_en) begin ... end
if (calc_en) begin ... end
```

If `load_en` and `calc_en` are co-asserted on the first CALC cycle, the datapath must use a bypass mux:

```verilog
working_data = load_en ? input_data : computed_result;
```
