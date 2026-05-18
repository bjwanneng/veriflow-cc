//----------------------------------------------------------------------
// Testbench for 4-way set-associative write-back cache controller
// Self-checking: drives all TEST_VECTORS and reports PASS/FAIL.
//
// Clock: 5 ns period (100 MHz)
// Reset: 5 cycles active-high
// Backing memory: sparse 128-bit line model with 1-cycle read latency
//----------------------------------------------------------------------

`timescale 1ns / 1ps

module tb_cache_ctrl;

    // ------------------------------------------------------------------
    // Parameters
    // ------------------------------------------------------------------
    parameter CLK_PERIOD   = 5;     // ns
    parameter RST_CYCLES   = 5;
    parameter DRIVE_PHASE  = 1;
    parameter MAX_WAIT     = 50;

    // ------------------------------------------------------------------
    // Signals
    // ------------------------------------------------------------------
    reg         clk;
    reg         rst;
    reg  [31:0] addr;
    reg  [31:0] wdata;
    reg  [3:0]  byte_en;
    reg         mem_read;
    reg         mem_write;
    wire [31:0] rdata;
    wire        ready;
    wire [31:0] m_addr;
    wire [127:0] m_wdata;
    wire        m_rd_en;
    wire        m_wr_en;
    wire [127:0] m_rdata;

    // ------------------------------------------------------------------
    // Backing memory — sparse, keyed by 32-bit word address
    // ------------------------------------------------------------------
    parameter MEM_WORDS = 65536;
    reg [31:0] backing_mem [0:MEM_WORDS-1];

    integer _init_i;
    initial begin
        for (_init_i = 0; _init_i < MEM_WORDS; _init_i = _init_i + 1)
            backing_mem[_init_i] = 32'd0;
    end

    // ------------------------------------------------------------------
    // DUT instantiation
    // ------------------------------------------------------------------
    cache_ctrl dut (
        .clk       (clk),
        .rst       (rst),
        .addr      (addr),
        .wdata     (wdata),
        .byte_en   (byte_en),
        .mem_read  (mem_read),
        .mem_write (mem_write),
        .rdata     (rdata),
        .ready     (ready),
        .m_addr    (m_addr),
        .m_wdata   (m_wdata),
        .m_rd_en   (m_rd_en),
        .m_wr_en   (m_wr_en),
        .m_rdata   (m_rdata)
    );

    // ------------------------------------------------------------------
    // Clock generation
    // ------------------------------------------------------------------
    initial clk = 0;
    always #(CLK_PERIOD/2) clk = ~clk;

    // ------------------------------------------------------------------
    // Backing memory model
    // Read: combinational (0-cycle latency) — responds to m_addr via assign
    // Write: sequential — captures m_wdata on posedge when m_wr_en is high
    // ------------------------------------------------------------------

    // Combinational read response: m_rdata reflects current m_addr immediately
    // This models a memory with zero read latency, matching the golden model
    // (which reads from its Python dict instantaneously in MEM_READ rd_cnt=1).
    assign m_rdata = {backing_mem[m_addr + 0],
                       backing_mem[m_addr + 4],
                       backing_mem[m_addr + 8],
                       backing_mem[m_addr + 12]};

    // Sequential write capture
    always @(posedge clk) begin
        if (!rst && m_wr_en) begin
            backing_mem[m_addr + 0]  <= m_wdata[127:96];
            backing_mem[m_addr + 4]  <= m_wdata[95:64];
            backing_mem[m_addr + 8]  <= m_wdata[63:32];
            backing_mem[m_addr + 12] <= m_wdata[31:0];
        end
    end

    // ------------------------------------------------------------------
    // Tasks
    // ------------------------------------------------------------------

    // Reset sequence
    task reset;
        begin
            rst       = 1;
            addr      = 0;
            wdata     = 0;
            byte_en   = 0;
            mem_read  = 0;
            mem_write = 0;
            repeat (RST_CYCLES) @(posedge clk);
            rst = 0;
            @(posedge clk);
        end
    endtask

    // Drive one operation and wait until ready == 1
    // Returns rdata in _got_rdata
    reg [31:0] _got_rdata;
    integer    _wait_cnt;

    task drive_op;
        input [31:0] i_addr;
        input [31:0] i_wdata;
        input [3:0]  i_byte_en;
        input         i_read;
        input         i_write;
    begin
        addr      = i_addr;
        wdata     = i_wdata;
        byte_en   = i_byte_en;
        mem_read  = i_read;
        mem_write = i_write;

        // Hold inputs for DRIVE_PHASE posedges
        repeat (DRIVE_PHASE) @(posedge clk);

        // De-assert request signals AFTER the posedge (at negedge)
        // to avoid race with DUT's always @(posedge clk) block
        @(negedge clk);
        mem_read  = 0;
        mem_write = 0;

        // Wait for ready at negedge (NBA updates visible at negedge)
        _wait_cnt = 0;
        @(negedge clk);
        while (ready !== 1'b1 && _wait_cnt < MAX_WAIT) begin
            @(posedge clk);
            @(negedge clk);
            _wait_cnt = _wait_cnt + 1;
        end

        if (ready !== 1'b1) begin
            $display("  ERROR: ready never went high (waited %0d cycles)", MAX_WAIT);
        end

        // Sample rdata (already at negedge, NBA visible)
        _got_rdata = rdata;
    end
    endtask

    // ------------------------------------------------------------------
    // Check result helper
    // ------------------------------------------------------------------
    integer total_pass, total_fail;

    task check;
        input [31:0] exp_rdata;
        input [31:0] got_rdata;
        input [255:0] tv_name;  // test vector name (padded string)
        input [31:0] op_idx;
        inout  pass_flag;
    begin
        if (got_rdata !== exp_rdata) begin
            $display("  FAIL op[%0d]: rdata=0x%08H, expected=0x%08H",
                     op_idx, got_rdata, exp_rdata);
            pass_flag = 0;
        end
    end
    endtask

    // ------------------------------------------------------------------
    // Test vectors (hardcoded expected from golden model)
    // ------------------------------------------------------------------

    // tv_read_hit: write 0x100 = 0xDEADBEEF, then read 0x100 -> 0xDEADBEEF
    integer tv_read_hit_pass;
    task run_tv_read_hit;
    begin
        tv_read_hit_pass = 1;
        // op0: write addr=0x100, wdata=0xDEADBEEF, byte_en=0xF
        drive_op(32'h00000100, 32'hDEADBEEF, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_read_hit", 0, tv_read_hit_pass);
        // op1: read addr=0x100
        drive_op(32'h00000100, 32'h00000000, 4'h0, 1'b1, 1'b0);
        check(32'hDEADBEEF, _got_rdata, "tv_read_hit", 1, tv_read_hit_pass);

        if (tv_read_hit_pass) begin
            $display("[PASS] tv_read_hit: Fill a line then read it back");
            total_pass = total_pass + 1;
        end else begin
            $display("[FAIL] tv_read_hit: Fill a line then read it back");
            total_fail = total_fail + 1;
        end
    end
    endtask

    // tv_write_hit: write 0x200=0xAAAA0000, write 0x204=0x0000BBBB
    integer tv_write_hit_pass;
    task run_tv_write_hit;
    begin
        tv_write_hit_pass = 1;
        // op0: write addr=0x200, wdata=0xAAAA0000, byte_en=0xF
        drive_op(32'h00000200, 32'hAAAA0000, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_write_hit", 0, tv_write_hit_pass);
        // op1: write addr=0x204, wdata=0x0000BBBB, byte_en=0xF
        drive_op(32'h00000204, 32'h0000BBBB, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_write_hit", 1, tv_write_hit_pass);

        if (tv_write_hit_pass) begin
            $display("[PASS] tv_write_hit: Write to same line twice");
            total_pass = total_pass + 1;
        end else begin
            $display("[FAIL] tv_write_hit: Write to same line twice");
            total_fail = total_fail + 1;
        end
    end
    endtask

    // tv_conflict_miss: 5 writes to idx=0, different tags
    integer tv_conflict_miss_pass;
    task run_tv_conflict_miss;
    begin
        tv_conflict_miss_pass = 1;
        // op0: write 0x000 = 0x11111111
        drive_op(32'h00000000, 32'h11111111, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_conflict_miss", 0, tv_conflict_miss_pass);
        // op1: write 0x400 = 0x22222222
        drive_op(32'h00000400, 32'h22222222, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_conflict_miss", 1, tv_conflict_miss_pass);
        // op2: write 0x800 = 0x33333333
        drive_op(32'h00000800, 32'h33333333, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_conflict_miss", 2, tv_conflict_miss_pass);
        // op3: write 0xC00 = 0x44444444
        drive_op(32'h00000C00, 32'h44444444, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_conflict_miss", 3, tv_conflict_miss_pass);
        // op4: write 0x1000 = 0x55555555 (evicts way 0)
        drive_op(32'h00001000, 32'h55555555, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_conflict_miss", 4, tv_conflict_miss_pass);

        if (tv_conflict_miss_pass) begin
            $display("[PASS] tv_conflict_miss: 5 addresses same index, different tags");
            total_pass = total_pass + 1;
        end else begin
            $display("[FAIL] tv_conflict_miss: 5 addresses same index, different tags");
            total_fail = total_fail + 1;
        end
    end
    endtask

    // tv_dirty_writeback: fill all ways, then read miss -> dirty eviction
    integer tv_dirty_wb_pass;
    task run_tv_dirty_writeback;
    begin
        tv_dirty_wb_pass = 1;
        // op0: write 0x100 = 0xCAFEBABE
        drive_op(32'h00000100, 32'hCAFEBABE, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_dirty_writeback", 0, tv_dirty_wb_pass);
        // op1: write 0x500 = 0x12345678
        drive_op(32'h00000500, 32'h12345678, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_dirty_writeback", 1, tv_dirty_wb_pass);
        // op2: write 0x900 = 0xAAAAAAAA
        drive_op(32'h00000900, 32'hAAAAAAAA, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_dirty_writeback", 2, tv_dirty_wb_pass);
        // op3: write 0xD00 = 0xBBBBBBBB
        drive_op(32'h00000D00, 32'hBBBBBBBB, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_dirty_writeback", 3, tv_dirty_wb_pass);
        // op4: read 0x1100 -> miss, evicts way 0 (dirty, needs write-back)
        drive_op(32'h00001100, 32'h00000000, 4'h0, 1'b1, 1'b0);
        check(32'h00000000, _got_rdata, "tv_dirty_writeback", 4, tv_dirty_wb_pass);

        if (tv_dirty_wb_pass) begin
            $display("[PASS] tv_dirty_writeback: Write-back before read on dirty miss");
            total_pass = total_pass + 1;
        end else begin
            $display("[FAIL] tv_dirty_writeback: Write-back before read on dirty miss");
            total_fail = total_fail + 1;
        end
    end
    endtask

    // tv_lru_stability: read way 0 x4, trigger miss, verify way 0 intact
    integer tv_lru_pass;
    task run_tv_lru_stability;
    begin
        tv_lru_pass = 1;
        // Fill all 4 ways for index 0
        // op0: write 0x000 = 0x10
        drive_op(32'h00000000, 32'h00000010, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_lru_stability", 0, tv_lru_pass);
        // op1: write 0x400 = 0x20
        drive_op(32'h00000400, 32'h00000020, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_lru_stability", 1, tv_lru_pass);
        // op2: write 0x800 = 0x30
        drive_op(32'h00000800, 32'h00000030, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_lru_stability", 2, tv_lru_pass);
        // op3: write 0xC00 = 0x40
        drive_op(32'h00000C00, 32'h00000040, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_lru_stability", 3, tv_lru_pass);
        // op4-op7: read 0x000 four times (read hit way 0, boost LRU)
        drive_op(32'h00000000, 32'h00000000, 4'h0, 1'b1, 1'b0);
        check(32'h00000010, _got_rdata, "tv_lru_stability", 4, tv_lru_pass);
        drive_op(32'h00000000, 32'h00000000, 4'h0, 1'b1, 1'b0);
        check(32'h00000010, _got_rdata, "tv_lru_stability", 5, tv_lru_pass);
        drive_op(32'h00000000, 32'h00000000, 4'h0, 1'b1, 1'b0);
        check(32'h00000010, _got_rdata, "tv_lru_stability", 6, tv_lru_pass);
        drive_op(32'h00000000, 32'h00000000, 4'h0, 1'b1, 1'b0);
        check(32'h00000010, _got_rdata, "tv_lru_stability", 7, tv_lru_pass);
        // op8: write 0x1000 = 0x50 (miss, evicts LRU way, NOT way 0)
        drive_op(32'h00001000, 32'h00000050, 4'hF, 1'b0, 1'b1);
        check(32'h00000000, _got_rdata, "tv_lru_stability", 8, tv_lru_pass);
        // op9: read 0x000 -> way 0 must still be 0x10
        drive_op(32'h00000000, 32'h00000000, 4'h0, 1'b1, 1'b0);
        check(32'h00000010, _got_rdata, "tv_lru_stability", 9, tv_lru_pass);

        if (tv_lru_pass) begin
            $display("[PASS] tv_lru_stability: Way 0 survives after repeated access");
            total_pass = total_pass + 1;
        end else begin
            $display("[FAIL] tv_lru_stability: Way 0 survives after repeated access");
            total_fail = total_fail + 1;
        end
    end
    endtask

    // ------------------------------------------------------------------
    // Main
    // ------------------------------------------------------------------
    integer i;
    initial begin
        // Initialize backing memory to zero
        for (i = 0; i < MEM_WORDS; i = i + 1)
            backing_mem[i] = 32'b0;

        total_pass = 0;
        total_fail = 0;

        $display("==========================================================");
        $display(" Cache Controller Testbench");
        $display("==========================================================");

        // --- tv_read_hit ---
        reset;
        run_tv_read_hit;

        // --- tv_write_hit ---
        reset;
        run_tv_write_hit;

        // --- tv_conflict_miss ---
        reset;
        run_tv_conflict_miss;

        // --- tv_dirty_writeback ---
        reset;
        run_tv_dirty_writeback;

        // --- tv_lru_stability ---
        reset;
        run_tv_lru_stability;

        // --- Summary ---
        $display("==========================================================");
        $display(" SUMMARY: %0d PASS, %0d FAIL out of %0d test vectors",
                 total_pass, total_fail, total_pass + total_fail);
        $display("==========================================================");

        if (total_fail > 0)
            $display("ALL TESTS FAILED — %0d vector(s) failed.", total_fail);
        else
            $display("ALL TESTS PASSED.");

        $finish;
    end

    // Timeout watchdog
    initial begin
        #100000;
        $display("ERROR: Simulation timeout (100 us)!");
        $finish;
    end

endmodule
