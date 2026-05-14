// tb_aes_128_core.v — integration testbench for aes_128_core
//
// Tests 3 FIPS-197 / NIST AES-128 test vectors against the aes_128_core DUT.
// Uses async active-low reset (rst_n) and 100 MHz clock (10 ns period).
//
// Timing:
//   - start is a single-cycle pulse, co-asserted with data_in/key_in
//   - data_in and key_in held for >= 12 cycles after start (DRIVE_PHASE_CYCLES+1)
//   - valid is a registered single-cycle pulse; data_out is registered
//   - data_out sampled at negedge AFTER valid detected at posedge (Rule 4B)
//
// Test vectors (verified against NIST FIPS 197):
//   TV0: FIPS-197 Appendix B
//   TV1: FIPS-197 Appendix C.1 AES-128
//   TV2: NIST CAVP ECB MMT

module tb_aes_128_core;

    // ─── DUT ports ──────────────────────────────────────────────────────
    reg         clk;
    reg         rst_n;
    reg         start;
    reg  [127:0] data_in;
    reg  [127:0] key_in;
    wire [127:0] data_out;
    wire         valid;

    // ─── Test infrastructure ────────────────────────────────────────────
    integer cycle_count = 0;
    integer fail_count  = 0;
    integer test_num    = 0;
    integer wait_cyc;

    // ─── Test vector constants (128-bit, MSB-first) ─────────────────────
    // TV0: FIPS-197 Appendix B
    localparam [127:0] TV0_PLAIN = 128'h3243f6a8_885a308d_313198a2_e0370734;
    localparam [127:0] TV0_KEY   = 128'h2b7e1516_28aed2a6_abf71588_09cf4f3c;
    localparam [127:0] TV0_CIPHER = 128'h3925841d_02dc09fb_dc118597_196a0b32;

    // TV1: FIPS-197 Appendix C.1 AES-128
    localparam [127:0] TV1_PLAIN  = 128'h00112233_44556677_8899aabb_ccddeeff;
    localparam [127:0] TV1_KEY    = 128'h00010203_04050607_08090a0b_0c0d0e0f;
    localparam [127:0] TV1_CIPHER = 128'h69c4e0d8_6a7b0430_d8cdb780_70b4c55a;

    // TV2: NIST CAVP ECB MMT (key=2b7e15...)
    localparam [127:0] TV2_PLAIN  = 128'hae2d8a57_1e03ac9c_9eb76fac_45af8e51;
    localparam [127:0] TV2_KEY    = 128'h2b7e1516_28aed2a6_abf71588_09cf4f3c;
    localparam [127:0] TV2_CIPHER = 128'hf5d3d585_03b9699d_e785895a_96fdbaaf;

    // ─── DUT instantiation ──────────────────────────────────────────────
    aes_128_core uut (
        .clk      (clk),
        .rst_n    (rst_n),
        .start    (start),
        .data_in  (data_in),
        .key_in   (key_in),
        .data_out (data_out),
        .valid    (valid)
    );

    // ─── Clock generation — 100 MHz, 10 ns period ──────────────────────
    initial clk = 0;
    always #5 clk = ~clk;   // half-period = 5 ns

    // ─── Cycle counter ──────────────────────────────────────────────────
    always @(posedge clk) cycle_count = cycle_count + 1;

    // ─── VCD capture ────────────────────────────────────────────────────
    initial begin
        $dumpfile("tb_aes_128_core.vcd");
        $dumpvars(0, tb_aes_128_core);
    end

    // ===========================================================================
    // MACROS: Race-free sampling helpers
    // ===========================================================================
    // Failure log format (parsed by timing_diagnostic.py):
    //   [FAIL] test=<name> cycle=<n> signal=<s> kind=<registered|pulse>
    //          width=<w>b expected=0x<hex> actual=0x<hex> xor=0x<hex> phase=<edge>

    `define CHECK_REGISTERED_OUTPUT(sig, expected, test_name) \
        @(negedge clk); \
        if (sig !== expected) begin \
            $display("[FAIL] test=%s cycle=%0d signal=%s kind=registered width=%0db expected=0x%0h actual=0x%0h xor=0x%0h phase=negedge", \
                     test_name, cycle_count, `"sig`", $bits(sig), expected, sig, (expected ^ sig)); \
            fail_count = fail_count + 1; \
        end else \
            $display("[PASS] test=%s cycle=%0d signal=%s kind=registered width=%0db actual=0x%0h phase=negedge", \
                     test_name, cycle_count, `"sig`", $bits(sig), sig);

    `define CHECK_PULSE_OUTPUT(sig, expected, test_name) \
        if (sig !== expected) begin \
            $display("[FAIL] test=%s cycle=%0d signal=%s kind=pulse width=%0db expected=0x%0h actual=0x%0h xor=0x%0h phase=posedge", \
                     test_name, cycle_count, `"sig`", $bits(sig), expected, sig, (expected ^ sig)); \
            fail_count = fail_count + 1; \
        end else \
            $display("[PASS] test=%s cycle=%0d signal=%s kind=pulse width=%0db actual=0x%0h phase=posedge", \
                     test_name, cycle_count, `"sig`", $bits(sig), sig);

    // ===========================================================================
    // RESET TASK: Async active-low reset
    //
    // Rule 2: Reset sequence timing
    //   rst_n = 0 (assert), hold >= 2 cycles, rst_n = 1 (deassert).
    //   Wait @(negedge clk) after deassert for NBA region to settle.
    // ===========================================================================
    task automatic apply_reset;
        begin
            rst_n   = 0;
            start   <= 1'b0;
            data_in <= 128'd0;
            key_in  <= 128'd0;
            @(posedge clk); @(posedge clk); @(posedge clk);
            rst_n   = 1;
            @(negedge clk);   // wait for NBA to settle after rst deassert
            $display("[TRACE] cycle=%0d rst_n released", cycle_count);
        end
    endtask

    // ===========================================================================
    // Task: Run a single AES test vector
    //
    // Sequence:
    //   1. Apply reset
    //   2. Drive data_in, key_in (NBA)
    //   3. Assert start pulse for 1 cycle (NBA)
    //   4. Hold data_in/key_in for DRIVE_PHASE_CYCLES+1 = 12 cycles after start
    //   5. Wait for valid pulse (poll at posedge)
    //   6. Sample data_out at negedge AFTER valid detected (Rule 4B)
    //   7. Check data_out against expected ciphertext
    //   8. Clear data_in/key_in
    // ===========================================================================
    task automatic run_test_vector;
        input [127:0] plaintext;
        input [127:0] cipherkey;
        input [127:0] expected_cipher;
        input [1023:0] test_name;   // string-ish for display
        begin
            test_num = test_num + 1;
            $display("============================================================");
            $display("[TEST %0d] %0s", test_num, test_name);
            $display("[TEST %0d] plaintext  = 0x%0h", test_num, plaintext);
            $display("[TEST %0d] key        = 0x%0h", test_num, cipherkey);
            $display("[TEST %0d] expected   = 0x%0h", test_num, expected_cipher);
            $display("============================================================");

            // Step 1: Reset
            apply_reset();

            // Step 2: Drive data_in, key_in with NBA
            data_in <= plaintext;
            key_in  <= cipherkey;
            @(posedge clk);   // let values settle

            // Step 3: Assert start pulse (1 cycle, NBA)
            start   <= 1'b1;
            @(posedge clk);   // DUT samples start=1, data_in, key_in
            start   <= 1'b0;

            $display("[TRACE] cycle=%0d start pulsed, data/key held", cycle_count);

            // Step 4: Hold data_in/key_in for DRIVE_PHASE_CYCLES = 11 more cycles
            // (total 12 cycles from start assertion: 1 sampling + 11 hold)
            repeat (11) @(posedge clk);

            $display("[TRACE] cycle=%0d data hold complete, waiting for valid", cycle_count);

            // Step 5: Wait for valid pulse (poll at posedge, max 200 cycles)
            wait_cyc = 0;
            while (valid !== 1'b1 && wait_cyc < 200) begin
                @(posedge clk);
                wait_cyc = wait_cyc + 1;
            end

            if (wait_cyc >= 200) begin
                $display("[FAIL] test=%0s cycle=%0d: TIMEOUT waiting for valid pulse", test_name, cycle_count);
                fail_count = fail_count + 1;
            end else begin
                // Step 5b: Check valid pulse at the posedge where detected
                `CHECK_PULSE_OUTPUT(valid, 1'b1, test_name)

                // Step 6: Sample data_out at negedge AFTER valid (Rule 4B)
                `CHECK_REGISTERED_OUTPUT(data_out, expected_cipher, test_name)

                $display("[TEST %0d] cycle=%0d valid detected, data_out sampled", test_num, cycle_count);
            end

            // Step 7: Clear data/key inputs
            data_in <= 128'd0;
            key_in  <= 128'd0;
            @(posedge clk);

            // Wait a few cycles before next test
            repeat (2) @(posedge clk);
        end
    endtask

    // ===========================================================================
    // Main test sequence: Run all 3 test vectors
    // ===========================================================================
    initial begin
        $display("============================================================");
        $display("tb_aes_128_core — AES-128 Encryption Core Integration Test");
        $display("Clock: 100 MHz, Reset: async active-low (rst_n)");
        $display("DRIVE_PHASE_CYCLES = 11, input hold = 12 cycles");
        $display("============================================================");

        // Wait for initial stabilization
        #1;

        // ── Test Vector 0: FIPS-197 Appendix B ──────────────────────────
        run_test_vector(
            TV0_PLAIN,
            TV0_KEY,
            TV0_CIPHER,
            "FIPS-197_Appendix_B"
        );

        // ── Test Vector 1: FIPS-197 Appendix C.1 ────────────────────────
        run_test_vector(
            TV1_PLAIN,
            TV1_KEY,
            TV1_CIPHER,
            "FIPS-197_Appendix_C.1"
        );

        // ── Test Vector 2: NIST CAVP ECB MMT ────────────────────────────
        run_test_vector(
            TV2_PLAIN,
            TV2_KEY,
            TV2_CIPHER,
            "NIST_CAVP_ECB_MMT"
        );

        // ── Summary ────────────────────────────────────────────────────
        $display("============================================================");
        if (fail_count == 0) begin
            $display("ALL TESTS PASSED (%0d test vectors)", test_num);
        end else begin
            $display("FAILED: %0d assertion(s) failed across %0d test vector(s)", fail_count, test_num);
        end
        $display("============================================================");
        $finish;
    end

endmodule
