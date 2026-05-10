# Verilog-2005 Coding Style (Condensed for AI Translation Path)

**Context**: Modules with `has_dsl_builder=true` use the VerilogEmitter, which guarantees
rules 10 (output wire), 11 (two-block separation), 12 (latch elimination), and =/<= separation
structurally. This document covers rules for **Path B** (AI-translated modules from timing_model).

Full rule document (460 lines): `coding_style_archive.md`.

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
- **Synchronous active-high** reset named `rst`. Place `if (rst)` at the **end** of sequential block.

```verilog
always @(posedge clk) begin
    state_reg <= state_next;
    if (rst) begin
        state_reg <= STATE_IDLE;
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

## 8. FSM Structure

1. `localparam` with explicit width for state encoding.
2. Combinational block: next-state decode + output, defaults at top.
3. Sequential block: state register + reset.

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
| `#delay` in synthesizable code | Remove |
| Asynchronous/active-low reset | Synchronous `rst` |
| Latches | Flip-flops with defaults |

## 16. Cross-Module Timing (from timing_model mapping)

When translating `@vf_block` functions:
- `RegT` input → `input wire` (caller provides registered output)
- `WireT` input → `input wire` (combinational)
- Local variable → `wire` + `assign`
- `reg_next(r, val)` → `r <= val` in sequential block
- Co-asserted enables: independent `if` blocks, NOT `if/else if`
- Finalize states: read `_reg` only, never `_next` combinational wires
