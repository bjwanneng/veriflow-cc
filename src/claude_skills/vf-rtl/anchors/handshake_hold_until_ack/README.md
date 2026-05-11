# Anchor: handshake_hold_until_ack

Hold-until-acknowledge handshake: valid stays high from req until ack.

## When to use this anchor

- Module needs to assert `valid` and keep it asserted until the receiver responds with `ack`.
- Not gated by a simple enable — the handshake itself controls the duration.
- Examples: AXI-lite write valid, mailbox full indicator.

## Python -> Verilog mapping

| Python (timing_model.py) | Verilog (module.v) | Note |
|---|---|---|
| `req: RegT(1)` | `input wire req` | Request from sender |
| `ack: RegT(1)` | `input wire ack` | Acknowledge from receiver |
| `pending: RegT(1)` | `reg pending` | Internal: waiting for ack |
| `valid_reg: RegT(1)` | `output wire valid` | In Verilog, `assign valid = pending` |
| `set_pending = req & ~pending` | `req && !pending` | New request arrives |
| `clr_pending = ack & pending` | `ack && pending` | Ack while pending |
| `reg_next(pending, next_pending)` | `pending <= ...` | NBA state update |

## Key pattern

**Set/clear on separate conditions:** The pending flag has independent set and clear conditions. It is NOT a simple mux(enable, 1, 0) — both req and ack can be high in the same cycle, and the priority matters. In this design, set wins over clear (req && !pending has higher priority than ack && pending).

**Valid as combinational wire:** `valid` is simply `pending`, giving same-cycle visibility. When the spec says `same_cycle_visible`, emit combinational `assign`. When `registered_outputs`, use `output wire` + internal `reg` + `assign`.

## Files

- `module.v` — hand-written Verilog-2005 reference
- `trace.md` — cycle-accurate expected values
