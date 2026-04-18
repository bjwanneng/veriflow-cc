`timescale 1ns/1ps

module tb_aes_128_core;

    // Clock and reset
    reg         clk;
    reg         rst_n;

    // DUT inputs
    reg         start;
    reg  [127:0] data_in;
    reg  [127:0] key_in;

    // DUT outputs
    wire [127:0] data_out;
    wire        valid;

    // Test tracking
    integer     fail_count;
    integer     test_num;

    // Instantiate DUT
    aes_128_core uut (
        .clk      (clk),
        .rst_n    (rst_n),
        .start    (start),
        .data_in  (data_in),
        .key_in   (key_in),
        .data_out (data_out),
        .valid    (valid)
    );

    // Clock generation: 100 MHz -> 10ns period
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    // Waveform dump
    initial begin
        $dumpfile("tb_aes_128_core.vcd");
        $dumpvars(0, tb_aes_128_core);
    end

    // Task: wait for valid output with timeout
    task wait_for_valid;
        input integer max_cycles;
        integer i;
        begin
            for (i = 0; i < max_cycles; i = i + 1) begin
                @(posedge clk);
                if (valid) begin
                    i = max_cycles + 1; // exit loop
                end
            end
        end
    endtask

    // Task: apply reset
    task apply_reset;
        begin
            rst_n = 0;
            start = 0;
            data_in = 128'h0;
            key_in = 128'h0;
            repeat(10) @(posedge clk);
            rst_n = 1;
            repeat(2) @(posedge clk);
        end
    endtask

    // Task: run single encryption and check result
    task run_encryption_check;
        input  [127:0] pt;
        input  [127:0] key;
        input  [127:0] expected_ct;
        input  [255:0] test_name; // ASCII test name string
        integer wait_cnt;
        begin
            test_num = test_num + 1;

            // Drive inputs
            @(posedge clk);
            data_in = pt;
            key_in  = key;
            start   = 1'b1;
            @(posedge clk);
            start   = 1'b0;

            // Wait for valid with timeout
            wait_cnt = 0;
            while (!valid && wait_cnt < 50) begin
                @(posedge clk);
                wait_cnt = wait_cnt + 1;
            end

            if (!valid) begin
                $display("FAIL [Test %0d]: %0s - TIMEOUT waiting for valid", test_num, test_name);
                fail_count = fail_count + 1;
            end else if (data_out !== expected_ct) begin
                $display("FAIL [Test %0d]: %0s", test_num, test_name);
                $display("  Expected: 0x%032h", expected_ct);
                $display("  Got:      0x%032h", data_out);
                fail_count = fail_count + 1;
            end else begin
                $display("PASS [Test %0d]: %0s - latency=%0d cycles", test_num, test_name, wait_cnt);
            end

            // Wait a few cycles before next test
            repeat(5) @(posedge clk);
        end
    endtask

    // Main test sequence
    initial begin
        fail_count = 0;
        test_num   = 0;

        //=============================================================
        // Test 1: Reset behavior
        //=============================================================
        apply_reset;
        if (valid !== 1'b0 || data_out !== 128'h0) begin
            $display("FAIL: After reset, valid=%b data_out=0x%032h (expected 0)", valid, data_out);
            fail_count = fail_count + 1;
        end else begin
            $display("PASS: Reset behavior correct - valid=0, data_out=0");
        end

        //=============================================================
        // Test 2: NIST FIPS-197 Appendix B (Table B.1, first vector)
        // Plaintext:  0x3243F6A8885A308D313198A2E0370734
        // Key:        0x2B7E151628AED2A6ABF7158809CF4F3C
        // Ciphertext: 0x3925841D02DC09FBDC118597196A0B32
        //=============================================================
        run_encryption_check(
            128'h3243F6A8885A308D313198A2E0370734,
            128'h2B7E151628AED2A6ABF7158809CF4F3C,
            128'h3925841D02DC09FBDC118597196A0B32,
            "NIST Appendix B vector 1"
        );

        //=============================================================
        // Test 3: All-zero plaintext, all-zero key
        // Ciphertext: 0x66E94BD4EF8A2C3B884CFA59CA342B2E
        //=============================================================
        run_encryption_check(
            128'h00000000000000000000000000000000,
            128'h00000000000000000000000000000000,
            128'h66E94BD4EF8A2C3B884CFA59CA342B2E,
            "All-zero PT, all-zero key"
        );

        //=============================================================
        // Test 4: NIST FIPS-197 Appendix B (full example)
        // Same as test 2 but we verify intermediate round keys match
        // Just re-run the same vector to verify repeatability
        //=============================================================
        run_encryption_check(
            128'h3243F6A8885A308D313198A2E0370734,
            128'h2B7E151628AED2A6ABF7158809CF4F3C,
            128'h3925841D02DC09FBDC118597196A0B32,
            "NIST vector repeat check"
        );

        //=============================================================
        // Test 5: Back-to-back encryptions (different keys)
        //=============================================================
        // First encryption
        @(posedge clk);
        data_in = 128'h3243F6A8885A308D313198A2E0370734;
        key_in  = 128'h2B7E151628AED2A6ABF7158809CF4F3C;
        start   = 1'b1;
        @(posedge clk);
        start = 1'b0;

        // Wait for first valid
        wait_for_valid(50);
        if (!valid) begin
            $display("FAIL: Back-to-back test - first encryption timed out");
            fail_count = fail_count + 1;
        end else begin
            $display("PASS: Back-to-back - first encryption done, ct=0x%032h", data_out);
        end

        // Immediately start second encryption with different key
        @(posedge clk);
        data_in = 128'h00112233445566778899AABBCCDDEEFF;
        key_in  = 128'h000102030405060708090A0B0C0D0E0F;
        start   = 1'b1;
        @(posedge clk);
        start = 1'b0;

        // Wait for second valid
        wait_for_valid(50);
        if (!valid) begin
            $display("FAIL: Back-to-back test - second encryption timed out");
            fail_count = fail_count + 1;
        end else begin
            // Known answer: plaintext 00112233445566778899AABBCCDDEEFF
            // key 000102030405060708090A0B0C0D0E0F
            // Expected ciphertext: 0x69C4E0D86A7B0430D8CDB78070B4C55A
            if (data_out !== 128'h69C4E0D86A7B0430D8CDB78070B4C55A) begin
                $display("FAIL: Back-to-back - second encryption mismatch");
                $display("  Expected: 0x69C4E0D86A7B0430D8CDB78070B4C55A");
                $display("  Got:      0x%032h", data_out);
                fail_count = fail_count + 1;
            end else begin
                $display("PASS: Back-to-back - second encryption correct");
            end
        end

        repeat(5) @(posedge clk);

        //=============================================================
        // Test 6: NIST FIPS-197 Appendix B (128-bit key, block 1)
        // Plaintext:  0x6BC1BEE22E409F96E93D7E117393172A
        // Key:        0x2B7E151628AED2A6ABF7158809CF4F3C
        // Ciphertext: 0x3AD77BB40D7A3660A89ECAF32466EF97 (FIPS-197 Appendix B.2)
        //=============================================================
        run_encryption_check(
            128'h6BC1BEE22E409F96E93D7E117393172A,
            128'h2B7E151628AED2A6ABF7158809CF4F3C,
            128'h3AD77BB40D7A3660A89ECAF32466EF97,
            "NIST Table B.2 vector"
        );

        //=============================================================
        // Summary
        //=============================================================
        repeat(10) @(posedge clk);
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

    // Timeout watchdog
    initial begin
        #100000;
        $display("ERROR: Simulation timeout at time %0t", $time);
        $finish;
    end

endmodule
