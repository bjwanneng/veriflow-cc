# Design Rules (Apply to ALL stages)

- All modules use **synchronous active-high reset** named `rst`. Reset is checked inside `always @(posedge clk)` only — no async sensitivity list. See `coding_style.md` Section 6 for full rules.
- Port naming: `_n` suffix for active-low, `_i`/`_o` for direction
- Parameterized design: use `parameter` for widths and depths
- Clock domains must be explicitly declared
- **Verilog-2005 only** — NO SystemVerilog (`logic`, `always_ff`, `assert property`, `|->`, `##`)

## Interface Lock

The following fields in spec.json are locked after Stage 1 completes. Stages 2-4 must NOT modify them:
- Port names, widths, and directions
- Reset polarity (`reset_polarity` field: `"active_high"` → port named `rst`, `"active_low"` → port named `rst_n`)
- Handshake protocol (`handshake` field: `"hold_until_ack"` / `"single_cycle"` / `"pulse"`)
- Module hierarchy and connectivity

If a later stage discovers a problem with the interface definition, it must roll back to Stage 1 to redefine.

## Port Semantic Fields (Interface Lock)

- Ports with `protocol: "reset"` MUST declare `reset_polarity`: `"active_high"` or `"active_low"`
- Ports with `protocol: "valid"` MUST declare `handshake`: `"hold_until_ack"` | `"single_cycle"` | `"pulse"`
- If `handshake: "hold_until_ack"`, MUST also declare `ack_port` with the name of the corresponding ack input port
- All ports MUST declare `signal_lifetime`: `"pulse"` or `"hold_until_used"`:
  - `"pulse"` — signal is asserted for 1 cycle and consumed immediately by the receiver
  - `"hold_until_used"` — signal is sampled at most once, arrives as a short pulse but is consumed many cycles later. The receiver MUST latch this signal.
- These fields are locked after Stage 1 and MUST NOT be changed by subsequent stages

## Finalize-State Invariant `[CRITICAL]`

In iterative computation FSMs (IDLE → CALC → DONE), the DONE/finalize state
MUST compute outputs from **registered values only** (`_reg`). Never use
combinational next-state wires (`_new`) in finalize states.

**Applies to**: All FSM designs with a DONE/finalize state that produces outputs
or updates state based on the completed computation.

**Rationale**: Combinational `_new` wires represent the result of applying one more
round of computation. When the FSM reaches DONE after N rounds, reading `_new`
effectively applies round N+1, corrupting the output.

```verilog
// WRONG — DONE state uses combinational next-state wires
STATE_DONE: begin
    V0 <= V0 ^ a_new;  // a_new = extra computation round!
end

// CORRECT — DONE state uses registered values only
STATE_DONE: begin
    V0 <= V0 ^ A_reg;  // A_reg = result of completed N rounds
end
```

## Merkle-Damgård Init Completeness `[CRITICAL]`

For iterated hash constructions with dual register sets (working A-H + chaining
V0-V7), the `is_first_block` initialization path MUST re-initialize BOTH sets to
IV. Chaining registers that retain stale values from previous messages will corrupt
subsequent message hashes.
