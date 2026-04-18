# VeriFlow Pipeline Stage Journal

This file records the progress, outputs, and key decisions for each pipeline stage.

## Stage: architect
**Status**: completed
**Timestamp**: 2026-04-15T21:28:36+08:00
**Outputs**: workspace/docs/spec.json, workspace/docs/behavior_spec.md
**Notes**: Specification and behavior spec generated. Baud rate 115200 with DIV=27 (0.47% error), 16x oversampling, 8N1 frame.

## Stage: microarch
**Status**: completed
**Timestamp**: 2026-04-15T21:30:04+08:00
**Outputs**: workspace/docs/micro_arch.md
**Notes**: Microarchitecture documented with 4 modules (uart_top, baud_gen, uart_tx, uart_rx), TX/RX FSMs defined, resource estimate ~57 LUTs / ~44 FFs.

## Stage: timing
**Status**: completed
**Timestamp**: 2026-04-15T21:32:04+08:00
**Outputs**: workspace/docs/timing_model.yaml, workspace/tb/tb_uart_top.v
**Notes**: Timing model with 7 scenarios (reset, 4 loopback patterns, tx_busy, multi-frame). Testbench with loopback verification.

## Stage: coder
**Status**: completed
**Timestamp**: 2026-04-15T21:38:16+08:00
**Outputs**: workspace/rtl/baud_gen.v, workspace/rtl/uart_tx.v, workspace/rtl/uart_rx.v, workspace/rtl/uart_top.v
**Notes**: All 4 RTL modules generated via vf-coder sub-agents.

## Stage: skill_d
**Status**: completed
**Timestamp**: 2026-04-15T21:40:15+08:00
**Outputs**: workspace/docs/static_report.json
**Notes**: Static analysis passed. No latches, no CDC risks, no functional gaps. ~57 LUTs, ~55 FFs, max logic depth 6 levels (budget 200).

## Stage: lint
**Status**: completed
**Timestamp**: 2026-04-15T21:41:25+08:00
**Outputs**: logs/lint.log
**Notes**: Fixed 2 syntax errors in uart_tx.v (wire->reg on line 48, <=> on line 53). Lint passed clean after fix.

## Stage: sim
**Status**: completed
**Timestamp**: 2026-04-15T21:43:59+08:00
**Outputs**: workspace/sim/tb.vvp, logs/sim.log
**Notes**: Fixed TB timing bug in Scenario 6 (rx_done pulse missed during repeat waits). All 8 tests pass: reset, 4 loopback patterns (0xA5/0x3C/0xFF/0x00), tx_busy flag, multi-frame.

## Stage: synth
**Status**: completed
**Timestamp**: 2026-04-15T21:44:39+08:00
**Outputs**: workspace/synth/synth_report.txt
**Notes**: Synthesis passed. 330 total cells (57 FFs, ~200 combinational). 0 problems reported by CHECK pass.
