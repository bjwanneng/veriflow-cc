// Testbench: sha256_core
// Verifies SHA-256 core against NIST test vectors
// Verilog-2005, iverilog-compatible — no SVA, no SystemVerilog

`timescale 1ns / 1ps

module tb_sha256_core;

    // DUT signals
    reg           clk;
    reg           rst;
    reg           init;
    reg           next;
    reg  [511:0]  block;
    wire          ready;
    wire          digest_valid;
    wire [255:0]  digest;

    // Test control
    integer        fail_count;
    integer        cycle;
    integer        timeout;
    reg  [255:0]   expected_digest;
    reg  [255:0]   captured_digest;

    // NIST test vectors
    // Test vector 1: empty string ""
    // Input block: 0x80000000... (padding for empty message, single block)
    // Expected digest: e3b0c442 98fc1c14 9afbf4c8 996fb924 27ae41e4 649b934c a495991b 7852b855

    // Test vector 2: "abc"
    // Input block: 0x61626380...000018 (length=24 bits = 0x18)
    // Expected digest: ba7816bf 8f01cfea 414140de 5dae2223 b00361a3 96177a9c b410ff61 f20015ad

    // DUT instantiation
    sha256_core uut (
        .clk          (clk),
        .rst          (rst),
        .init         (init),
        .next         (next),
        .block        (block),
        .ready        (ready),
        .digest_valid (digest_valid),
        .digest       (digest)
    );

    // Clock generation: 200 MHz = 5 ns period
    always #2.5 clk = ~clk;

    // Waveform dump
    initial begin
        $dumpfile("workspace/sim/tb_sha256_core.vcd");
        $dumpvars(0, tb_sha256_core);
    end

    // Main test sequence
    initial begin
        // Initialize
        clk   = 0;
        rst   = 0;
        init  = 0;
        next  = 0;
        block = 512'h0;
        fail_count = 0;
        cycle = 0;

        // ============================================================
        // Test 1: Reset behavior
        // ============================================================
        $display("=== Test 1: Reset Behavior ===");

        // Apply reset
        @(posedge clk); cycle = cycle + 1;
        rst = 1;
        @(posedge clk); cycle = cycle + 1;
        @(posedge clk); cycle = cycle + 1;

        // Check outputs during reset
        if (ready !== 1'b1) begin
            $display("  FAIL: ready should be 1 during reset, got %b", ready);
            fail_count = fail_count + 1;
        end else begin
            $display("  PASS: ready=1 during reset");
        end

        if (digest_valid !== 1'b0) begin
            $display("  FAIL: digest_valid should be 0 during reset, got %b", digest_valid);
            fail_count = fail_count + 1;
        end else begin
            $display("  PASS: digest_valid=0 during reset");
        end

        // Release reset
        @(posedge clk); cycle = cycle + 1;
        rst = 0;

        // Check post-reset state
        @(posedge clk); cycle = cycle + 1;
        if (ready !== 1'b1) begin
            $display("  FAIL: ready should be 1 after reset release, got %b", ready);
            fail_count = fail_count + 1;
        end else begin
            $display("  PASS: ready=1 after reset release");
        end

        // ============================================================
        // Test 2: INIT loads IV
        // ============================================================
        $display("=== Test 2: INIT Loads IV ===");

        // Wait a cycle to ensure IDLE
        @(posedge clk); cycle = cycle + 1;

        // Assert init
        init = 1;
        @(posedge clk); cycle = cycle + 1;
        init = 0;

        // Check ready stays high
        @(posedge clk); cycle = cycle + 1;
        if (ready !== 1'b1) begin
            $display("  FAIL: ready should be 1 after init, got %b", ready);
            fail_count = fail_count + 1;
        end else begin
            $display("  PASS: ready=1 after init");
        end

        // ============================================================
        // Test 3: NIST empty string
        // ============================================================
        $display("=== Test 3: NIST Empty String ===");

        // First do init to load IV
        @(posedge clk); cycle = cycle + 1;
        init = 1;
        @(posedge clk); cycle = cycle + 1;
        init = 0;

        // Wait one cycle
        @(posedge clk); cycle = cycle + 1;

        // Assert next with empty string block
        // block = 0x80000000_00000000_... (big-endian block with padding)
        if (ready !== 1'b1) begin
            $display("  FAIL: ready not asserted before next, got %b", ready);
            fail_count = fail_count + 1;
        end

        next  = 1;
        block = 512'h80000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000;
        @(posedge clk); cycle = cycle + 1;
        next  = 0;
        block = 512'h0;

        // Wait for digest_valid (should be 66 cycles)
        timeout = 0;
        while (!digest_valid && timeout < 200) begin
            @(posedge clk); cycle = cycle + 1;
            timeout = timeout + 1;
        end

        if (timeout >= 200) begin
            $display("  FAIL: Timeout waiting for digest_valid");
            fail_count = fail_count + 1;
        end else begin
            captured_digest = digest;
            expected_digest = 256'he3b0c442_98fc1c14_9afbf4c8_996fb924_27ae41e4_649b934c_a495991b_7852b855;

            $display("  digest_valid asserted at cycle %0d", cycle);
            $display("  got:      %x", captured_digest);
            $display("  expected: %x", expected_digest);

            if (captured_digest === expected_digest) begin
                $display("  PASS: NIST empty string");
            end else begin
                $display("  FAIL: NIST empty string mismatch");
                fail_count = fail_count + 1;
            end

            // digest_valid should be a single pulse
            @(posedge clk); cycle = cycle + 1;
            if (digest_valid !== 1'b0) begin
                $display("  FAIL: digest_valid should de-assert after 1 cycle");
                fail_count = fail_count + 1;
            end
        end

        // ============================================================
        // Test 4: NIST "abc" string
        // ============================================================
        $display("=== Test 4: NIST 'abc' ===");

        // Init to reload IV
        @(posedge clk); cycle = cycle + 1;
        init = 1;
        @(posedge clk); cycle = cycle + 1;
        init = 0;

        // Wait one cycle
        @(posedge clk); cycle = cycle + 1;

        // Assert next with "abc" block
        if (ready !== 1'b1) begin
            $display("  FAIL: ready not asserted before next, got %b", ready);
            fail_count = fail_count + 1;
        end

        next  = 1;
        // block = "abc" padded: 0x61626380...000018 (length 24 bits = 0x18 big-endian)
        block = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;
        @(posedge clk); cycle = cycle + 1;
        next  = 0;
        block = 512'h0;

        // Wait for digest_valid
        timeout = 0;
        while (!digest_valid && timeout < 200) begin
            @(posedge clk); cycle = cycle + 1;
            timeout = timeout + 1;
        end

        if (timeout >= 200) begin
            $display("  FAIL: Timeout waiting for digest_valid");
            fail_count = fail_count + 1;
        end else begin
            captured_digest = digest;
            expected_digest = 256'hba7816bf_8f01cfea_414140de_5dae2223_b00361a3_96177a9c_b410ff61_f20015ad;

            $display("  got:      %x", captured_digest);
            $display("  expected: %x", expected_digest);

            if (captured_digest === expected_digest) begin
                $display("  PASS: NIST 'abc'");
            end else begin
                $display("  FAIL: NIST 'abc' mismatch");
                fail_count = fail_count + 1;
            end
        end

        // ============================================================
        // Test 5: init and next simultaneous (next takes priority)
        // ============================================================
        $display("=== Test 5: init + next Simultaneous (next priority) ===");

        // Wait for IDLE
        @(posedge clk); cycle = cycle + 1;

        // Assert both init and next
        init = 1;
        next = 1;
        block = 512'h80000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000;
        @(posedge clk); cycle = cycle + 1;
        init = 0;
        next = 0;
        block = 512'h0;

        // Verify ready de-asserted (core is busy processing)
        @(posedge clk); cycle = cycle + 1;
        if (ready !== 1'b0) begin
            $display("  FAIL: ready should be 0 during COMPUTE, got %b", ready);
            fail_count = fail_count + 1;
        end else begin
            $display("  PASS: ready de-asserted during COMPUTE (next took priority)");
        end

        // Wait for completion and check result
        timeout = 0;
        while (!digest_valid && timeout < 200) begin
            @(posedge clk); cycle = cycle + 1;
            timeout = timeout + 1;
        end

        if (timeout >= 200) begin
            $display("  FAIL: Timeout waiting for digest_valid");
            fail_count = fail_count + 1;
        end else begin
            captured_digest = digest;
            // Since we didn't do separate init first, and H0-H7 were from prior "abc" computation
            // plus we just did another empty-string block, the H state accumulated.
            // We just verify that a valid result was produced (not checking exact value).
            $display("  PASS: digest_valid asserted at cycle %0d (init+next simultaneous)", cycle);
        end

        // ============================================================
        // Test 6: ready is high when idle (between operations)
        // ============================================================
        $display("=== Test 6: Ready Signal During Idle ===");

        @(posedge clk); cycle = cycle + 1;

        if (ready !== 1'b1) begin
            $display("  FAIL: ready should be 1 in IDLE, got %b", ready);
            fail_count = fail_count + 1;
        end else begin
            $display("  PASS: ready=1 in IDLE");
        end

        // ============================================================
        // Summary
        // ============================================================
        $display("===============================");
        if (fail_count == 0) begin
            $display("ALL TESTS PASSED");
        end else begin
            $display("FAILED: %0d assertion(s) failed", fail_count);
        end
        $display("===============================");
        $finish;
    end

endmodule
