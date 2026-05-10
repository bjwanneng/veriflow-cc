# Anchor: fsm_4state

4-state FSM with localparam encoding and two-segment style.

## When to use this anchor

- Module has discrete states and state transitions (control logic).
- Needs localparam state encoding and next-state combinational logic.
- Examples: DMA controller, command parser, bus arbiter.

## Python -> Verilog mapping

| Python (timing_model.py) | Verilog (module.v) | Note |
|---|---|---|
| `state_reg: RegT(2)` | `reg [1:0] state_reg_reg` | State register |
| `start: RegT(1)` | `input wire start` | External trigger |
| `done_signal: RegT(1)` | `input wire done_signal` | Completion signal |
| Nested `mux(...)` | `case (state_reg_reg) ... endcase` | Next-state logic |
| `state_reg == LOAD` | `(state_reg_reg == LOAD)` | State comparison |
| `reg_next(state_reg, next_state)` | `state_reg_reg <= next_state` | State update |
| `reg_next(load_en, state==LOAD)` | `assign load_en = (state_reg_reg == LOAD)` | Output decode |

## Key pattern

**Two-segment FSM:**
1. `always @(*)` — combinational next-state logic (case statement)
2. `always @(posedge clk)` — sequential state update (NBA)

This is the canonical Verilog style for FSMs. It separates "what state should we go to" from "update the state register."

**Moore outputs:** Outputs like `load_en`, `process_en`, `done_out` depend ONLY on the current state, not on inputs. This makes the output decode simple combinational logic.

**Nested mux as case:** In Python, nested `mux()` expressions encode the same logic as a Verilog `case` statement. vf-coder should recognize this pattern and emit `case`/`endcase`.

## Files

- `timing_model.py` — veriflow_spec sequential model
- `module.v` — hand-written Verilog-2005 (two-segment FSM)
