// tb_resnet_basic_block.v — integration test for resnet_basic_block
module tb_resnet_basic_block;
    // Declare wires/regs matching ALL ports of the top module DUT
    reg clk, rst;
    reg in_valid_i;
    reg [7:0] in_data_i;
    wire out_valid_o;
    wire [7:0] out_data_o;

    // Cycle counter — used in ALL $display calls for waveform correlation
    integer cycle_count = 0;
    integer fail_count  = 0;

    // Instantiate DUT (top module — submodules are linked via RTL files)
    resnet_basic_block #(
        .WIDTH(4),
        .HEIGHT(4),
        .CHANNELS(1)
    ) uut (
        .clk(clk),
        .rst(rst),
        .in_valid_i(in_valid_i),
        .in_data_i(in_data_i),
        .out_valid_o(out_valid_o),
        .out_data_o(out_data_o)
    );

    // Clock generation: 200 MHz -> 5 ns period -> 2.5 ns half period
    initial clk = 0;
    always #2.5 clk = ~clk;

    // Cycle counter — increment every posedge
    always @(posedge clk) cycle_count = cycle_count + 1;

    // VCD capture — REQUIRED for waveform analysis
    initial begin
        $dumpfile("tb_resnet_basic_block.vcd");
        $dumpvars(0, tb_resnet_basic_block);
    end

    // ===========================================================================
    // TESTBENCH TIMING METHODOLOGY — Read Before Modifying This Testbench
    // ===========================================================================
    //
    // Rule 1: NBA FOR DUT INPUTS (MANDATORY)
    //   All DUT input assignments in initial blocks MUST use non-blocking
    //   assignment (<=). This prevents race conditions between the testbench
    //   and the DUT's sequential always blocks at the same posedge.
    //
    //   Exception: Reset signal (rst/rst_n) MAY use blocking (=) in the
    //   dedicated reset sequence only. All other DUT inputs: use <= .
    //
    // Rule 2: RESET SEQUENCE TIMING
    //   Standard pattern:
    //     rst = 1;                          // blocking OK for reset only
    //     <zero all data inputs with <=>
    //     @(posedge clk); @(posedge clk);   // hold reset 2 cycles
    //     rst = 0;                          // blocking OK for reset only
    //     @(negedge clk);                   // wait for NBA region to settle
    //     // Now all DUT registers have their reset values
    //
    // Rule 4: OUTPUT SAMPLING — posedge vs negedge (CRITICAL)
    //
    //   A) PULSE signals (valid_out, ready, done):
    //      Detect AND sample at the SAME @(posedge clk).
    //
    //   B) REGISTERED DATA outputs (result_out, result, data_out):
    //      Sample at @(negedge clk) AFTER the posedge where the valid pulse
    //      was detected. Reason: at the posedge where valid_out first appears,
    //      the DUT's NBA has just scheduled the new result_out value but it
    //      hasn't propagated through the event queue yet.
    //
    //   CORRECT pattern:
    //     while (valid_out !== 1'b1) @(posedge clk);
    //     @(negedge clk);  // wait for NBA to settle on result_out
    //     check_result(expected, "test_name");
    //
    // ===========================================================================

    // ===========================================================================
    // MACROS: Race-free sampling helpers
    // ===========================================================================
    `define SAMPLE_REGISTERED_OUTPUT(sig, expected, test_name) \
        @(negedge clk); \
        if (sig !== expected) begin \
            $display("[FAIL] test=%s cycle=%0d signal=%s kind=registered width=%0db expected=0x%0h actual=0x%0h xor=0x%0h phase=negedge", \
                     test_name, cycle_count, `"sig`", $bits(sig), expected, sig, (expected ^ sig)); \
            fail_count = fail_count + 1; \
        end else \
            $display("[PASS] test=%s cycle=%0d signal=%s kind=registered width=%0db actual=0x%0h phase=negedge", \
                     test_name, cycle_count, `"sig`", $bits(sig), sig);

    `define SAMPLE_PULSE_OUTPUT(sig, expected, test_name) \
        if (sig !== expected) begin \
            $display("[FAIL] test=%s cycle=%0d signal=%s kind=pulse width=%0db expected=0x%0h actual=0x%0h xor=0x%0h phase=posedge", \
                     test_name, cycle_count, `"sig`", $bits(sig), expected, sig, (expected ^ sig)); \
            fail_count = fail_count + 1; \
        end else \
            $display("[PASS] test=%s cycle=%0d signal=%s kind=pulse width=%0db actual=0x%0h phase=posedge", \
                     test_name, cycle_count, `"sig`", $bits(sig), sig);

    // ===========================================================================
    // RESET TASK: Must be called at start of EVERY independent test
    // ===========================================================================
    task automatic apply_reset;
        begin
            rst = 1;
            in_valid_i <= 0;
            in_data_i  <= 0;
            @(posedge clk); @(posedge clk); @(posedge clk);
            rst = 0;
            @(negedge clk);
            $display("[TRACE] cycle=%0d rst released", cycle_count);
        end
    endtask

    // ===========================================================================
    // Test cases
    // ===========================================================================
    initial begin
        integer i;
        integer pixels_driven;
        integer outputs_received;
        integer expected_idx;

        // Expected output values from golden model:
        // resnet_basic_block(INPUT_4X4) = [[96,127,127,114],[127,127,127,127],[127,127,127,127],[108,127,127,106]]
        reg [7:0] expected_output [0:15];
        expected_output[0]  = 8'd96;
        expected_output[1]  = 8'd127;
        expected_output[2]  = 8'd127;
        expected_output[3]  = 8'd114;
        expected_output[4]  = 8'd127;
        expected_output[5]  = 8'd127;
        expected_output[6]  = 8'd127;
        expected_output[7]  = 8'd127;
        expected_output[8]  = 8'd127;
        expected_output[9]  = 8'd127;
        expected_output[10] = 8'd127;
        expected_output[11] = 8'd127;
        expected_output[12] = 8'd108;
        expected_output[13] = 8'd127;
        expected_output[14] = 8'd127;
        expected_output[15] = 8'd106;

        // Input pixels: [1,2,3,4,5,6,7,8,9,0,1,2,3,4,5,6]
        reg [7:0] input_pixels [0:15];
        input_pixels[0]  = 8'd1;
        input_pixels[1]  = 8'd2;
        input_pixels[2]  = 8'd3;
        input_pixels[3]  = 8'd4;
        input_pixels[4]  = 8'd5;
        input_pixels[5]  = 8'd6;
        input_pixels[6]  = 8'd7;
        input_pixels[7]  = 8'd8;
        input_pixels[8]  = 8'd9;
        input_pixels[9]  = 8'd0;
        input_pixels[10] = 8'd1;
        input_pixels[11] = 8'd2;
        input_pixels[12] = 8'd3;
        input_pixels[13] = 8'd4;
        input_pixels[14] = 8'd5;
        input_pixels[15] = 8'd6;

        // --- Test case 1: Reset behavior ---
        apply_reset();
        // After reset, outputs should be 0
        if (out_valid_o !== 1'b0) begin
            $display("[FAIL] test=reset_check cycle=%0d signal=out_valid_o expected=0 actual=%b", cycle_count, out_valid_o);
            fail_count = fail_count + 1;
        end
        if (out_data_o !== 8'd0) begin
            $display("[FAIL] test=reset_check cycle=%0d signal=out_data_o expected=0 actual=%0d", cycle_count, out_data_o);
            fail_count = fail_count + 1;
        end
        $display("[PASS] test=reset_check outputs are 0 after reset");

        // --- Test case 2: Drive 16 input pixels and check outputs ---
        apply_reset();

        pixels_driven = 0;
        outputs_received = 0;
        expected_idx = 0;

        // Drive all 16 input pixels, one per cycle
        for (i = 0; i < 16; i = i + 1) begin
            in_valid_i <= 1'b1;
            in_data_i  <= input_pixels[i];
            @(posedge clk);
            pixels_driven = pixels_driven + 1;
        end

        // Deassert valid after last pixel
        in_valid_i <= 1'b0;
        in_data_i  <= 8'd0;

        // Wait for out_valid_o to assert and collect outputs
        // We expect 16 output pixels (4x4 output feature map)
        while (outputs_received < 16) begin
            @(posedge clk);
            if (out_valid_o === 1'b1) begin
                // Detected valid pulse at posedge
                // Sample registered data at negedge after detecting valid
                @(negedge clk);
                `SAMPLE_REGISTERED_OUTPUT(out_data_o, expected_output[expected_idx], "resnet_output")
                expected_idx = expected_idx + 1;
                outputs_received = outputs_received + 1;
            end
        end

        $display("[INFO] Pixels driven: %0d, Outputs received: %0d", pixels_driven, outputs_received);

        // --- Summary ---
        if (fail_count == 0) $display("ALL TESTS PASSED");
        else $display("FAILED: %0d assertion(s) failed", fail_count);
        $finish;
    end
endmodule
