// -----------------------------------------------------------------------------
// File   : tb_sm3_core.v
// Author : VeriFlow Pipeline
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   Testbench for SM3 Core compression module. Tests reset behavior,
//   official GM/T 0004-2012 'abc' test vector, backpressure protocol,
//   and multi-block chaining.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  VeriFlow  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module tb_sm3_core();

    // -------------------------------------------------------------------------
    // DUT signals
    // -------------------------------------------------------------------------
    reg          clk;
    reg          rst;
    reg          msg_valid;
    reg  [511:0] msg_block;
    reg          is_last;

    wire         ready;
    wire         hash_valid;
    wire [255:0] hash_out;

    // -------------------------------------------------------------------------
    // Test tracking
    // -------------------------------------------------------------------------
    integer      fail_count;
    integer      test_num;

    // -------------------------------------------------------------------------
    // DUT instantiation
    // -------------------------------------------------------------------------
    sm3_core u_sm3_core (
        .clk        (clk),
        .rst        (rst),
        .msg_valid  (msg_valid),
        .msg_block  (msg_block),
        .is_last    (is_last),
        .ready      (ready),
        .hash_valid (hash_valid),
        .hash_out   (hash_out)
    );

    // -------------------------------------------------------------------------
    // Clock generation: 150 MHz = 6.667 ns period
    // -------------------------------------------------------------------------
    initial begin
        clk = 1'b0;
        forever #3.333 clk = ~clk;
    end

    // -------------------------------------------------------------------------
    // Waveform dump
    // -------------------------------------------------------------------------
    initial begin
        $dumpfile("sm3_core.vcd");
        $dumpvars(0, tb_sm3_core);
    end

    // -------------------------------------------------------------------------
    // Helper task: report failure
    // -------------------------------------------------------------------------
    task check;
        input expected;
        input actual;
        input [1023:0] msg;
        begin
            if (expected !== actual) begin
                $display("  FAIL [T%0d]: %s (expected %b, got %b)", test_num, msg, expected, actual);
                fail_count = fail_count + 1;
            end
        end
    endtask

    task check_hash;
        input [255:0] expected;
        input [255:0] actual;
        input [1023:0] msg;
        begin
            if (expected !== actual) begin
                $display("  FAIL [T%0d]: %s", test_num, msg);
                $display("    Expected: %h", expected);
                $display("    Got     : %h", actual);
                fail_count = fail_count + 1;
            end
        end
    endtask

    // -------------------------------------------------------------------------
    // Main test sequence
    // -------------------------------------------------------------------------
    initial begin
        fail_count = 0;
        test_num   = 0;

        // Initialize inputs
        rst       = 1'b1;
        msg_valid = 1'b0;
        is_last   = 1'b0;
        msg_block = 512'd0;

        // Wait a few cycles in reset
        repeat (3) @(posedge clk);

        // =====================================================================
        // Test 1: Reset behavior
        // =====================================================================
        test_num = 1;
        $display("[TEST 1] Reset behavior");
        rst = 1'b1;
        repeat (2) @(posedge clk);
        #1;
        check(1'b0, ready, "ready should be 0 during reset");
        check(1'b0, hash_valid, "hash_valid should be 0 during reset");

        rst = 1'b0;
        @(posedge clk);
        #1;
        check(1'b1, ready, "ready should be 1 after reset de-assert");
        $display("[TEST 1] Done");

        // =====================================================================
        // Test 2: Official 'abc' single-block hash (GM/T 0004-2012)
        // =====================================================================
        test_num = 2;
        $display("[TEST 2] 'abc' single-block hash");

        // Wait for ready
        wait (ready == 1'b1);
        @(posedge clk);

        msg_valid = 1'b1;
        is_last   = 1'b1;
        // "abc" padded block: 0x61626380 ... 0x00000018
        msg_block = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;

        @(posedge clk);
        msg_valid = 1'b0;
        is_last   = 1'b0;
        #1;
        check(1'b0, ready, "ready should be low after accepting block");

        // Wait for hash_valid
        wait (hash_valid == 1'b1);
        #1;
        check_hash(
            256'h66c7f0f4_62eeedd9_d1f2d46b_dc10e4e2_4167c487_5cf2f7a2_297da02b_8f4ba8e0,
            hash_out,
            "Hash mismatch for 'abc' test vector"
        );
        $display("[TEST 2] Done");

        // One cycle to return to IDLE
        @(posedge clk);

        // =====================================================================
        // Test 3: Backpressure protocol (msg_valid while ready=0 is ignored)
        // =====================================================================
        test_num = 3;
        $display("[TEST 3] Backpressure protocol");

        // Reset to clear V registers between independent hash operations
        rst = 1'b1;
        repeat (2) @(posedge clk);
        rst = 1'b0;
        @(posedge clk);
        #1;
        check(1'b1, ready, "ready should be 1 after reset de-assert");

        // Wait for ready after previous test
        wait (ready == 1'b1);
        @(posedge clk);

        // Start first block
        msg_valid = 1'b1;
        is_last   = 1'b1;
        msg_block = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;

        @(posedge clk);

        // Assert msg_valid again while ready is low (should be ignored)
        msg_valid = 1'b1;
        is_last   = 1'b1;
        // Keep msg_block stable; the RTL may still be loading the accepted block

        @(posedge clk);
        msg_valid = 1'b0;
        is_last   = 1'b0;

        // Wait for completion — should still produce correct 'abc' hash
        wait (hash_valid == 1'b1);
        #1;
        check_hash(
            256'h66c7f0f4_62eeedd9_d1f2d46b_dc10e4e2_4167c487_5cf2f7a2_297da02b_8f4ba8e0,
            hash_out,
            "Backpressure test: hash should match 'abc' (second msg_valid ignored)"
        );
        $display("[TEST 3] Done");

        @(posedge clk);

        // =====================================================================
        // Test 4: Multi-block chain (two identical blocks)
        // =====================================================================
        test_num = 4;
        $display("[TEST 4] Multi-block chain");

        // Reset to start multi-block chain from IV
        rst = 1'b1;
        repeat (2) @(posedge clk);
        rst = 1'b0;
        @(posedge clk);
        #1;
        check(1'b1, ready, "ready should be 1 after reset de-assert");

        wait (ready == 1'b1);
        @(posedge clk);

        // First block: is_last = 0
        msg_valid = 1'b1;
        is_last   = 1'b0;
        msg_block = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;

        @(posedge clk);
        msg_valid = 1'b0;
        is_last   = 1'b0;
        #1;

        // Wait for ready again (first block done, no hash output)
        wait (ready == 1'b1);
        @(posedge clk);

        // Second block: is_last = 1
        msg_valid = 1'b1;
        is_last   = 1'b1;
        msg_block = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;

        @(posedge clk);
        msg_valid = 1'b0;
        is_last   = 1'b0;

        // Wait for final hash
        wait (hash_valid == 1'b1);
        #1;
        // Two identical blocks produce a different hash than single block
        // We just verify hash_out is non-zero and hash_valid is correct
        if (hash_out == 256'd0) begin
            $display("  FAIL [T%0d]: Multi-block hash should not be zero", test_num);
            fail_count = fail_count + 1;
        end
        $display("[TEST 4] Done (hash_out = %h)", hash_out);

        // =====================================================================
        // Summary
        // =====================================================================
        @(posedge clk);
        if (fail_count == 0) begin
            $display("========================================");
            $display("ALL TESTS PASSED");
            $display("========================================");
        end else begin
            $display("========================================");
            $display("FAILED: %0d assertion(s) failed", fail_count);
            $display("========================================");
        end

        $finish;
    end

endmodule

`resetall
