`timescale 1ns / 1ps

module tb_chacha20;

    // Clock and reset
    reg         clk;
    reg         rst_n;

    // Config
    reg  [255:0] key;
    reg  [95:0]  nonce;
    reg  [31:0]  counter;

    // Control
    reg         start;

    // Data input
    reg         din_valid;
    reg  [31:0] din_data;
    wire        din_ready;

    // Data output
    wire        dout_valid;
    wire [31:0] dout_data;
    reg         dout_ready;

    // Status
    wire        ready;
    wire        block_done;

    integer     fail_count;
    integer     cycle_count;
    integer     i;

    // Instantiate DUT
    chacha20_top uut (
        .clk_i       (clk),
        .rst_n_i     (rst_n),
        .key_i       (key),
        .nonce_i     (nonce),
        .counter_i   (counter),
        .start_i     (start),
        .din_valid_i (din_valid),
        .din_data_i  (din_data),
        .din_ready_o (din_ready),
        .dout_valid_o(dout_valid),
        .dout_data_o (dout_data),
        .dout_ready_i(dout_ready),
        .ready_o     (ready),
        .block_done_o(block_done)
    );

    // Clock generation: 10ns period = 100 MHz
    initial clk = 0;
    always #5 clk = ~clk;

    // Waveform dump
    initial begin
        $dumpfile("tb_chacha20.vcd");
        $dumpvars(0, tb_chacha20);
    end

    // Cycle counter
    always @(posedge clk) begin
        if (!rst_n)
            cycle_count <= 0;
        else
            cycle_count <= cycle_count + 1;
    end

    // -------------------------------------------------------------------
    // RFC 8439 Section 2.3.2 test vector for ChaCha20 Block Function
    // Key: 0x000102...1f, Nonce: 0x000000090000004a00000000, Counter: 1
    // Expected keystream block (16 words, little-endian):
    //   After initial state add, the 16 output words are:
    //   state[0]  = e4e7f110
    //   state[1]  = 15593bd1
    //   state[2]  = 1fdd0f50
    //   state[3]  = c47120a3
    //   state[4]  = c7f4d1c7
    //   state[5]  = 0368c033
    //   state[6]  = 9aaa2204
    //   state[7]  = 4e6cd4c3
    //   state[8]  = 466482d2
    //   state[9]  = 09aa9f07
    //   state[10] = 05d7c214
    //   state[11] = a2028bd9
    //   state[12] = d19c12b5
    //   state[13] = b94e16de
    //   state[14] = e883d0cb
    //   state[15] = 4e3c50a2
    // -------------------------------------------------------------------

    // Expected keystream words (from RFC 8439 Section 2.3.2)
    reg [31:0] expected_ks [0:15];
    initial begin
        expected_ks[0]  = 32'he4e7f110;
        expected_ks[1]  = 32'h15593bd1;
        expected_ks[2]  = 32'h1fdd0f50;
        expected_ks[3]  = 32'hc47120a3;
        expected_ks[4]  = 32'hc7f4d1c7;
        expected_ks[5]  = 32'h0368c033;
        expected_ks[6]  = 32'h9aaa2204;
        expected_ks[7]  = 32'h4e6cd4c3;
        expected_ks[8]  = 32'h466482d2;
        expected_ks[9]  = 32'h09aa9f07;
        expected_ks[10] = 32'h05d7c214;
        expected_ks[11] = 32'ha2028bd9;
        expected_ks[12] = 32'hd19c12b5;
        expected_ks[13] = 32'hb94e16de;
        expected_ks[14] = 32'he883d0cb;
        expected_ks[15] = 32'h4e3c50a2;
    end

    // -------------------------------------------------------------------
    // RFC 8439 Section 2.4.2 plaintext and expected ciphertext
    // Plaintext: "Ladies and Gentlemen of the class of '99"
    // (9 words, 36 bytes padded with zeros to fill 9 x 32-bit words)
    // Plaintext words (little-endian):
    //   "Ladi" = 0x6469644c -> wait, "Ladi" in ASCII: L=4c a=61 d=64 i=69
    //   Little-endian 32-bit: 0x6964614c
    // -------------------------------------------------------------------
    reg [31:0] plaintext [0:15];
    reg [31:0] expected_ct [0:15];
    initial begin
        // Plaintext: "Ladies and Gentlemen of the class of '99" + padding
        // Word 0: "Ladi" -> 4c 61 64 69 -> LE: 0x6964614c
        plaintext[0]  = 32'h6964614c;
        // Word 1: "es a" -> 65 73 20 61 -> LE: 0x61207365
        plaintext[1]  = 32'h61207365;
        // Word 2: "nd G" -> 6e 64 20 47 -> LE: 0x4720646e
        plaintext[2]  = 32'h4720646e;
        // Word 3: "entl" -> 65 6e 74 6c -> LE: 0x6c746e65
        plaintext[3]  = 32'h6c746e65;
        // Word 4: "emen" -> 65 6d 65 6e -> LE: 0x6e656d65
        plaintext[4]  = 32'h6e656d65;
        // Word 5: " of " -> 20 6f 66 20 -> LE: 0x20666f20
        plaintext[5]  = 32'h20666f20;
        // Word 6: "the " -> 74 68 65 20 -> LE: 0x20656874
        plaintext[6]  = 32'h20656874;
        // Word 7: "clas" -> 63 6c 61 73 -> LE: 0x73616c63
        plaintext[7]  = 32'h73616c63;
        // Word 8: "s of" -> 73 20 6f 66 -> LE: 0x666f2073
        plaintext[8]  = 32'h666f2073;
        // Word 9: " '99" -> 20 27 39 39 -> LE: 0x39392720
        plaintext[9]  = 32'h39392720;
        // Words 10-15: padding zeros
        plaintext[10] = 32'h00000000;
        plaintext[11] = 32'h00000000;
        plaintext[12] = 32'h00000000;
        plaintext[13] = 32'h00000000;
        plaintext[14] = 32'h00000000;
        plaintext[15] = 32'h00000000;

        // Expected ciphertext = plaintext XOR keystream
        expected_ct[0]  = plaintext[0]  ^ expected_ks[0];
        expected_ct[1]  = plaintext[1]  ^ expected_ks[1];
        expected_ct[2]  = plaintext[2]  ^ expected_ks[2];
        expected_ct[3]  = plaintext[3]  ^ expected_ks[3];
        expected_ct[4]  = plaintext[4]  ^ expected_ks[4];
        expected_ct[5]  = plaintext[5]  ^ expected_ks[5];
        expected_ct[6]  = plaintext[6]  ^ expected_ks[6];
        expected_ct[7]  = plaintext[7]  ^ expected_ks[7];
        expected_ct[8]  = plaintext[8]  ^ expected_ks[8];
        expected_ct[9]  = plaintext[9]  ^ expected_ks[9];
        expected_ct[10] = plaintext[10] ^ expected_ks[10];
        expected_ct[11] = plaintext[11] ^ expected_ks[11];
        expected_ct[12] = plaintext[12] ^ expected_ks[12];
        expected_ct[13] = plaintext[13] ^ expected_ks[13];
        expected_ct[14] = plaintext[14] ^ expected_ks[14];
        expected_ct[15] = plaintext[15] ^ expected_ks[15];
    end

    // -------------------------------------------------------------------
    // Test task: wait N clock cycles
    // -------------------------------------------------------------------
    task wait_cycles;
        input integer n;
        integer j;
    begin
        for (j = 0; j < n; j = j + 1)
            @(posedge clk);
    end
    endtask

    // -------------------------------------------------------------------
    // Test task: check a 1-bit value
    // -------------------------------------------------------------------
    task check_bit;
        input actual;
        input expected;
        input [256*8-1:0] label;
    begin
        if (actual !== expected) begin
            $display("[FAIL] %0s: got %0b, expected %0b (cycle %0d)", label, actual, expected, cycle_count);
            fail_count = fail_count + 1;
        end else begin
            $display("[PASS] %0s: %0b (cycle %0d)", label, actual, cycle_count);
        end
    end
    endtask

    // -------------------------------------------------------------------
    // Test task: check a 32-bit value
    // -------------------------------------------------------------------
    task check_32;
        input [31:0] actual;
        input [31:0] expected;
        input [256*8-1:0] label;
    begin
        if (actual !== expected) begin
            $display("[FAIL] %0s: got 0x%h, expected 0x%h (cycle %0d)", label, actual, expected, cycle_count);
            fail_count = fail_count + 1;
        end else begin
            $display("[PASS] %0s: 0x%h (cycle %0d)", label, actual, cycle_count);
        end
    end
    endtask

    // -------------------------------------------------------------------
    // Main test sequence
    // -------------------------------------------------------------------
    initial begin
        fail_count = 0;

        // Initialize all inputs
        clk       = 0;
        rst_n     = 0;
        key       = 0;
        nonce     = 0;
        counter   = 0;
        start     = 0;
        din_valid = 0;
        din_data  = 0;
        dout_ready = 0;

        // ============================================================
        // TEST 1: Reset behavior
        // ============================================================
        $display("\n=== TEST 1: Reset Behavior ===");
        wait_cycles(5);

        // De-assert reset
        rst_n = 1;
        wait_cycles(4);

        // Check ready_o is HIGH after reset
        check_bit(ready, 1'b1, "ready_o after reset");

        // ============================================================
        // TEST 2: RFC 8439 Section 2.3.2 - ChaCha20 Block Function
        // Check the raw keystream output (encrypt zero plaintext)
        // ============================================================
        $display("\n=== TEST 2: RFC 8439 Keystream Block ===");

        // Set up RFC 8439 test vector
        key     = 256'h000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f;
        nonce   = 96'h000000090000004a00000000;
        counter = 32'h00000001;

        // Start the core
        start = 1;
        wait_cycles(1);
        start = 0;

        // Wait for computation to complete (22 cycles for core + margin)
        // block_done should pulse after ~22 cycles from start
        wait_cycles(25);

        // Now stream out data: feed zero plaintext, read ciphertext = keystream
        dout_ready = 1;
        din_valid  = 1;

        for (i = 0; i < 16; i = i + 1) begin
            din_data = 32'h00000000;  // XOR with 0 = raw keystream
            @(posedge clk);
            // Wait for valid output
            while (dout_valid !== 1'b1) @(posedge clk);
            check_32(dout_data, expected_ks[i], "keystream word");
        end

        din_valid  = 0;
        dout_ready = 0;

        // Wait for ready
        wait_cycles(5);
        while (ready !== 1'b1) @(posedge clk);

        // ============================================================
        // TEST 3: RFC 8439 Section 2.4.2 - Full Encryption
        // Encrypt "Ladies and Gentlemen of the class of '99"
        // ============================================================
        $display("\n=== TEST 3: RFC 8439 Full Encryption ===");

        key     = 256'h000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f;
        nonce   = 96'h000000090000004a00000000;
        counter = 32'h00000001;

        start = 1;
        wait_cycles(1);
        start = 0;

        // Wait for computation
        wait_cycles(25);

        // Stream plaintext and check ciphertext
        dout_ready = 1;
        din_valid  = 1;

        for (i = 0; i < 16; i = i + 1) begin
            din_data = plaintext[i];
            @(posedge clk);
            while (dout_valid !== 1'b1) @(posedge clk);
            check_32(dout_data, expected_ct[i], "ciphertext word");
        end

        din_valid  = 0;
        dout_ready = 0;

        wait_cycles(5);
        while (ready !== 1'b1) @(posedge clk);

        // ============================================================
        // TEST 4: Backpressure handling
        // ============================================================
        $display("\n=== TEST 4: Backpressure ===");

        key     = 256'h000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f;
        nonce   = 96'h000000090000004a00000000;
        counter = 32'h00000002;  // Different counter -> different keystream

        start = 1;
        wait_cycles(1);
        start = 0;

        wait_cycles(25);

        // Stream with intermittent backpressure
        dout_ready = 1;
        din_valid  = 1;
        din_data   = 32'h00000000;

        @(posedge clk);
        while (dout_valid !== 1'b1) @(posedge clk);
        // First word should transfer
        $display("[INFO] Backpressure: first word received = 0x%h", dout_data);

        // De-assert ready for 5 cycles (stall)
        dout_ready = 0;
        wait_cycles(5);
        // dout_valid should still be HIGH (holding data)
        if (dout_valid === 1'b1)
            $display("[PASS] Backpressure: dout_valid stays HIGH during stall");
        else begin
            $display("[FAIL] Backpressure: dout_valid dropped during stall");
            fail_count = fail_count + 1;
        end

        // Re-assert ready
        dout_ready = 1;
        @(posedge clk);
        // Should continue streaming

        din_valid  = 0;
        dout_ready = 0;
        wait_cycles(20);

        // ============================================================
        // Summary
        // ============================================================
        $display("\n========================================");
        if (fail_count == 0)
            $display("ALL TESTS PASSED");
        else
            $display("FAILED: %0d assertion(s) failed", fail_count);
        $display("========================================");

        $finish;
    end

    // Timeout watchdog
    initial begin
        #100000;
        $display("[ERROR] Simulation timeout at cycle %0d", cycle_count);
        $finish;
    end

endmodule
