# VeriFlow Anchor Library

7 high-quality Python -> Verilog reference pairs for vf-coder translation.

## Anchor List

| Anchor | Feature | What it teaches |
|---|---|---|
| `fsm_4state/` | State machine | localparam encoding, two-segment (next-state comb + state seq), case statement |
| `shift_register/` | Shift register | Concatenation for shift-in, enable gating with mux |
| `pipeline_register/` | Pipeline | Multi-register group, valid-follows-data, bubble handling |
| `hash_round_one_cycle/` | Crypto round | Complex combinational intermediates, register group simultaneous update |
| `handshake_hold_until_ack/` | Hold handshake | Valid stays high until ack, set/clear on separate conditions |
| `handshake_single_cycle/` | Pulse handshake | One-shot valid for exactly 1 cycle, companion last signal |
| `barrel_shifter_var_n/` | Variable rotation | log2(W) cascaded mux stages, **no variable part-select** |
| `priority_encoder_8bit/` | Priority encoder | Combinational tuple return (multi-output), cat() for bit assembly |

## Selection Rules (for vf-architect)

vf-architect generates `anchor_hints` in spec.json based on module features:

| Module Feature | anchor_hint |
|---|---|
| `module_type=control` + `has_states=true` | `fsm_4state` |
| Contains shift register + `shift_en` | `shift_register` |
| Contains multi-stage data flow + `valid` | `pipeline_register` |
| Cryptographic / hash algorithm iteration | `hash_round_one_cycle` |
| Handshake with `valid` held until `ack` | `handshake_hold_until_ack` |
| Handshake with single-cycle `valid` + `last` | `handshake_single_cycle` |
| Variable rotation amount (signal, not constant) | `barrel_shifter_var_n` |
| Priority encoder with `encoded` + `valid` outputs | `priority_encoder_8bit` |

Each module gets **at most 2** anchors in its prompt (most relevant first).

## Directory Layout

Each anchor directory contains:
- `timing_model.py` — veriflow_spec protocol model (`@vf_block`, `RegT`/`WireT`, `reg_next`)
- `module.v` — hand-written Verilog-2005 reference
- `README.md` — Python -> Verilog mapping guide

## Quality Gates

Every anchor must pass:
1. `python timing_model.py` emits Verilog and passes `iverilog -g2005 -Wall`
2. `module.v` passes `iverilog -g2005 -Wall`
3. `module.v` passes `yosys -p "read_verilog module.v; synth -top <module>"`
