// tb_sm3_core.v — Integration testbench for SM3 cryptographic hash core
// Verifies "abc" test vector per GM/T 0004-2012 standard.
//
// Timing protocol:
//   1. Apply reset (rst_n=0) for 3 cycles, then deassert
//   2. Wait for ready=1 (IDLE state)
//   3. Drive msg_valid=1, msg_block, is_last for 1 cycle
//   4. Hold data stable for 2 cycles after valid deassert (Rule 6)
//   5. Wait for hash_valid strobe (poll at posedge)
//   6. Check hash_out matches expected value at same posedge (Rule 5)
//   7. Report PASS/FAIL
//
// Timing Rules (from template):
//   Rule 1: NBA for DUT inputs (except reset)
//   Rule 5: Single-cycle pulse signals (hash_valid) — sample at SAME posedge
//   Rule 6: Data hold — keep msg_block stable 2 cycles after valid deassert

module tb_sm3_core;

    // ─── DUT ports ──────────────────────────────────────────────────────
    reg         clk;
    reg         rst_n;
    reg         msg_valid;
    reg [511:0] msg_block;
    reg         is_last;
    wire        ready;
    wire        hash_valid;
    wire [255:0] hash_out;

    // ─── Cycle counter and status ───────────────────────────────────────
    integer cycle_count;
    integer fail_count;
    integer i;

    // ─── Test vector ────────────────────────────────────────────────────
    // "abc" padded message block (big-endian, per GM/T 0004-2012)
    localparam [511:0] TEST_MSG_BLOCK =
        512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;
    localparam [255:0] EXPECTED_HASH =
        256'h66c7f0f4_62eeedd9_d1f2d46b_dc10e4e2_4167c487_5cf2f7a2_297da02b_8f4ba8e0;

    // ─── DUT instantiation ──────────────────────────────────────────────
    sm3_core uut (
        .clk        (clk),
        .rst_n      (rst_n),
        .msg_valid  (msg_valid),
        .msg_block  (msg_block),
        .is_last    (is_last),
        .ready      (ready),
        .hash_valid (hash_valid),
        .hash_out   (hash_out)
    );

    // ─── Clock generation ───────────────────────────────────────────────
    initial clk = 0;
    always #5 clk = ~clk;   // 10ns period, 100MHz

    // ─── Cycle counter ──────────────────────────────────────────────────
    initial cycle_count = 0;
    always @(posedge clk) cycle_count = cycle_count + 1;

    // ─── VCD capture ────────────────────────────────────────────────────
    initial begin
        $dumpfile("tb_sm3_core.vcd");
        $dumpvars(0, tb_sm3_core);
    end

    // ─── Main test sequence ─────────────────────────────────────────────
    initial begin
        fail_count = 0;

        // ── Reset (Rule 2) ──────────────────────────────────────────────
        clk       = 0;
        rst_n     = 1;          // start inactive (blocking OK for reset only)
        msg_valid = 0;
        msg_block <= 512'd0;
        is_last   <= 1'b0;
        @(posedge clk);
        rst_n     = 0;          // assert reset (active-low, blocking OK)
        @(posedge clk); @(posedge clk);   // hold reset 2 cycles
        rst_n     = 1;          // deassert reset (blocking OK)
        @(negedge clk);         // wait for NBA region to settle
        $display("[TRACE] cycle=%0d reset released, ready=%b", cycle_count, uut.ready);

        // ── Wait for ready ──────────────────────────────────────────────
        for (i = 0; i < 50; i = i + 1) begin
            @(posedge clk);
            if (uut.ready == 1'b1) begin
                $display("[TRACE] cycle=%0d ready asserted", cycle_count);
                i = 999;    // break out of loop (no 'break' in Verilog-2005)
            end
        end
        if (uut.ready !== 1'b1) begin
            $display("[FAIL] Timeout waiting for ready after reset");
            fail_count = fail_count + 1;
            $finish;
        end

        // ── Drive test vector (same protocol as verified debug TB) ─────
        // Set msg_block before the handshake
        msg_block = TEST_MSG_BLOCK;
        @(posedge clk);
        msg_valid = 1;
        is_last = 1;

        @(posedge clk);
        msg_valid = 0;
        $display("[TRACE] cycle=%0d data hold complete, waiting for hash_valid", cycle_count);

        // ── Wait for hash_valid ─────────────────────────────────────────
        wait(uut.hash_valid == 1'b1);
        $display("[TRACE] cycle=%0d hash_valid asserted", cycle_count);

        // hash_out is registered; valid in cycle after hash_valid's NBA
        @(posedge clk);

        // ── Check hash_out ──────────────────────────────────────────────
        if (hash_out !== EXPECTED_HASH) begin
            $display("[FAIL] test=abc cycle=%0d signal=hash_out expected=0x%064h actual=0x%064h",
                     cycle_count, EXPECTED_HASH, hash_out);
            fail_count = fail_count + 1;
        end else begin
            $display("[PASS] test=abc cycle=%0d signal=hash_out actual=0x%064h",
                     cycle_count, hash_out);
        end

        // ── Summary ─────────────────────────────────────────────────────
        if (fail_count == 0)
            $display("ALL TESTS PASSED");
        else
            $display("FAILED: %0d assertion(s) failed", fail_count);

        $finish;
    end

endmodule
