// tb_<design_name>.v — integration test for <design_name>
module tb_<design_name>;
    // Declare wires/regs matching ALL ports of the top module DUT
    reg clk, rst;
    reg [31:0] data_in;
    wire [31:0] data_out;
    wire ready;

    // Cycle counter — used in ALL $display calls for waveform correlation
    integer cycle_count = 0;
    integer fail_count  = 0;

    // Instantiate DUT (top module — submodules are linked via RTL files)
    <design_name> uut (
        .clk(clk), .rst(rst),
        .data_in(data_in), .data_out(data_out), .ready(ready)
    );

    // Clock generation
    initial clk = 0;
    // codegen: replace #5 with half-period from spec timing.target_frequency_mhz
    always #5 clk = ~clk;

    // Cycle counter — increment every posedge
    always @(posedge clk) cycle_count = cycle_count + 1;

    // VCD capture — REQUIRED for waveform analysis
    initial begin
        $dumpfile("tb_<design_name>.vcd");
        $dumpvars(0, tb_<design_name>);
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
    //   CORRECT:
    //     msg_block <= 512'h...;
    //     msg_valid <= 1'b1;
    //     @(posedge clk);
    //
    //   WRONG (blocking assignment to DUT input — race condition):
    //     msg_block = 512'h...;
    //     msg_valid = 1'b1;
    //     @(posedge clk);
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
    // Rule 3: MULTI-BLOCK/MESSAGE SENDING PATTERN
    //   When sending multiple blocks to a processing core:
    //     // Block 1:
    //     msg_block <= BLOCK1_DATA;
    //     msg_valid <= 1'b1;
    //     is_last   <= 1'b0;
    //     @(posedge clk);          // DUT samples inputs
    //     msg_valid <= 1'b0;
    //     // ... wait for block to complete ...
    //     @(posedge clk);          // inter-block gap — DUT FSM returns to IDLE
    //
    //     // Block 2:
    //     msg_block <= BLOCK2_DATA;
    //     msg_valid <= 1'b1;
    //     is_last   <= 1'b1;
    //     @(posedge clk);
    //     ...
    //
    //   CRITICAL: After a valid pulse, add at least one @(posedge clk) gap
    //   before driving the next block. The DUT FSM needs time to transition
    //   back to IDLE and re-assert ready.
    //
    // Rule 4: OUTPUT SAMPLING — posedge vs negedge
    //   - Registered outputs (most outputs): sample at @(negedge clk) AFTER
    //     the @(posedge clk) where the output is expected. The negedge gives
    //     NBA region time to apply new register values.
    //   - Single-cycle pulse signals (hash_valid, ready, done): sample at
    //     the SAME @(posedge clk) where detection occurs. Do NOT insert
    //     @(negedge clk) between detection and sampling. (See Rule 5 below.)
    //
    // Rule 5: TIMING CONTRACT QUICK REFERENCE
    //   When spec.json timing_contract shows:
    //     same_cycle_visible=false, pipeline_delay_cycles=1
    //     → Consumer sees NEW value one posedge AFTER producer writes it.
    //       Insert one @(posedge clk) between driving and checking.
    //     same_cycle_visible=true, pipeline_delay_cycles=0
    //     → Consumer sees value immediately. Check on the same posedge.
    //
    // Rule 6: DATA INPUT HOLD TIME (CRITICAL — prevents hash mismatches)
    //   Data inputs must remain stable until the DUT has sampled them.
    //   If the control signal that triggers sampling has pipeline_delay_cycles=N
    //   in the timing_contract, keep data inputs stable for N+1 cycles AFTER
    //   deasserting valid. Do NOT clear msg_block immediately with msg_valid.
    //
    //   CORRECT (N=1, e.g. registered FSM → combinational datapath):
    //     msg_block <= BLOCK_DATA;
    //     msg_valid <= 1'b1;
    //     @(posedge clk);          // handshake posedge
    //     msg_valid <= 1'b0;
    //     @(posedge clk);          // wait for load_en to propagate
    //     msg_block <= 512'd0;     // NOW safe to clear
    //
    //   WRONG (data cleared before consumer sees load_en):
    //     msg_block <= BLOCK_DATA;
    //     msg_valid <= 1'b1;
    //     @(posedge clk);
    //     msg_valid <= 1'b0;
    //     msg_block <= 512'd0;     // BUG: cleared one cycle too early!
    //
    // ===========================================================================

    // ===========================================================================
    // MACROS: Race-free sampling helpers
    // ===========================================================================
    // Use these macros instead of raw @(negedge clk) to avoid race conditions.
    `define SAMPLE_REGISTERED_OUTPUT(sig, expected, test_name) \
        @(negedge clk); \
        if (sig !== expected) begin \
            $display("[FAIL] test=%s cycle=%0d signal=%s expected=0x%0h actual=0x%0h phase=negedge", \
                     test_name, cycle_count, `"sig`", expected, sig); \
            fail_count = fail_count + 1; \
        end else \
            $display("[PASS] test=%s cycle=%0d signal=%s actual=0x%0h phase=negedge", \
                     test_name, cycle_count, `"sig`", sig);

    `define SAMPLE_PULSE_OUTPUT(sig, expected, test_name) \
        if (sig !== expected) begin \
            $display("[FAIL] test=%s cycle=%0d signal=%s expected=0x%0h actual=0x%0h phase=posedge", \
                     test_name, cycle_count, `"sig`", expected, sig); \
            fail_count = fail_count + 1; \
        end else \
            $display("[PASS] test=%s cycle=%0d signal=%s actual=0x%0h phase=posedge", \
                     test_name, cycle_count, `"sig`", sig);

    // ===========================================================================
    // RESET TASK: Must be called at start of EVERY independent test
    // ===========================================================================
    task automatic apply_reset;
        begin
            rst = 1;
            data_in <= 0;  // zero all data inputs with NBA
            @(posedge clk); @(posedge clk); @(posedge clk);
            rst = 0;
            @(negedge clk);  // wait for NBA to settle after rst deassert
            $display("[TRACE] cycle=%0d rst released", cycle_count);
        end
    endtask

    // ===========================================================================
    // Test cases
    // ===========================================================================
    initial begin
        // --- Test case 1: <description> ---
        apply_reset();
        data_in <= 32'h0000_1234;
        @(posedge clk);   // DUT samples data_in
        `SAMPLE_REGISTERED_OUTPUT(data_out, 32'hEXPECTED, "test1")

        // --- Test case 2: multi-cycle operation with valid/ready handshake ---
        // CRITICAL: Call apply_reset() before EVERY independent test to prevent
        // state accumulation (e.g., hash chaining variables retaining stale values).
        apply_reset();

        // IMPORTANT: When polling for single-cycle pulse signals (hash_valid, ready):
        //   - Detect the signal at posedge in a wait loop
        //   - Check output IMMEDIATELY after wait returns — NO @(negedge clk) delay
        //   - The pulse signal is cleared on the next posedge, so any delay misses it
        //
        // Correct pattern:
        //   wait_hash_valid(cycles);   // polls @(posedge clk) until hash_valid==1
        //   check_hash(expected, ...); // reads hash_out at SAME posedge — no delay!
        //
        // Wrong pattern:
        //   wait_hash_valid(cycles);
        //   @(negedge clk);            // BUG: hash_valid already cleared!
        //   check_hash(expected, ...); // sees hash_valid=0

        // --- Summary ---
        if (fail_count == 0) $display("ALL TESTS PASSED");
        else $display("FAILED: %0d assertion(s) failed", fail_count);
        $finish;
    end
endmodule
