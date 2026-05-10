`timescale 1ns / 1ps

/**
 * Testbench for sm3_core module
 *
 * This testbench verifies the SM3 hash implementation using test vectors.
 * It respects the input hold time requirement from spec.json timing contracts.
 *
 * Timing Contract Analysis:
 * - All control signal connections have pipeline_delay_cycles = 0
 * - max_pipeline_delay = 0
 * - Minimum input hold time = max_pipeline_delay + 1 = 1 cycle
 * - Data inputs (msg_block) must remain stable for at least 1 cycle after valid pulse
 */

module tb_sm3_core;

    // Testbench parameters
    localparam CLK_PERIOD = 2;  // 2ns = 500 MHz
    localparam MAX_CYCLES = 1000;

    // DUT signals
    reg clk;
    reg rst;
    reg msg_valid;
    reg [511:0] msg_block;
    reg is_last;
    wire ready;
    wire hash_valid;
    wire [255:0] hash_out;

    // Test control
    integer test_passed;
    integer test_failed;
    integer cycle_count;
    reg [255:0] temp_hash;

    // Instantiate DUT
    sm3_core u_dut (
        .clk(clk),
        .rst(rst),
        .msg_valid(msg_valid),
        .msg_block(msg_block),
        .is_last(is_last),
        .ready(ready),
        .hash_valid(hash_valid),
        .hash_out(hash_out)
    );

    // Clock generation
    initial begin
        clk = 0;
        forever #(CLK_PERIOD/2) clk = ~clk;
    end

    // Reset task
    task reset_dut;
        begin
            rst = 1;
            #(CLK_PERIOD * 5);
            rst = 0;
            #(CLK_PERIOD * 2);
        end
    endtask

    // Wait for ready task
    task wait_for_ready;
        begin
            cycle_count = 0;
            while (ready !== 1'b1 && cycle_count < MAX_CYCLES) begin
                @(posedge clk);
                cycle_count = cycle_count + 1;
            end
            if (cycle_count >= MAX_CYCLES) begin
                $display("[ERROR] Timeout waiting for ready!");
                $finish;
            end
        end
    endtask

    // Send block task
    // IMPORTANT: msg_block must remain stable for at least 1 cycle after msg_valid deassertion
    task send_block;
        input [511:0] block_upper;
        input [511:0] block_lower;
        input is_last_block;
        begin
            // Wait for ready
            wait_for_ready();

            // Drive inputs
            msg_block = {block_upper, block_lower};
            is_last = is_last_block;
            msg_valid = 1'b1;

            // Hold for 1 cycle (min hold time = max_pipeline_delay + 1 = 0 + 1 = 1)
            @(posedge clk);

            // Deassert valid but keep data stable for 1 more cycle
            msg_valid = 1'b0;
            @(posedge clk);
        end
    endtask

    // Wait for hash_valid and read hash
    task get_hash;
        output [255:0] hash_result;
        begin
            cycle_count = 0;
            while (hash_valid !== 1'b1 && cycle_count < MAX_CYCLES) begin
                @(posedge clk);
                cycle_count = cycle_count + 1;
            end
            if (cycle_count >= MAX_CYCLES) begin
                $display("[ERROR] Timeout waiting for hash_valid!");
                $finish;
            end
            hash_result = hash_out;
        end
    endtask

    // Compare hash task
    task compare_hash;
        input [255:0] actual;
        input [255:0] expected;
        input [319:0] test_name;  // 40 chars
        begin
            $display("Test: %s", test_name);
            $display("  Expected hash: 0x%064h", expected);
            $display("  Got hash     : 0x%064h", actual);

            if (actual === expected) begin
                $display("  Status: PASS");
                test_passed = test_passed + 1;
            end else begin
                $display("  Status: FAIL");
                test_failed = test_failed + 1;
            end
            $display("");
        end
    endtask

    // Main test sequence
    initial begin
        // Initialize signals
        msg_valid = 0;
        msg_block = 512'h0;
        is_last = 0;
        test_passed = 0;
        test_failed = 0;

        $display("========================================");
        $display("SM3 Core Testbench");
        $display("========================================");
        $display("");

        // Test 1: "abc"
        reset_dut();
        send_block(512'h6162638000000000000000000000000000000000000000000000000000000000,
                   512'h0000000000000000000000000000000000000000000000000000000000000018,
                   1'b1);

        // Expected hash for "abc": 0x66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0
        begin
            get_hash(temp_hash);
            compare_hash(temp_hash,
                        256'h66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0,
                        "abc");
        end

        // Test 2: 16 bytes "abcd" * 4
        reset_dut();
        // Padded block for 16-byte message
        send_block(512'h616263646162636461626364616263648000000000000000000000000000000,
                   512'h0000000000000000000000000000000000000000000000000000000000000080,
                   1'b1);

        // Expected hash: 0x639c6f6b30d93ecebd559a953ba2eb72705db7d2be82bbf32979380e02124971
        begin
            get_hash(temp_hash);
            compare_hash(temp_hash,
                        256'h639c6f6b30d93ecebd559a953ba2eb72705db7d2be82bbf32979380e02124971,
                        "16_bytes_abcd*4");
        end

        // Test 3: 32 bytes "abcd" * 8 (one 512-bit block after padding)
        reset_dut();
        send_block(512'h6162636461626364616263646162636461626364616263646162636461626364,
                   512'h8000000000000000000000000000000000000000000000000000000000000100,
                   1'b1);

        // Expected hash: 0x73edef5c9d3710f14dbaf892f50ce9dfab48e462d837d93ec0f9422c5f2a4007
        begin
            get_hash(temp_hash);
            compare_hash(temp_hash,
                        256'h73edef5c9d3710f14dbaf892f50ce9dfab48e462d837d93ec0f9422c5f2a4007,
                        "32_bytes_one_block");
        end

        // Test 4: 64 bytes "abcd" * 16 (two 512-bit blocks after padding)
        reset_dut();
        // First block
        send_block(512'h616263646162636461626364616263646162636461626364616263646461626364,
                   512'h6162636461626364616263646162636461626364616263646162636461626364,
                   1'b0);
        // Second block
        send_block(512'h8000000000000000000000000000000000000000000000000000000000000000,
                   512'h0000000000000000000000000000000000000000000000000000000000000200,
                   1'b1);

        // Expected hash: 0xdebe9ff92275b8a138604889c18e5a4d6fdb70e5387e5765293dcba39c0c5732
        begin
            get_hash(temp_hash);
            compare_hash(temp_hash,
                        256'hdebe9ff92275b8a138604889c18e5a4d6fdb70e5387e5765293dcba39c0c5732,
                        "64_bytes_two_blocks");
        end

        // Summary
        $display("========================================");
        $display("Test Summary");
        $display("========================================");
        $display("Passed: %0d", test_passed);
        $display("Failed: %0d", test_failed);
        $display("========================================");

        if (test_failed > 0) begin
            $display("[ERROR] Some tests failed!");
            $finish(1);
        end else begin
            $display("[SUCCESS] All tests passed!");
            $finish(0);
        end
    end

    // Timeout watchdog
    initial begin
        #(CLK_PERIOD * 100000);  // 200,000 ns timeout
        $display("[ERROR] Simulation timeout!");
        $finish(1);
    end

endmodule
