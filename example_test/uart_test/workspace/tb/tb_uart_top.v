`timescale 1ns / 1ps

module tb_uart_top;

    // -------------------------------------------------------
    // Parameters
    // -------------------------------------------------------
    parameter CLK_PERIOD    = 20;        // 50 MHz -> 20 ns
    parameter DIV           = 27;        // baud divider
    parameter OVERSAMPLE    = 16;
    parameter FRAME_BITS    = 10;        // start + 8 data + stop
    parameter FRAME_TICKS   = FRAME_BITS * OVERSAMPLE;  // 160
    parameter FRAME_SYS_CLK = FRAME_TICKS * DIV;         // 4320
    parameter RST_CYCLES    = 100;
    parameter SETUP_CYCLES  = 100;

    // -------------------------------------------------------
    // DUT signals
    // -------------------------------------------------------
    reg         clk;
    reg         rst_n;
    reg  [7:0]  tx_data;
    reg         tx_en;
    wire        uart_txd;
    wire        tx_busy;
    wire        uart_rxd;
    wire [7:0]  rx_data;
    wire        rx_done;
    wire        rx_frame_err;

    // -------------------------------------------------------
    // Loopback: connect TX output to RX input
    // -------------------------------------------------------
    assign uart_rxd = uart_txd;

    // -------------------------------------------------------
    // DUT instantiation
    // -------------------------------------------------------
    uart_top dut (
        .clk          (clk),
        .rst_n        (rst_n),
        .tx_data      (tx_data),
        .tx_en        (tx_en),
        .uart_txd     (uart_txd),
        .tx_busy      (tx_busy),
        .uart_rxd     (uart_rxd),
        .rx_data      (rx_data),
        .rx_done      (rx_done),
        .rx_frame_err (rx_frame_err)
    );

    // -------------------------------------------------------
    // Clock generation
    // -------------------------------------------------------
    initial clk = 0;
    always #(CLK_PERIOD/2) clk = ~clk;

    // -------------------------------------------------------
    // Test bookkeeping
    // -------------------------------------------------------
    integer fail_count;
    integer test_count;

    initial begin
        fail_count = 0;
        test_count = 0;
    end

    // -------------------------------------------------------
    // Waveform dump
    // -------------------------------------------------------
    initial begin
        $dumpfile("tb_uart_top.vcd");
        $dumpvars(0, tb_uart_top);
    end

    // -------------------------------------------------------
    // Helper tasks
    // -------------------------------------------------------
    task reset_dut;
        begin
            rst_n   = 0;
            tx_data = 8'h00;
            tx_en   = 0;
            repeat(RST_CYCLES) @(posedge clk);
            rst_n = 1;
            repeat(SETUP_CYCLES) @(posedge clk);
        end
    endtask

    task send_byte;
        input [7:0] data;
        begin
            @(posedge clk);
            tx_data = data;
            tx_en   = 1;
            @(posedge clk);
            tx_en   = 0;
        end
    endtask

    task wait_for_rx_done;
        input integer max_wait;
        integer waited;
        begin
            waited = 0;
            while (rx_done === 0 && waited < max_wait) begin
                @(posedge clk);
                waited = waited + 1;
            end
            if (waited >= max_wait) begin
                $display("[FAIL] rx_done timeout after %0d cycles", max_wait);
                fail_count = fail_count + 1;
            end
        end
    endtask

    task check_rx;
        input [7:0] expected;
        input        expect_err;
        begin
            test_count = test_count + 1;
            // Wait for rx_done with generous margin
            wait_for_rx_done(FRAME_SYS_CLK + 500);
            if (rx_done === 1) begin
                if (rx_data !== expected) begin
                    $display("[FAIL] Test %0d: rx_data=0x%02h, expected=0x%02h",
                             test_count, rx_data, expected);
                    fail_count = fail_count + 1;
                end else if (rx_frame_err !== expect_err) begin
                    $display("[FAIL] Test %0d: rx_frame_err=%0b, expected=%0b (data=0x%02h)",
                             test_count, rx_frame_err, expect_err, expected);
                    fail_count = fail_count + 1;
                end else begin
                    $display("[PASS] Test %0d: loopback 0x%02h OK, frame_err=%0b",
                             test_count, expected, expect_err);
                end
            end
            // Small gap between frames
            repeat(100) @(posedge clk);
        end
    endtask

    // -------------------------------------------------------
    // Main test sequence
    // -------------------------------------------------------
    initial begin
        // Scenario 1: Reset behavior
        $display("--- Scenario 1: Reset behavior ---");
        reset_dut;
        test_count = test_count + 1;
        if (uart_txd !== 1'b1) begin
            $display("[FAIL] Test %0d: uart_txd not 1 after reset", test_count);
            fail_count = fail_count + 1;
        end else if (tx_busy !== 1'b0) begin
            $display("[FAIL] Test %0d: tx_busy not 0 after reset", test_count);
            fail_count = fail_count + 1;
        end else if (rx_done !== 1'b0) begin
            $display("[FAIL] Test %0d: rx_done not 0 after reset", test_count);
            fail_count = fail_count + 1;
        end else if (rx_frame_err !== 1'b0) begin
            $display("[FAIL] Test %0d: rx_frame_err not 0 after reset", test_count);
            fail_count = fail_count + 1;
        end else begin
            $display("[PASS] Test %0d: Reset outputs correct", test_count);
        end

        // Scenario 2: Loopback 0xA5
        $display("--- Scenario 2: Loopback 0xA5 ---");
        send_byte(8'hA5);
        check_rx(8'hA5, 1'b0);

        // Scenario 3: Loopback 0x3C
        $display("--- Scenario 3: Loopback 0x3C ---");
        send_byte(8'h3C);
        check_rx(8'h3C, 1'b0);

        // Scenario 4: Loopback 0xFF (all ones)
        $display("--- Scenario 4: Loopback 0xFF ---");
        send_byte(8'hFF);
        check_rx(8'hFF, 1'b0);

        // Scenario 5: Loopback 0x00 (all zeros)
        $display("--- Scenario 5: Loopback 0x00 ---");
        send_byte(8'h00);
        check_rx(8'h00, 1'b0);

        // Scenario 6: tx_busy flag
        $display("--- Scenario 6: tx_busy flag ---");
        test_count = test_count + 1;
        send_byte(8'h55);
        // tx_busy should be asserted shortly after tx_en
        repeat(10) @(posedge clk);
        if (tx_busy !== 1'b1) begin
            $display("[FAIL] Test %0d: tx_busy not asserted during TX", test_count);
            fail_count = fail_count + 1;
        end else begin
            $display("[PASS] Test %0d: tx_busy asserted during TX", test_count);
        end
        // Wait for TX to complete
        repeat(FRAME_SYS_CLK) @(posedge clk);
        repeat(100) @(posedge clk);
        if (tx_busy !== 1'b0) begin
            $display("[FAIL] Test %0d: tx_busy still asserted after frame complete", test_count);
            fail_count = fail_count + 1;
        end else begin
            $display("[PASS] Test %0d: tx_busy deasserted after TX complete", test_count);
        end
        // RX completes simultaneously with TX (loopback) — frame already received
        repeat(100) @(posedge clk);

        // Scenario 7: Multiple frames back-to-back
        $display("--- Scenario 7: Multiple frames ---");
        send_byte(8'hA5);
        check_rx(8'hA5, 1'b0);
        send_byte(8'h55);
        check_rx(8'h55, 1'b0);

        // ---------------------------------------------------
        // Final report
        // ---------------------------------------------------
        $display("");
        $display("========================================");
        if (fail_count == 0)
            $display("ALL TESTS PASSED (%0d tests)", test_count);
        else
            $display("FAILED: %0d of %0d assertion(s) failed", fail_count, test_count);
        $display("========================================");
        $finish;
    end

    // Timeout watchdog
    initial begin
        #(CLK_PERIOD * (FRAME_SYS_CLK * 10 + 100000));
        $display("[ERROR] Simulation timeout!");
        $finish;
    end

endmodule
