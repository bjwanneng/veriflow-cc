`timescale 1ns / 1ps
`default_nettype none

// =============================================================================
// tb_sm3_core.v - Self-checking Verilog testbench for SM3 core
//
// Cross-check / fallback verification path. Drives the GM/T 0004-2012 "abc"
// KAT and checks the final hash against a pre-computed expected value embedded
// as a 256-bit hex literal.
//
// Timing notes (TB Rule 3 — registered output sampling):
//   - ready / hash_valid are detected at posedge.
//   - hash_out is a registered output: sampled at @(negedge clk) after the
//     posedge where hash_valid was first observed (NBA-settled value).
//   - DUT input assignments use blocking `=` only inside the dedicated reset
//     sequence; all subsequent stimulus uses non-blocking `<=` to avoid
//     racing the DUT's posedge sampling logic.
// =============================================================================

module tb_sm3_core;
    reg          clk;
    reg          rst_n;
    reg          msg_valid;
    reg  [511:0] msg_block;
    reg          is_last;

    wire         ready;
    wire         hash_valid;
    wire [255:0] hash_out;

    // -------------------------------------------------------------------------
    // Pre-computed expected values (from golden_model.py TEST_VECTORS[0])
    // GM/T 0004-2012 "abc" KAT
    // hex digit count check: 256/4 = 64 digits, 512/4 = 128 digits
    // -------------------------------------------------------------------------
    localparam [255:0] EXPECTED_ABC = 256'h66c7f0f4_62eeedd9_d1f2d46b_dc10e4e2_4167c487_5cf2f7a2_297da02b_8f4ba8e0;
    localparam [511:0] MSG_ABC      = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;

    // -------------------------------------------------------------------------
    // DUT instantiation
    // -------------------------------------------------------------------------
    sm3_core dut (
        .clk        (clk),
        .rst_n      (rst_n),
        .msg_valid  (msg_valid),
        .msg_block  (msg_block),
        .is_last    (is_last),
        .ready      (ready),
        .hash_valid (hash_valid),
        .hash_out   (hash_out)
    );

    // -------------------------------------------------------------------------
    // VCD capture (used by vcd2table.py for divergence analysis)
    // -------------------------------------------------------------------------
    initial begin
        $dumpfile("workspace/sim/wave.vcd");
        $dumpvars(0, tb_sm3_core);
    end

    // -------------------------------------------------------------------------
    // 100 MHz clock (10 ns period)
    // -------------------------------------------------------------------------
    initial clk = 1'b0;
    always #5 clk = ~clk;

    // -------------------------------------------------------------------------
    // Cycle counter for diagnostics
    // -------------------------------------------------------------------------
    integer cycle_counter;
    initial cycle_counter = 0;
    always @(posedge clk) cycle_counter <= cycle_counter + 1;

    integer fail_count;
    initial fail_count = 0;

    integer timeout_cnt;

    // -------------------------------------------------------------------------
    // Test sequence
    // -------------------------------------------------------------------------
    initial begin
        // --- Reset (blocking OK inside reset sequence only) ---
        rst_n     = 1'b0;
        msg_valid = 1'b0;
        is_last   = 1'b0;
        msg_block = MSG_ABC;       // hold stimulus stable from start

        // hold reset for 20 ns (>= 2 posedges)
        #20;
        rst_n = 1'b1;
        @(negedge clk);

        // --- Wait for DUT ready ---
        wait (ready === 1'b1);
        @(posedge clk);

        // --- Drive valid pulse (non-blocking, scheduled into NBA region) ---
        msg_valid <= 1'b1;
        is_last   <= 1'b1;
        msg_block <= MSG_ABC;

        // Hold msg_block stable for 2 cycles (cycle 0 handshake + cycle 1 load).
        // DRIVE_PHASE_CYCLES = 1 per spec.timing_convention; we hold +1 cycle
        // for safety so msg_block is stable through the W_regs load posedge.
        @(posedge clk);
        @(posedge clk);
        msg_valid <= 1'b0;
        is_last   <= 1'b0;
        // msg_block left stable (don't care after load)

        // --- Wait for hash_valid (with timeout) ---
        timeout_cnt = 0;
        while (hash_valid !== 1'b1 && timeout_cnt < 200) begin
            @(posedge clk);
            timeout_cnt = timeout_cnt + 1;
        end

        if (hash_valid === 1'b1) begin
            // Registered DATA output: re-sample after NBA settles
            @(negedge clk);
            $display("[TB] hash_valid asserted at cycle %0d", cycle_counter);
            $display("[TB] hash_out = 0x%064h", hash_out);
            if (hash_out === EXPECTED_ABC) begin
                $display("========================================");
                $display("SUCCESS: Hash matches GM/T 0004-2012 'abc' KAT!");
                $display("ALL TESTS PASSED");
                $display("========================================");
            end else begin
                fail_count = fail_count + 1;
                $display("========================================");
                $display("[FAIL] test=abc_kat cycle=%0d signal=hash_out width=256b",
                         cycle_counter);
                $display("  expected = 0x%064h", EXPECTED_ABC);
                $display("  actual   = 0x%064h", hash_out);
                $display("  xor diff = 0x%064h", EXPECTED_ABC ^ hash_out);
                $display("  root_cause = signal_mismatch (DUT computation)");
                $display("FAILED: %0d assertion(s) failed", fail_count);
                $display("========================================");
            end
            #20 $finish;
        end else begin
            $display("========================================");
            $display("[FAIL] test=abc_kat cycle=%0d signal=hash_valid",
                     cycle_counter);
            $display("  TIMEOUT waiting for hash_valid");
            $display("  final ready      = %b", ready);
            $display("  final hash_valid = %b", hash_valid);
            $display("  final hash_out   = 0x%064h", hash_out);
            $display("  root_cause = signal_mismatch (DUT never asserted hash_valid)");
            $display("FAILED: timeout");
            $display("========================================");
            $finish;
        end
    end
endmodule

`resetall
