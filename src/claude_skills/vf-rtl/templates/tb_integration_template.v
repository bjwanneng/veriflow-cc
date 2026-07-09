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
    // codegen: replace #5 with HALF-period from spec timing.target_frequency_mhz.
    // half_period_ns = 1000 / (2 * target_frequency_mhz) = CLK_PERIOD_NS / 2.
    // For 100 MHz: full period = 10 ns, half period = 5 ns -> `always #5 clk = ~clk;`.
    always #5 clk = ~clk;

    // Cycle counter — increment every posedge
    always @(posedge clk) cycle_count = cycle_count + 1;

    // VCD capture — REQUIRED for waveform analysis. Suppress with `define NODUMP
    // (the runner passes -DNODUMP when invoked with --no-vcd).
`ifndef NODUMP
    initial begin
        $dumpfile("tb_<design_name>.vcd");
        $dumpvars(0, tb_<design_name>);
    end
`endif

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
    //     // Block 1 (NOT the last):
    //     msg_block <= BLOCK1_DATA;
    //     msg_valid <= 1'b1;
    //     is_last   <= 1'b0;       // MUST be 0 for all non-final blocks
    //     @(posedge clk);          // DUT samples inputs (msg_valid + is_last together)
    //     msg_valid <= 1'b0;
    //     is_last   <= 1'b0;       // hold 0 — never let it float into the gap
    //     // ... wait for block to complete ...
    //     @(posedge clk);          // inter-block gap — DUT FSM returns to IDLE
    //
    //     // Block 2 (the LAST block):
    //     msg_block <= BLOCK2_DATA;
    //     msg_valid <= 1'b1;
    //     is_last   <= 1'b1;       // MUST be 1 at the SAME posedge as msg_valid
    //     @(posedge clk);          // DUT samples both signals here
    //     msg_valid <= 1'b0;
    //     // is_last hold rule: see is_last sub-rule below.
    //
    //   CRITICAL: After a valid pulse, add at least one @(posedge clk) gap
    //   before driving the next block. The DUT FSM needs time to transition
    //   back to IDLE and re-assert ready.
    //
    // Rule 3a: is_last SEMANTICS (CRITICAL — was wrong in SM3 run)
    //   `is_last` is a *per-block* flag co-sampled with `msg_valid`. Strict rules:
    //   - All non-final blocks: `is_last <= 1'b0` at the same posedge as `msg_valid <= 1'b1`.
    //     Never leave is_last at its prior value — always re-drive 0 explicitly.
    //   - The final block: `is_last <= 1'b1` at the same posedge as `msg_valid <= 1'b1`.
    //   - Hold lifetime:
    //       * If the port's `handshake` is `single_cycle` / `pulse`:
    //           Deassert `is_last` together with `msg_valid` at the next posedge.
    //       * If the port's `handshake` is `hold_until_ack`:
    //           Hold `is_last` stable along with `msg_valid` until DUT asserts the
    //           ack/ready confirming the last block was consumed; then deassert
    //           BOTH together at the next posedge.
    //   - `is_last` MUST be driven with `<=` (non-blocking) like all other DUT inputs.
    //   - When the testbench has only ONE block, `is_last <= 1'b1` at the sole
    //     msg_valid posedge. Do not split it into a separate posedge.
    //
    // Rule 4: OUTPUT SAMPLING — posedge vs negedge (CRITICAL — caused SM3 Bug 3)
    //
    //   Two categories of output signals with DIFFERENT sampling rules:
    //
    //   A) PULSE signals (valid_out, ready, done, valid_out):
    //      These are single-cycle pulses. Detect AND sample at the SAME @(posedge clk).
    //      Do NOT insert @(negedge clk) between detection and sampling — the pulse
    //      may be cleared on the next posedge.
    //
    //   B) REGISTERED DATA outputs (result_out, result, data_out):
    //      These are NBA-driven register values. They MUST be sampled at @(negedge clk)
    //      AFTER the posedge where the valid pulse was detected. Reason: at the posedge
    //      where valid_out first appears, the DUT's NBA has just scheduled the new
    //      result_out value but it hasn't propagated through the event queue yet.
    //      Reading result_out at the SAME posedge as valid_out returns the PREVIOUS value.
    //
    //   CORRECT pattern (pulse detection + data sampling):
    //     // Wait for valid pulse at posedge
    //     while (valid_out !== 1'b1) @(posedge clk);
    //     // valid_out is 1 here — detected at posedge ✓
    //     // result_out is STALE here — NBA hasn't settled yet ✗
    //     @(negedge clk);  // wait for NBA to settle on result_out
    //     // result_out now has the correct new value ✓
    //     check_result(expected, "test_name");
    //
    //   WRONG pattern (reads stale result_out):
    //     while (valid_out !== 1'b1) @(posedge clk);
    //     check_result(expected, "test_name");  // result_out = OLD value!
    //
    //   Note: If the data output is purely combinational (assign data_out = data_reg),
    //   a simple #1 delay after posedge also works. But @(negedge clk) is the
    //   universal pattern that works for both registered and combinational outputs.
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
    //
    // Failure log format (parsed by timing_diagnostic.py):
    //   [FAIL] test=<name> cycle=<n> signal=<s> kind=<registered|pulse>
    //          width=<w>b expected=0x<hex> actual=0x<hex> xor=0x<hex> phase=<edge>
    // Keep this format stable — the diagnostic tool relies on it.
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

        // IMPORTANT: When polling for single-cycle pulse signals (valid_out, ready):
        //   - PULSE detection: Detect the signal at posedge in a wait loop
        //   - DATA sampling: Read the guarded data output at @(negedge clk) AFTER
        //     detecting the pulse — this gives NBA time to settle on registered outputs
        //   - Do NOT read data outputs at the same posedge as pulse detection
        //
        // Correct pattern (pulse at posedge, data at negedge):
        //   wait_valid(cycles);   // polls @(posedge clk) until valid_out==1
        //   @(negedge clk);            // wait for NBA to settle on result_out
        //   check_result(expected, ...); // NOW result_out has the correct value
        //
        // Wrong pattern (reads stale data — SM3 Bug 3):
        //   wait_valid(cycles);
        //   check_result(expected, ...); // result_out still has PREVIOUS value!

        // --- Summary ---
        if (fail_count == 0) $display("ALL TESTS PASSED");
        else $display("FAILED: %0d assertion(s) failed", fail_count);
        $finish;
    end
endmodule
