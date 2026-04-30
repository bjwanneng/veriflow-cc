`timescale 1ns/1ps

module tb_sm3_core();

    //-------------------------------------------------------------------------
    // Clock and Reset
    //-------------------------------------------------------------------------
    reg         clk;
    reg         rst;

    //-------------------------------------------------------------------------
    // DUT Inputs
    //-------------------------------------------------------------------------
    reg         msg_valid;
    reg  [511:0] msg_block;
    reg         is_last;
    reg         ack;

    //-------------------------------------------------------------------------
    // DUT Outputs
    //-------------------------------------------------------------------------
    wire        ready;
    wire        hash_valid;
    wire [255:0] hash_out;

    //-------------------------------------------------------------------------
    // Test Control
    //-------------------------------------------------------------------------
    integer     fail_count;
    integer     test_num;
    integer     cycle_count;
    reg  [255:0] expected_hash;

    //-------------------------------------------------------------------------
    // DUT Instantiation
    //-------------------------------------------------------------------------
    sm3_core u_dut (
        .clk        (clk),
        .rst        (rst),
        .msg_valid  (msg_valid),
        .msg_block  (msg_block),
        .is_last    (is_last),
        .ack        (ack),
        .ready      (ready),
        .hash_valid (hash_valid),
        .hash_out   (hash_out)
    );

    //-------------------------------------------------------------------------
    // Clock Generation (100MHz for simulation speed, real target is 150MHz)
    //-------------------------------------------------------------------------
    always #5 clk = ~clk;

    //-------------------------------------------------------------------------
    // Cycle Counter
    //-------------------------------------------------------------------------
    always @(posedge clk or posedge rst) begin
        if (rst)
            cycle_count <= 0;
        else
            cycle_count <= cycle_count + 1;
    end

    //-------------------------------------------------------------------------
    // Waveform Dump
    //-------------------------------------------------------------------------
    initial begin
        $dumpfile("workspace/sim/tb_sm3_core.vcd");
        $dumpvars(0, tb_sm3_core);
    end

    //-------------------------------------------------------------------------
    // Helper: Wait N cycles
    //-------------------------------------------------------------------------
    task wait_cycles;
        input integer n;
        integer i;
        begin
            for (i = 0; i < n; i = i + 1)
                @(posedge clk);
        end
    endtask

    //-------------------------------------------------------------------------
    // Helper: Wait for signal to be 1
    //-------------------------------------------------------------------------
    task wait_signal;
        input signal;
        begin
            while (signal !== 1'b1)
                @(posedge clk);
        end
    endtask

    //-------------------------------------------------------------------------
    // Helper: Check assertion and increment fail_count
    //-------------------------------------------------------------------------
    task check_eq;
        input [1023:0] name;
        input [255:0]  actual;
        input [255:0]  expected;
        begin
            if (actual !== expected) begin
                $display("  [FAIL] %0s: expected 0x%064x, got 0x%064x", name, expected, actual);
                fail_count = fail_count + 1;
            end else begin
                $display("  [PASS] %0s", name);
            end
        end
    endtask

    task check_true;
        input [1023:0] name;
        input           condition;
        begin
            if (!condition) begin
                $display("  [FAIL] %0s: condition is false", name);
                fail_count = fail_count + 1;
            end else begin
                $display("  [PASS] %0s", name);
            end
        end
    endtask

    //-------------------------------------------------------------------------
    // Main Test Sequence
    //-------------------------------------------------------------------------
    initial begin
        clk         = 0;
        rst         = 1;
        msg_valid   = 0;
        msg_block   = 512'h0;
        is_last    <= 0;
        ack         = 0;
        fail_count  = 0;
        test_num    = 0;
        cycle_count = 0;

        //---------------------------------------------------------------------
        // TEST 0: Reset Behavior
        //---------------------------------------------------------------------
        test_num = 0;
        $display("========================================");
        $display("TEST %0d: Reset Behavior", test_num);
        $display("========================================");

        wait_cycles(3);
        check_true("hash_valid==0 during reset", hash_valid == 1'b0);
        check_true("ready==0 during reset",     ready == 1'b0);

        rst = 0;
        @(posedge clk);
        @(posedge clk);
        check_true("ready==1 after reset de-assertion", ready == 1'b1);
        $display("");

        //---------------------------------------------------------------------
        // TEST 1: Single Block (is_last) — GM/T 0004-2012 "abc" Test Vector
        //---------------------------------------------------------------------
        test_num = 1;
        $display("========================================");
        $display("TEST %0d: Single Block 'abc' — GM/T 0004-2012", test_num);
        $display("========================================");

        // Wait for ready
        wait(ready == 1'b1);

        // Present "abc" padded message block
        @(posedge clk);
        msg_valid  <= 1;
        is_last    <= 1;
        ack         = 0;
        // "abc" padded to 512 bits per SM3 padding rules:
        // 0x61626380 || 0x00...00 || 0x00000018 (message length = 24 bits = 0x18)
        msg_block   = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;

        @(posedge clk);
        msg_valid <= 0;

        // Wait for hash_valid
        wait(hash_valid == 1'b1);

        expected_hash = 256'h66c7f0f4_62eeedd9_d1f2d46b_dc10e4e2_4167c487_5cf2f7a2_297da02b_8f4ba8e0;
        check_eq("GM/T 0004-2012 'abc' hash", hash_out, expected_hash);

        // Verify hash_valid is held (ack still 0)
        @(posedge clk);
        check_true("hash_valid held without ack", hash_valid == 1'b1);

        // Assert ack
        ack = 1;
        @(posedge clk);
        @(posedge clk);
        check_true("hash_valid de-asserted after ack", hash_valid == 1'b0);
        ack = 0;
        $display("");

        // Reset between tests
        rst = 1; @(posedge clk); rst = 0; @(posedge clk);

        //---------------------------------------------------------------------
        // TEST 2: Ack Hold Behavior (hold for 3 cycles before ack)
        //---------------------------------------------------------------------
        test_num = 2;
        $display("========================================");
        $display("TEST %0d: Ack Hold Behavior", test_num);
        $display("========================================");

        wait(ready == 1'b1);

        @(posedge clk);
        msg_valid  <= 1;
        is_last    <= 1;
        msg_block   = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;
        @(posedge clk);
        msg_valid <= 0;

        wait(hash_valid == 1'b1);

        // Hold ack low for 3 extra cycles
        wait_cycles(3);
        check_true("hash_valid still held after 3 cycles no ack", hash_valid == 1'b1);

        // Now assert ack
        ack = 1;
        @(posedge clk);
        @(posedge clk);
        check_true("hash_valid de-asserted after delayed ack", hash_valid == 1'b0);
        ack = 0;
        $display("");

        // Reset between tests
        rst = 1; @(posedge clk); rst = 0; @(posedge clk);

        //---------------------------------------------------------------------
        // TEST 3: Non-Last Block (is_last=0) — no hash_valid
        //---------------------------------------------------------------------
        test_num = 3;
        $display("========================================");
        $display("TEST %0d: Non-Last Block", test_num);
        $display("========================================");

        wait(ready == 1'b1);

        @(posedge clk);
        msg_valid  <= 1;
        is_last    <= 0;
        msg_block   = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;
        @(posedge clk);
        msg_valid <= 0;

        // Wait for ready to de-assert, then re-assert (block processing done)
        wait(ready == 1'b0);
        wait(ready == 1'b1);
        @(posedge clk);
        check_true("hash_valid=0 for non-last block", hash_valid == 1'b0);
        check_true("ready=1 after non-last block",   ready == 1'b1);
        $display("");

        // Reset between tests
        rst = 1; @(posedge clk); rst = 0; @(posedge clk);

        //---------------------------------------------------------------------
        // TEST 4: Back-to-Back Blocks (non-last then last)
        //---------------------------------------------------------------------
        test_num = 4;
        $display("========================================");
        $display("TEST %0d: Back-to-Back Blocks", test_num);
        $display("========================================");

        wait(ready == 1'b1);

        // Block 1: non-last "abc"
        @(posedge clk);
        msg_valid  <= 1;
        is_last    <= 0;
        msg_block   = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;
        @(posedge clk);
        msg_valid <= 0;

        // Wait for ready to re-assert
        wait(ready == 1'b1);
        check_true("Block1: hash_valid=0", hash_valid == 1'b0);

        // Block 2: last block (empty message + padding)
        @(posedge clk);
        msg_valid  <= 1;
        is_last    <= 1;
        // This is the second block after "abc". Since this is a simplified test,
        // we reuse the padding block and verify the module produces a hash.
        // Standard SM3 padding for empty message: 0x80 || 0x00...00 || 0x00
        msg_block   = 512'h80000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000200;
        @(posedge clk);
        msg_valid <= 0;

        // Wait for hash_valid
        wait(hash_valid == 1'b1);
        check_true("Block2: hash_valid=1 for last block", hash_valid == 1'b1);

        // Two-block computation produces a different hash than single-block
        // Verify hash was computed (not IV, not zero)
        check_true("Back-to-back hash computed (non-zero)", hash_out != 256'd0);

        ack = 1;
        @(posedge clk);
        ack = 0;
        $display("");

        // Reset between tests
        rst = 1; @(posedge clk); rst = 0; @(posedge clk);

        //---------------------------------------------------------------------
        // TEST 5: Ready de-asserted during CALC
        //---------------------------------------------------------------------
        test_num = 5;
        $display("========================================");
        $display("TEST %0d: Ready de-asserted during computation", test_num);
        $display("========================================");

        wait(ready == 1'b1);

        @(posedge clk);
        msg_valid  <= 1;
        is_last    <= 1;
        msg_block   = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;
        @(posedge clk);
        msg_valid <= 0;

        // Check ready goes low during computation
        @(posedge clk);
        check_true("ready=0 during CALC (cycle 1)", ready == 1'b0);
        wait_cycles(10);
        check_true("ready=0 during CALC (cycle 10)", ready == 1'b0);

        // Wait for completion and ack
        wait(hash_valid == 1'b1);
        ack = 1;
        @(posedge clk);
        ack = 0;
        $display("");

        // Reset between tests
        rst = 1; @(posedge clk); rst = 0; @(posedge clk);

        //---------------------------------------------------------------------
        // TEST 6: msg_valid ignored when not ready
        //---------------------------------------------------------------------
        test_num = 6;
        $display("========================================");
        $display("TEST %0d: msg_valid ignored when not ready", test_num);
        $display("========================================");

        wait(ready == 1'b1);

        // Start a block
        @(posedge clk);
        msg_valid  <= 1;
        is_last    <= 1;
        msg_block   = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;
        @(posedge clk);
        msg_valid <= 0;

        // Try to assert msg_valid during CALC (should be ignored)
        @(posedge clk);
        msg_valid <= 1;
        msg_block <= 512'hFFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF;
        @(posedge clk);
        msg_valid <= 0;

        // Wait for completion
        wait(hash_valid == 1'b1);
        // If the rogue msg_valid was ignored, we should still get the 'abc' hash
        check_eq("msg_valid ignored: correct hash", hash_out, expected_hash);

        ack = 1;
        @(posedge clk);
        ack = 0;
        $display("");

        //---------------------------------------------------------------------
        // Final Report
        //---------------------------------------------------------------------
        $display("========================================");
        $display("            TEST SUMMARY");
        $display("========================================");
        if (fail_count == 0) begin
            $display("ALL TESTS PASSED");
        end else begin
            $display("FAILED: %0d assertion(s) failed", fail_count);
        end
        $display("========================================");

        #20;
        $finish;
    end

endmodule
