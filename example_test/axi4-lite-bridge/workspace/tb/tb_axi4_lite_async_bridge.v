`timescale 1ns / 1ps
// tb_axi4_lite_async_bridge.v -- Self-checking Verilog testbench for
// axi4_lite_async_bridge. No Python dependencies.
//
// Tests a simple write-then-read sequence through the async bridge.
// Two asynchronous clocks: s_axi_aclk at 10ns (100 MHz), m_axi_aclk at 13ns
// (~77 MHz). Different frequencies stress the async crossing.
//
// The master-side slave BFM is implemented as always-ready with a small
// latency for B and R responses. The slave-side master drives AXI transactions
// via the initial block.

module tb_axi4_lite_async_bridge;

    // =========================================================================
    // Port declarations matching DUT (all top-level ports)
    // =========================================================================

    // Slave-side clock and reset
    reg         s_axi_aclk;
    reg         s_axi_aresetn;

    // Master-side clock and reset
    reg         m_axi_aclk;
    reg         m_axi_aresetn;

    // Slave-side AXI (master BFM drives these)
    reg         s_axi_awvalid;
    wire        s_axi_awready;
    reg  [31:0] s_axi_awaddr;
    reg  [2:0]  s_axi_awprot;
    reg         s_axi_wvalid;
    wire        s_axi_wready;
    reg  [31:0] s_axi_wdata;
    reg  [3:0]  s_axi_wstrb;
    wire        s_axi_bvalid;
    reg         s_axi_bready;
    wire [1:0]  s_axi_bresp;
    reg         s_axi_arvalid;
    wire        s_axi_arready;
    reg  [31:0] s_axi_araddr;
    reg  [2:0]  s_axi_arprot;
    wire        s_axi_rvalid;
    reg         s_axi_rready;
    wire [31:0] s_axi_rdata;
    wire [1:0]  s_axi_rresp;

    // Master-side AXI (slave BFM drives these)
    wire        m_axi_awvalid;
    reg         m_axi_awready;
    wire [31:0] m_axi_awaddr;
    wire [2:0]  m_axi_awprot;
    wire        m_axi_wvalid;
    reg         m_axi_wready;
    wire [31:0] m_axi_wdata;
    wire [3:0]  m_axi_wstrb;
    reg         m_axi_bvalid;
    wire        m_axi_bready;
    reg  [1:0]  m_axi_bresp;
    wire        m_axi_arvalid;
    reg         m_axi_arready;
    wire [31:0] m_axi_araddr;
    wire [2:0]  m_axi_arprot;
    reg         m_axi_rvalid;
    wire        m_axi_rready;
    reg  [31:0] m_axi_rdata;
    reg  [1:0]  m_axi_rresp;

    // =========================================================================
    // Counters
    // =========================================================================

    integer cycle_count_s = 0;  // s_axi_aclk cycle counter
    integer cycle_count_m = 0;  // m_axi_aclk cycle counter
    integer fail_count    = 0;

    // =========================================================================
    // DUT instantiation
    // =========================================================================

    axi4_lite_async_bridge uut (
        .s_axi_aclk      (s_axi_aclk),
        .s_axi_aresetn   (s_axi_aresetn),
        .m_axi_aclk      (m_axi_aclk),
        .m_axi_aresetn   (m_axi_aresetn),

        // Slave-side AXI
        .s_axi_awvalid   (s_axi_awvalid),
        .s_axi_awready   (s_axi_awready),
        .s_axi_awaddr    (s_axi_awaddr),
        .s_axi_awprot    (s_axi_awprot),
        .s_axi_wvalid    (s_axi_wvalid),
        .s_axi_wready    (s_axi_wready),
        .s_axi_wdata     (s_axi_wdata),
        .s_axi_wstrb     (s_axi_wstrb),
        .s_axi_bvalid    (s_axi_bvalid),
        .s_axi_bready    (s_axi_bready),
        .s_axi_bresp     (s_axi_bresp),
        .s_axi_arvalid   (s_axi_arvalid),
        .s_axi_arready   (s_axi_arready),
        .s_axi_araddr    (s_axi_araddr),
        .s_axi_arprot    (s_axi_arprot),
        .s_axi_rvalid    (s_axi_rvalid),
        .s_axi_rready    (s_axi_rready),
        .s_axi_rdata     (s_axi_rdata),
        .s_axi_rresp     (s_axi_rresp),

        // Master-side AXI
        .m_axi_awvalid   (m_axi_awvalid),
        .m_axi_awready   (m_axi_awready),
        .m_axi_awaddr    (m_axi_awaddr),
        .m_axi_awprot    (m_axi_awprot),
        .m_axi_wvalid    (m_axi_wvalid),
        .m_axi_wready    (m_axi_wready),
        .m_axi_wdata     (m_axi_wdata),
        .m_axi_wstrb     (m_axi_wstrb),
        .m_axi_bvalid    (m_axi_bvalid),
        .m_axi_bready    (m_axi_bready),
        .m_axi_bresp     (m_axi_bresp),
        .m_axi_arvalid   (m_axi_arvalid),
        .m_axi_arready   (m_axi_arready),
        .m_axi_araddr    (m_axi_araddr),
        .m_axi_arprot    (m_axi_arprot),
        .m_axi_rvalid    (m_axi_rvalid),
        .m_axi_rready    (m_axi_rready),
        .m_axi_rdata     (m_axi_rdata),
        .m_axi_rresp     (m_axi_rresp)
    );

    // =========================================================================
    // Clock generation -- two async clocks at different frequencies
    // s_axi_aclk: period = 10 ns (100 MHz), half-period = 5 ns
    // m_axi_aclk: period = 13 ns (~77 MHz), half-period = 6.5 ns
    // =========================================================================

    initial s_axi_aclk = 0;
    always #5.0 s_axi_aclk = ~s_axi_aclk;

    initial m_axi_aclk = 0;
    always #6.5 m_axi_aclk = ~m_axi_aclk;

    // Cycle counters
    always @(posedge s_axi_aclk) cycle_count_s = cycle_count_s + 1;
    always @(posedge m_axi_aclk) cycle_count_m = cycle_count_m + 1;

    // =========================================================================
    // VCD capture
    // =========================================================================

    initial begin
        $dumpfile("tb_axi4_lite_async_bridge.vcd");
        $dumpvars(0, tb_axi4_lite_async_bridge);
    end

    // =========================================================================
    // Macros: Race-free sampling helpers
    // =========================================================================

    `define CHECK_SIGNAL(sig, expected, test_name, width) \
        if (sig !== expected) begin \
            $display("[FAIL] test=%s cycle_s=%0d signal=%s kind=registered width=%0db expected=0x%0h actual=0x%0h xor=0x%0h phase=negedge_s", \
                     test_name, cycle_count_s, `"sig`", width, expected, sig, (expected ^ sig)); \
            fail_count = fail_count + 1; \
        end else \
            $display("[PASS] test=%s cycle_s=%0d signal=%s kind=registered width=%0db actual=0x%0h phase=negedge_s", \
                     test_name, cycle_count_s, `"sig`", width, sig);

    // =========================================================================
    // Master-side Slave BFM: always-ready with latency for B and R responses
    // =========================================================================
    //
    // This BFM runs in the m_axi_aclk domain. It:
    //   1. Always asserts awready, wready, arready
    //   2. When it sees awvalid+wvalid (write accepted), drives bvalid+bresp
    //      after a small latency (2 m_clk cycles)
    //   3. When it sees arvalid (read accepted), drives rvalid+rdata+rresp
    //      after a small latency (2 m_clk cycles)

    // Simple memory model for reads: store the last write data per address
    reg [31:0] mem [0:15];  // 16-entry memory for lower 4 address bits
    integer    mem_init;

    initial begin
        for (mem_init = 0; mem_init < 16; mem_init = mem_init + 1)
            mem[mem_init] = 32'h0000_0000;
    end

    // AW+W -> B response path
    reg [31:0] captured_awaddr;
    reg [31:0] captured_wdata;
    reg [3:0]  captured_wstrb;
    reg        b_resp_pending;
    reg [1:0]  b_resp_delay;

    // AR -> R response path
    reg [31:0] captured_araddr;
    reg        r_resp_pending;
    reg [1:0]  r_resp_delay;

    initial begin
        b_resp_pending = 0;
        r_resp_pending = 0;
        b_resp_delay   = 0;
        r_resp_delay   = 0;
        captured_awaddr = 0;
        captured_wdata  = 0;
        captured_wstrb  = 0;
        captured_araddr = 0;
    end

    // Master-side always-ready + B/R response FSM
    always @(posedge m_axi_aclk) begin
        if (!m_axi_aresetn) begin
            m_axi_awready <= 1'b1;
            m_axi_wready  <= 1'b1;
            m_axi_arready <= 1'b1;
            m_axi_bvalid  <= 1'b0;
            m_axi_bresp   <= 2'b00;
            m_axi_rvalid  <= 1'b0;
            m_axi_rdata   <= 32'h0;
            m_axi_rresp   <= 2'b00;
            b_resp_pending <= 1'b0;
            r_resp_pending <= 1'b0;
            b_resp_delay   <= 2'b0;
            r_resp_delay   <= 2'b0;
        end else begin
            // Always ready for AW, W, AR
            m_axi_awready <= 1'b1;
            m_axi_wready  <= 1'b1;
            m_axi_arready <= 1'b1;

            // --- Write path: capture AW+W, respond with B ---
            if (m_axi_awvalid && m_axi_awready && !b_resp_pending) begin
                captured_awaddr <= m_axi_awaddr;
            end
            if (m_axi_wvalid && m_axi_wready && !b_resp_pending) begin
                captured_wdata <= m_axi_wdata;
                captured_wstrb <= m_axi_wstrb;
                // Store to memory model
                if (m_axi_wstrb[0]) mem[captured_awaddr[5:2]][7:0]   <= m_axi_wdata[7:0];
                if (m_axi_wstrb[1]) mem[captured_awaddr[5:2]][15:8]  <= m_axi_wdata[15:8];
                if (m_axi_wstrb[2]) mem[captured_awaddr[5:2]][23:16] <= m_axi_wdata[23:16];
                if (m_axi_wstrb[3]) mem[captured_awaddr[5:2]][31:24] <= m_axi_wdata[31:24];
                b_resp_pending <= 1'b1;
                b_resp_delay   <= 2'd2;  // 2 cycle latency
            end

            if (b_resp_pending) begin
                if (b_resp_delay > 0) begin
                    b_resp_delay <= b_resp_delay - 1;
                end else begin
                    m_axi_bvalid <= 1'b1;
                    m_axi_bresp  <= 2'b00;  // OKAY
                    b_resp_pending <= 1'b0;
                end
            end else if (m_axi_bvalid && m_axi_bready) begin
                // Clear bvalid only when NOT asserting (else if prevents same-cycle cancel)
                m_axi_bvalid <= 1'b0;
            end

            // --- Read path: capture AR, respond with R ---
            if (m_axi_arvalid && m_axi_arready && !r_resp_pending) begin
                captured_araddr <= m_axi_araddr;
                r_resp_pending  <= 1'b1;
                r_resp_delay    <= 2'd2;  // 2 cycle latency
            end

            if (r_resp_pending) begin
                if (r_resp_delay > 0) begin
                    r_resp_delay <= r_resp_delay - 1;
                end else begin
                    m_axi_rvalid <= 1'b1;
                    m_axi_rdata  <= mem[captured_araddr[5:2]];
                    m_axi_rresp  <= 2'b00;  // OKAY
                    r_resp_pending <= 1'b0;
                end
            end else if (m_axi_rvalid && m_axi_rready) begin
                // Clear rvalid only when NOT asserting (else if prevents same-cycle cancel)
                m_axi_rvalid <= 1'b0;
            end
        end
    end

    // =========================================================================
    // Test sequence: slave-side master BFM
    // =========================================================================
    //
    // Test plan:
    //   1. Write addr=0x00001000, data=0xDEADBEEF, strb=0xF
    //      -> expect bresp=0x0 (OKAY) on slave side
    //   2. Read  addr=0x00001000
    //      -> expect rdata=0xDEADBEEF, rresp=0x0 (OKAY) on slave side

    localparam [31:0] WRITE_ADDR  = 32'h0000_1000;
    localparam [31:0] WRITE_DATA  = 32'hDEAD_BEEF;
    localparam [3:0]  WRITE_STRB  = 4'hF;
    localparam [1:0]  EXPECT_OKAY = 2'b00;

    integer timeout;

    initial begin
        // ================================================================
        // Reset sequence
        // ================================================================
        s_axi_aresetn = 0;
        m_axi_aresetn = 0;

        // Zero all slave-side master inputs (non-blocking for data, blocking for reset)
        s_axi_awvalid <= 1'b0;
        s_axi_awaddr  <= 32'h0;
        s_axi_awprot  <= 3'h0;
        s_axi_wvalid  <= 1'b0;
        s_axi_wdata   <= 32'h0;
        s_axi_wstrb   <= 4'h0;
        s_axi_bready  <= 1'b0;
        s_axi_arvalid <= 1'b0;
        s_axi_araddr  <= 32'h0;
        s_axi_arprot  <= 3'h0;
        s_axi_rready  <= 1'b0;

        // Hold reset for 10 s_clk cycles (100 ns)
        #(10 * 10);
        s_axi_aresetn = 1;
        m_axi_aresetn = 1;
        // Wait for reset recovery (3 cycles in each domain)
        repeat (3) @(posedge s_axi_aclk);
        repeat (3) @(posedge m_axi_aclk);
        @(negedge s_axi_aclk);
        $display("[TRACE] cycle_s=%0d reset released", cycle_count_s);

        // ================================================================
        // TEST 1: Single write transaction
        // ================================================================
        $display("[TEST] Starting single_write: addr=0x%08h data=0x%08h", WRITE_ADDR, WRITE_DATA);

        // Drive AW channel
        s_axi_awaddr  <= WRITE_ADDR;
        s_axi_awprot  <= 3'h0;
        s_axi_awvalid <= 1'b1;

        // Drive W channel simultaneously
        s_axi_wdata   <= WRITE_DATA;
        s_axi_wstrb   <= WRITE_STRB;
        s_axi_wvalid  <= 1'b1;

        // Accept B response when it arrives
        s_axi_bready  <= 1'b1;

        // Wait for AW handshake
        timeout = 200;
        while (s_axi_awready !== 1'b1 && timeout > 0) begin
            @(posedge s_axi_aclk);
            timeout = timeout - 1;
        end
        if (timeout == 0) begin
            $display("[FAIL] test=single_write cycle_s=%0d signal=s_axi_awready timeout waiting for AW handshake",
                     cycle_count_s);
            fail_count = fail_count + 1;
        end else begin
            @(negedge s_axi_aclk);
            $display("[PASS] test=single_write cycle_s=%0d signal=s_axi_awready kind=pulse width=1b actual=1 phase=negedge_s",
                     cycle_count_s);
        end

        // Deassert AW after handshake
        s_axi_awvalid <= 1'b0;

        // Wait for W handshake
        timeout = 200;
        while (s_axi_wready !== 1'b1 && timeout > 0) begin
            @(posedge s_axi_aclk);
            timeout = timeout - 1;
        end
        if (timeout == 0) begin
            $display("[FAIL] test=single_write cycle_s=%0d signal=s_axi_wready timeout waiting for W handshake",
                     cycle_count_s);
            fail_count = fail_count + 1;
        end else begin
            @(negedge s_axi_aclk);
            $display("[PASS] test=single_write cycle_s=%0d signal=s_axi_wready kind=pulse width=1b actual=1 phase=negedge_s",
                     cycle_count_s);
        end

        // Deassert W after handshake
        s_axi_wvalid <= 1'b0;
        s_axi_wdata  <= 32'h0;
        s_axi_wstrb  <= 4'h0;
        s_axi_awaddr <= 32'h0;

        // Wait for B response (s_axi_bvalid) — sample data at posedge
        // before FIFO pop advances the read pointer
        timeout = 200;
        while (s_axi_bvalid !== 1'b1 && timeout > 0) begin
            @(posedge s_axi_aclk);
            timeout = timeout - 1;
        end
        if (timeout == 0) begin
            $display("[FAIL] test=single_write cycle_s=%0d signal=s_axi_bvalid timeout waiting for B response",
                     cycle_count_s);
            fail_count = fail_count + 1;
        end else begin
            // Sample at posedge (data valid before NBA advances FIFO pointer)
            `CHECK_SIGNAL(s_axi_bresp, EXPECT_OKAY, "single_write_bresp", 2)
        end

        // Deassert B ready
        s_axi_bready <= 1'b0;

        // Wait a few cycles for FIFO crossing to settle
        repeat (5) @(posedge s_axi_aclk);
        @(negedge s_axi_aclk);

        // ================================================================
        // TEST 2: Single read transaction
        // ================================================================
        $display("[TEST] Starting single_read: addr=0x%08h expect_rdata=0x%08h", WRITE_ADDR, WRITE_DATA);

        // Drive AR channel
        s_axi_araddr  <= WRITE_ADDR;
        s_axi_arprot  <= 3'h0;
        s_axi_arvalid <= 1'b1;

        // Accept R response when it arrives
        s_axi_rready  <= 1'b1;

        // Wait for AR handshake
        timeout = 200;
        while (s_axi_arready !== 1'b1 && timeout > 0) begin
            @(posedge s_axi_aclk);
            timeout = timeout - 1;
        end
        if (timeout == 0) begin
            $display("[FAIL] test=single_read cycle_s=%0d signal=s_axi_arready timeout waiting for AR handshake",
                     cycle_count_s);
            fail_count = fail_count + 1;
        end else begin
            @(negedge s_axi_aclk);
            $display("[PASS] test=single_read cycle_s=%0d signal=s_axi_arready kind=pulse width=1b actual=1 phase=negedge_s",
                     cycle_count_s);
        end

        // Deassert AR after handshake
        s_axi_arvalid <= 1'b0;
        s_axi_araddr  <= 32'h0;
        s_axi_arprot  <= 3'h0;

        // Wait for R response (s_axi_rvalid) — sample data at posedge
        // before FIFO pop advances the read pointer
        timeout = 200;
        while (s_axi_rvalid !== 1'b1 && timeout > 0) begin
            @(posedge s_axi_aclk);
            timeout = timeout - 1;
        end
        if (timeout == 0) begin
            $display("[FAIL] test=single_read cycle_s=%0d signal=s_axi_rvalid timeout waiting for R response",
                     cycle_count_s);
            fail_count = fail_count + 1;
        end else begin
            // Sample at posedge (data valid before NBA advances FIFO pointer)
            `CHECK_SIGNAL(s_axi_rdata, WRITE_DATA, "single_read_rdata", 32)
            `CHECK_SIGNAL(s_axi_rresp, EXPECT_OKAY, "single_read_rresp", 2)
        end

        // Deassert R ready
        s_axi_rready <= 1'b0;

        // Wait for settling
        repeat (5) @(posedge s_axi_aclk);
        @(negedge s_axi_aclk);

        // ================================================================
        // Summary
        // ================================================================
        $display("");
        if (fail_count == 0)
            $display("ALL TESTS PASSED");
        else
            $display("FAILED: %0d assertion(s) failed", fail_count);
        $finish;
    end

endmodule
