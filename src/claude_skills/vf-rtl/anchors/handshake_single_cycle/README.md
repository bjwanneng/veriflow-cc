# Anchor: handshake_single_cycle

Single-cycle pulse generator with companion last signal.

## When to use this anchor

- Module needs to emit a valid pulse for exactly 1 cycle when triggered.
- Has a companion `last` signal indicating end-of-transfer.
- Examples: DMA descriptor completion, packet boundary marker.

## Python -> Verilog mapping

| Python (timing_model.py) | Verilog (module.v) | Note |
|---|---|---|
| `trigger: RegT(1)` | `input wire trigger` | External trigger |
| `sent_reg: RegT(1)` | `reg sent_reg` | Internal: already sent this cycle |
| `valid_reg: RegT(1)` | `output wire valid` | In Verilog, combinational output |
| `last_reg: RegT(1)` | `output wire last` | In Verilog, combinational output |
| `fire = trigger & ~sent_reg` | `trigger && !sent_reg` | Pulse condition |
| `reg_next(sent_reg, fire)` | `sent_reg <= (trigger && !sent_reg)` | State update |

## Key pattern

**One-shot with flag:** Use a `sent_reg` flag to prevent re-triggering in the same cycle. The flag is set when the pulse fires and cleared on the next cycle (or when trigger goes low).

**Combinational vs registered outputs:** In the timing_model, `valid_reg` and `last_reg` are registers to fit the sequential protocol. In the Verilog reference, they are `wire` outputs (combinational) for same-cycle visibility. vf-coder should follow the spec: if the module spec says "wire output", emit combinational assign.

## Files

- `timing_model.py` — veriflow_spec sequential model
- `module.v` — hand-written Verilog-2005
