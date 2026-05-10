# Anchor: pipeline_register

3-stage pipeline register with valid following data flow and bubble handling.

## When to use this anchor

- Module has multi-stage data flow with valid/enable signals.
- Needs bubble handling (invalid data replaced with 0).
- Examples: DSP pipeline, packet processing, image filter chains.

## Python -> Verilog mapping

| Python (timing_model.py) | Verilog (module.v) | Note |
|---|---|---|
| `data_0/1/2_reg: RegT(32)` | `reg [31:0] data_0/1/2_reg` | Pipeline data registers |
| `valid_0/1/2_reg: RegT(1)` | `reg valid_0/1/2_reg` | Pipeline valid registers |
| `data_in: RegT(32)` | `input wire [31:0] data_in` | Input data |
| `valid_in: RegT(1)` | `input wire valid_in` | Input valid |
| `mux(valid_in, data_in, 0)` | `valid_in ? data_in : 32'd0` | Bubble = 0 |
| `reg_next(data_1_reg, ...)` | `data_1_reg <= ...` | Stage advance |

## Key pattern

**Valid-follows-data:** Each stage has a data register AND a valid register. The valid bit propagates alongside the data, so downstream stages know whether the data is real or a bubble.

**Bubble handling:** When input is invalid (`valid_in = 0`), the stage captures `0` instead of whatever is on the wire. This prevents X-propagation and makes debugging easier.

**Simultaneous update:** All 6 registers (3 data + 3 valid) update in the same `always @(posedge clk)` block using NBA (`<=`). This ensures the old values are read for all stages before any register is updated.

## Files

- `timing_model.py` — veriflow_spec sequential model
- `module.v` — hand-written Verilog-2005
