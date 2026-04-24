# VeriFlow Pipeline Stage Journal

This file records the progress, outputs, and key decisions for each pipeline stage.

## Stage: architect
**Status**: completed
**Timestamp**: 2026-04-24T11:20:57+08:00
**Outputs**: workspace/docs/spec.json, workspace/docs/behavior_spec.md
**Notes**: ChaCha20 iterative architecture spec generated. 3 modules: chacha20_top (top), chacha20_core (processing), chacha20_qr (combinational QR). Target 100MHz generic FPGA. RFC 8439 test vectors for verification.

## Stage: microarch
**Status**: completed
**Timestamp**: 2026-04-24T11:23:51+08:00
**Outputs**: workspace/docs/micro_arch.md
**Notes**: Iterative microarchitecture with 4 parallel QR units. ~630 LUTs, ~1110 FFs, 22 cycles/block.

## Stage: timing
**Status**: completed
**Timestamp**: 2026-04-24T11:27:00+08:00
**Outputs**: workspace/docs/timing_model.yaml, workspace/tb/tb_chacha20.v
**Notes**: Timing model with 5 scenarios. Testbench with RFC 8439 Section 2.3.2 and 2.4.2 test vectors.

## Stage: coder
**Status**: completed
**Timestamp**: 2026-04-24T11:33:46+08:00
**Outputs**: workspace/rtl/chacha20_qr.v, workspace/rtl/chacha20_core.v, workspace/rtl/chacha20_top.v
**Notes**: All 3 RTL modules generated via vf-coder sub-agents.

## Stage: skill_d
**Status**: completed
**Timestamp**: 2026-04-24T11:36:42+08:00
**Outputs**: workspace/docs/static_report.json
**Notes**: Static analysis passed. No latches, no CDC risks, all ports match spec. ~630 LUTs, ~1110 FFs.

## Stage: lint
**Status**: completed
**Timestamp**: 2026-04-24T11:37:31+08:00
**Outputs**: logs/lint.log
**Notes**: iverilog lint passed with zero errors and zero warnings.

## Stage: sim
**Status**: completed
**Timestamp**: 2026-04-24T11:55:42+08:00
**Outputs**: workspace/sim/tb.vvp, logs/sim.log
**Notes**: ALL TESTS PASSED. Fixed byte-swap for key/nonce (not counter), made dout_data_o combinational to fix pipeline delay, fixed testbench typos.

## Stage: synth
**Status**: completed
**Timestamp**: 2026-04-24T11:56:36+08:00
**Outputs**: workspace/synth/synth_report.txt
**Notes**: Yosys synthesis successful. 15,359 total cells. Hierarchy: chacha20_top (5,239 cells) + chacha20_core (9,120 cells) + chacha20_qr x4 (4,468 cells). No errors.
