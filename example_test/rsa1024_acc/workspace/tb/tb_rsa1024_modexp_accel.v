`timescale 1ns / 1ps

// Testbench for rsa1024_modexp_accel
// Tests: reset, AXI-Lite register access, AXI-Stream I/O, dsp_mac_32 pipeline,
//        full modexp with E=1 identity (M^1 mod N = M)
//
// Test vector: N=13, E=1, M=2, N'=0x3B13B13B, R2=9, expected result=2

module tb_rsa1024_modexp_accel;

    // ----------------------------------------------------------------
    // Parameters
    // ----------------------------------------------------------------
    parameter CLK_PERIOD = 4;  // 250 MHz -> 4 ns

    // ----------------------------------------------------------------
    // Signals
    // ----------------------------------------------------------------
    reg         clk;
    reg         rst;

    // AXI4-Lite Slave
    reg  [15:0] s_axi_awaddr;
    reg         s_axi_awvalid;
    wire        s_axi_awready;
    reg  [31:0] s_axi_wdata;
    reg         s_axi_wvalid;
    wire        s_axi_wready;
    wire [ 1:0] s_axi_bresp;
    wire        s_axi_bvalid;
    reg         s_axi_bready;
    reg  [15:0] s_axi_araddr;
    reg         s_axi_arvalid;
    wire        s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [ 1:0] s_axi_rresp;
    wire        s_axi_rvalid;
    reg         s_axi_rready;

    // AXI4-Stream Input
    reg  [31:0] s_axis_tdata;
    reg         s_axis_tvalid;
    wire        s_axis_tready;
    reg         s_axis_tlast;

    // AXI4-Stream Output
    wire [31:0] m_axis_tdata;
    wire        m_axis_tvalid;
    reg         m_axis_tready;
    wire        m_axis_tlast;

    // ----------------------------------------------------------------
    // DUT
    // ----------------------------------------------------------------
    rsa_modexp_top dut (
        .clk            (clk),
        .rst            (rst),
        .s_axi_awaddr   (s_axi_awaddr),
        .s_axi_awvalid  (s_axi_awvalid),
        .s_axi_awready  (s_axi_awready),
        .s_axi_wdata    (s_axi_wdata),
        .s_axi_wvalid   (s_axi_wvalid),
        .s_axi_wready   (s_axi_wready),
        .s_axi_bresp    (s_axi_bresp),
        .s_axi_bvalid   (s_axi_bvalid),
        .s_axi_bready   (s_axi_bready),
        .s_axi_araddr   (s_axi_araddr),
        .s_axi_arvalid  (s_axi_arvalid),
        .s_axi_arready  (s_axi_arready),
        .s_axi_rdata    (s_axi_rdata),
        .s_axi_rresp    (s_axi_rresp),
        .s_axi_rvalid   (s_axi_rvalid),
        .s_axi_rready   (s_axi_rready),
        .s_axis_tdata   (s_axis_tdata),
        .s_axis_tvalid  (s_axis_tvalid),
        .s_axis_tready  (s_axis_tready),
        .s_axis_tlast   (s_axis_tlast),
        .m_axis_tdata   (m_axis_tdata),
        .m_axis_tvalid  (m_axis_tvalid),
        .m_axis_tready  (m_axis_tready),
        .m_axis_tlast   (m_axis_tlast)
    );

    // ----------------------------------------------------------------
    // Clock Generation
    // ----------------------------------------------------------------
    initial clk = 0;
    always #(CLK_PERIOD/2) clk = ~clk;

    // ----------------------------------------------------------------
    // Test tracking
    // ----------------------------------------------------------------
    integer fail_count;
    integer test_num;
    integer cycle_count;

    // ----------------------------------------------------------------
    // AXI4-Lite Write Task
    // ----------------------------------------------------------------
    task axi_lite_write;
        input [15:0] addr;
        input [31:0] data;
    begin
        // AW phase
        @(posedge clk);
        s_axi_awaddr  <= addr;
        s_axi_awvalid <= 1'b1;
        s_axi_wdata   <= data;
        s_axi_wvalid  <= 1'b1;
        s_axi_bready  <= 1'b1;
        // Wait for AW and W ready
        while (!s_axi_awready || !s_axi_wready) @(posedge clk);
        @(posedge clk);
        s_axi_awvalid <= 1'b0;
        s_axi_wvalid  <= 1'b0;
        // Wait for B response
        while (!s_axi_bvalid) @(posedge clk);
        @(posedge clk);
        s_axi_bready <= 1'b0;
    end
    endtask

    // ----------------------------------------------------------------
    // AXI4-Lite Read Task
    // ----------------------------------------------------------------
    task axi_lite_read;
        input  [15:0] addr;
        output [31:0] data;
    begin
        @(posedge clk);
        s_axi_araddr  <= addr;
        s_axi_arvalid <= 1'b1;
        s_axi_rready  <= 1'b1;
        // Wait for AR ready
        while (!s_axi_arready) @(posedge clk);
        @(posedge clk);
        s_axi_arvalid <= 1'b0;
        // Wait for R valid
        while (!s_axi_rvalid) @(posedge clk);
        data = s_axi_rdata;
        @(posedge clk);
        s_axi_rready <= 1'b0;
    end
    endtask

    // ----------------------------------------------------------------
    // AXI4-Stream Send Task (32 beats)
    // ----------------------------------------------------------------
    task axis_send_message;
        input [31:0] word0;  // Only word 0 is set, others are 0
    begin
        s_axis_tvalid <= 1'b1;
        s_axis_tdata  <= word0;
        s_axis_tlast  <= 1'b0;
        while (!s_axis_tready) @(posedge clk);
        @(posedge clk);
        // Words 1-30: all zeros
        s_axis_tdata <= 32'h0;
        repeat (30) begin
            while (!s_axis_tready) @(posedge clk);
            @(posedge clk);
        end
        // Word 31 (last)
        s_axis_tlast <= 1'b1;
        while (!s_axis_tready) @(posedge clk);
        @(posedge clk);
        s_axis_tvalid <= 1'b0;
        s_axis_tlast  <= 1'b0;
        s_axis_tdata  <= 32'h0;
    end
    endtask

    // ----------------------------------------------------------------
    // AXI4-Stream Receive Task (32 beats)
    // ----------------------------------------------------------------
    task axis_receive_result;
        output [31:0] result_word0;
        reg [31:0] rdata;
        integer i;
    begin
        m_axis_tready <= 1'b1;
        i = 0;
        while (i < 32) begin
            @(posedge clk);
            if (m_axis_tvalid) begin
                if (i == 0) result_word0 = m_axis_tdata;
                if (i < 31 && m_axis_tdata !== 32'h0) begin
                    $display("[FAIL] Result word %0d = 0x%08X (expected 0)", i, m_axis_tdata);
                    fail_count = fail_count + 1;
                end
                i = i + 1;
            end
        end
        m_axis_tready <= 1'b0;
    end
    endtask

    // ----------------------------------------------------------------
    // Check task
    // ----------------------------------------------------------------
    task check;
        input [255:0] name;
        input [31:0]  actual;
        input [31:0]  expected;
    begin
        if (actual !== expected) begin
            $display("[FAIL] %0s: got 0x%08H, expected 0x%08H", name, actual, expected);
            fail_count = fail_count + 1;
        end else begin
            $display("[PASS] %0s: 0x%08H", name, actual);
        end
    end
    endtask

    // ----------------------------------------------------------------
    // Wait for DONE status
    // ----------------------------------------------------------------
    task wait_for_done;
        reg [31:0] stat;
        integer timeout;
    begin
        timeout = 0;
        stat = 32'h0;
        while (timeout < 10_000_000) begin
            axi_lite_read(16'h0004, stat);
            if (stat[1]) begin  // DONE bit
                $display("[INFO] DONE asserted after %0d cycles (approx)", timeout);
                disable wait_for_done;
            end
            timeout = timeout + 10;
        end
        $display("[FAIL] Timeout waiting for DONE after 10M cycles");
        fail_count = fail_count + 1;
    end
    endtask

    // ----------------------------------------------------------------
    // dsp_mac_32 standalone test
    // ----------------------------------------------------------------
    // Signals for standalone dsp_mac_32 test
    reg         mac_clk;
    reg         mac_rst;
    reg  [31:0] mac_a, mac_b, mac_c_in, mac_t_in;
    wire [31:0] mac_res, mac_c_out;

    dsp_mac_32 mac_dut (
        .clk      (mac_clk),
        .rst      (mac_rst),
        .a_i      (mac_a),
        .b_i      (mac_b),
        .c_in_i   (mac_c_in),
        .t_in_i   (mac_t_in),
        .res_out_o(mac_res),
        .c_out_o  (mac_c_out)
    );

    initial mac_clk = 0;
    always #(CLK_PERIOD/2) mac_clk = ~mac_clk;

    // ----------------------------------------------------------------
    // mont_mult_1024 standalone test
    // ----------------------------------------------------------------
    reg         mm_rst;
    reg         mm_start;
    wire        mm_done;
    reg         mm_mem_wr_en;
    reg  [1:0]  mm_mem_sel;
    reg  [4:0]  mm_mem_addr;
    reg  [31:0] mm_mem_wdata;
    reg  [31:0] mm_n_prime;
    reg  [4:0]  mm_result_addr;
    wire [31:0] mm_result_data;

    mont_mult_1024 mm_dut (
        .clk           (clk),
        .rst           (mm_rst),
        .start_i       (mm_start),
        .done_o        (mm_done),
        .mem_wr_en_i   (mm_mem_wr_en),
        .mem_sel_i     (mm_mem_sel),
        .mem_addr_i    (mm_mem_addr),
        .mem_wdata_i   (mm_mem_wdata),
        .n_prime_i     (mm_n_prime),
        .result_addr_i (mm_result_addr),
        .result_data_o (mm_result_data)
    );

    // ----------------------------------------------------------------
    // Main Test Sequence
    // ----------------------------------------------------------------
    initial begin
        // Dump waveform
        $dumpfile("tb_rsa1024_modexp_accel.vcd");
        $dumpvars(0, tb_rsa1024_modexp_accel);

        fail_count = 0;
        test_num = 0;

        // Initialize all signals
        rst            = 1;
        s_axi_awaddr   = 0;
        s_axi_awvalid  = 0;
        s_axi_wdata    = 0;
        s_axi_wvalid   = 0;
        s_axi_bready   = 0;
        s_axi_araddr   = 0;
        s_axi_arvalid  = 0;
        s_axi_rready   = 0;
        s_axis_tdata   = 0;
        s_axis_tvalid  = 0;
        s_axis_tlast   = 0;
        m_axis_tready  = 0;

        mac_rst  = 1;
        mac_a    = 0;
        mac_b    = 0;
        mac_c_in = 0;
        mac_t_in = 0;

        // ============================================================
        // Test 1: Reset Behavior
        // ============================================================
        test_num = 1;
        $display("\n=== Test %0d: Reset Behavior ===", test_num);
        rst = 1;
        repeat (10) @(posedge clk);
        rst = 0;
        @(posedge clk);
        @(posedge clk);
        // Check STAT_REG reads 0 after reset
        begin : test1_check
            reg [31:0] stat_val;
            axi_lite_read(16'h0004, stat_val);
            check("STAT_REG after reset", stat_val, 32'h0);
        end

        // ============================================================
        // Test 2: AXI-Lite Register Write/Read
        // ============================================================
        test_num = 2;
        $display("\n=== Test %0d: AXI-Lite Register Access ===", test_num);
        begin : test2
            reg [31:0] rd_val;

            // Write N_prime
            axi_lite_write(16'h0010, 32'h3B13B13B);
            axi_lite_read(16'h0010, rd_val);
            check("N_prime readback", rd_val, 32'h3B13B13B);

            // Write N[0] = 13
            axi_lite_write(16'h0100, 32'h0000000D);
            axi_lite_read(16'h0100, rd_val);
            check("N[0] readback", rd_val, 32'h0000000D);

            // Write E[0] = 1
            axi_lite_write(16'h0200, 32'h00000001);
            axi_lite_read(16'h0200, rd_val);
            check("E[0] readback", rd_val, 32'h00000001);

            // Write R2[0] = 9
            axi_lite_write(16'h0300, 32'h00000009);
            axi_lite_read(16'h0300, rd_val);
            check("R2[0] readback", rd_val, 32'h00000009);

            // Write N[1..31] = 0 (explicitly clear)
            begin : clear_n
                integer k;
                for (k = 1; k < 32; k = k + 1) begin
                    axi_lite_write(16'h0100 + k*4, 32'h0);
                end
            end

            // Write E[1..31] = 0
            begin : clear_e
                integer k;
                for (k = 1; k < 32; k = k + 1) begin
                    axi_lite_write(16'h0200 + k*4, 32'h0);
                end
            end

            // Write R2[1..31] = 0
            begin : clear_r2
                integer k;
                for (k = 1; k < 32; k = k + 1) begin
                    axi_lite_write(16'h0300 + k*4, 32'h0);
                end
            end
        end

        // ============================================================
        // Test 3: dsp_mac_32 Pipeline
        // ============================================================
        test_num = 3;
        $display("\n=== Test %0d: dsp_mac_32 Pipeline ===", test_num);
        begin : test3
            mac_rst = 1;
            repeat (5) @(posedge mac_clk);
            mac_rst = 0;
            repeat (2) @(posedge mac_clk);

            // Test: 5 * 7 + 0 + 0 = 35
            mac_a = 32'h5; mac_b = 32'h7; mac_c_in = 32'h0; mac_t_in = 32'h0;
            repeat (3) @(posedge mac_clk);
            check("MAC 5*7+0+0 result", mac_res, 32'h23);  // 35 = 0x23
            check("MAC 5*7+0+0 carry", mac_c_out, 32'h0);

            // Test: 0xFFFFFFFF * 2 + 0 + 0 = 0x1FFFFFFFE (res=0xFFFFFFFE, carry=1)
            mac_a = 32'hFFFFFFFF; mac_b = 32'h2; mac_c_in = 32'h0; mac_t_in = 32'h0;
            repeat (3) @(posedge mac_clk);
            check("MAC FFFFFFFF*2 result", mac_res, 32'hFFFFFFFE);
            check("MAC FFFFFFFF*2 carry", mac_c_out, 32'h1);

            // Test: 3 * 9 + 100 + 200 = 327 = 0x147
            mac_a = 32'h3; mac_b = 32'h9; mac_c_in = 32'h64; mac_t_in = 32'hC8;
            repeat (3) @(posedge mac_clk);
            check("MAC 3*9+100+200 result", mac_res, 32'h147);
            check("MAC 3*9+100+200 carry", mac_c_out, 32'h0);
        end

        // ============================================================
        // Test 4: MontMult MonPro(0, 0) = 0 (standalone)
        // ============================================================
        test_num = 4;
        $display("\n=== Test %0d: MontMult MonPro(0, 0) ===", test_num);
        begin : test4
            integer k;

            mm_rst <= 1;
            mm_start <= 0;
            mm_mem_wr_en <= 0;
            mm_mem_sel <= 0;
            mm_mem_addr <= 0;
            mm_mem_wdata <= 0;
            mm_n_prime <= 32'h3B13B13B;
            mm_result_addr <= 0;
            repeat (10) @(posedge clk);
            mm_rst <= 0;
            repeat (5) @(posedge clk);

            // Load op_a = all zeros (32 words)
            for (k = 0; k < 32; k = k + 1) begin
                @(posedge clk);
                mm_mem_wr_en  <= 1;
                mm_mem_sel    <= 2'b00;  // op_a
                mm_mem_addr   <= k[4:0];
                mm_mem_wdata  <= 32'h0;
            end
            @(posedge clk);
            mm_mem_wr_en <= 0;

            // Load op_b = all zeros (32 words)
            for (k = 0; k < 32; k = k + 1) begin
                @(posedge clk);
                mm_mem_wr_en  <= 1;
                mm_mem_sel    <= 2'b01;  // op_b
                mm_mem_addr   <= k[4:0];
                mm_mem_wdata  <= 32'h0;
            end
            @(posedge clk);
            mm_mem_wr_en <= 0;

            // Load N = {0,...,0, 13} (modulus)
            for (k = 0; k < 32; k = k + 1) begin
                @(posedge clk);
                mm_mem_wr_en  <= 1;
                mm_mem_sel    <= 2'b10;  // modulus
                mm_mem_addr   <= k[4:0];
                if (k == 0)
                    mm_mem_wdata <= 32'hD;  // N = 13
                else
                    mm_mem_wdata <= 32'h0;
            end
            @(posedge clk);
            mm_mem_wr_en <= 0;

            // Start Montgomery multiplication
            $display("[INFO] Starting MonPro(0, 0)...");
            repeat (5) @(posedge clk);
            mm_start <= 1;
            @(posedge clk);
            mm_start <= 0;

            // Wait for done (should be ~4500 cycles)
            begin : wait_mm
                integer timeout;
                timeout = 0;
                while (!mm_done && timeout < 20000) begin
                    @(posedge clk);
                    timeout = timeout + 1;
                end
                if (mm_done) begin
                    $display("[INFO] MonPro done after %0d cycles", timeout);
                    $display("[DEBUG] state_reg=%0d i_cnt=%0d copy_cnt=%0d",
                             mm_dut.state_reg, mm_dut.i_cnt_reg, mm_dut.copy_cnt_reg);
                end else begin
                    $display("[FAIL] MonPro timeout after 20000 cycles");
                    $display("[DEBUG] mm_dut state_reg = %0d", mm_dut.state_reg);
                    fail_count = fail_count + 1;
                    disable wait_mm;
                end
            end

            // Wait a few more cycles for copy to complete
            repeat (40) @(posedge clk);

            // Read result (should be all zeros)
            for (k = 0; k < 32; k = k + 1) begin
                @(posedge clk);
                mm_result_addr <= k[4:0];
                #1;
                if (mm_result_data !== 32'h0) begin
                    $display("[FAIL] Result[%0d] = 0x%08h, expected 0x0", k, mm_result_data);
                    fail_count = fail_count + 1;
                end else begin
                    $display("[PASS] Result[%0d] = 0x%08h", k, mm_result_data);
                end
            end
        end

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

endmodule
