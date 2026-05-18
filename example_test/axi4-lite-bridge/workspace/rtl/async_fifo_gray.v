`resetall
`timescale 1ns / 1ps
`default_nettype none

module async_fifo_gray #(
    parameter DATA_WIDTH = 36,
    parameter FIFO_DEPTH = 4
)(
    // Write-domain signals
    input  wire                  wr_clk,
    input  wire                  wr_rst_n,
    input  wire                  wr_en,
    input  wire [DATA_WIDTH-1:0] wr_data,
    output wire                  full,

    // Read-domain signals
    input  wire                  rd_clk,
    input  wire                  rd_rst_n,
    input  wire                  rd_en,
    output wire [DATA_WIDTH-1:0] rd_data,
    output wire                  empty
);

    // ----------------------------------------------------------------
    // Local parameters
    // ----------------------------------------------------------------
    // PTR_WIDTH = log2(DEPTH) + 1 (extra MSB for full/empty disambiguation)
    localparam PTR_WIDTH = $clog2(FIFO_DEPTH) + 1;

    // ----------------------------------------------------------------
    // Memory array
    // ----------------------------------------------------------------
    reg [DATA_WIDTH-1:0] mem [FIFO_DEPTH-1:0];

    // ----------------------------------------------------------------
    // Write-domain pointers (binary and gray)
    // ----------------------------------------------------------------
    reg [PTR_WIDTH-1:0] wr_ptr_bin;
    reg [PTR_WIDTH-1:0] wr_ptr_gray;

    // Read pointer gray, synced into write clock domain (2-stage)
    reg [PTR_WIDTH-1:0] rd_ptr_gray_sync1;
    reg [PTR_WIDTH-1:0] rd_ptr_gray_sync2;

    // ----------------------------------------------------------------
    // Read-domain pointers (binary and gray)
    // ----------------------------------------------------------------
    reg [PTR_WIDTH-1:0] rd_ptr_bin;
    reg [PTR_WIDTH-1:0] rd_ptr_gray;

    // Write pointer gray, synced into read clock domain (2-stage)
    reg [PTR_WIDTH-1:0] wr_ptr_gray_sync1;
    reg [PTR_WIDTH-1:0] wr_ptr_gray_sync2;

    // ----------------------------------------------------------------
    // Write-domain combinational signals
    // ----------------------------------------------------------------
    wire [PTR_WIDTH-1:0] wr_ptr_bin_next;
    wire [PTR_WIDTH-1:0] wr_ptr_gray_next;
    wire                 wr_full_next;

    // Next write pointer (binary)
    assign wr_ptr_bin_next  = wr_ptr_bin + {{(PTR_WIDTH-1){1'b0}}, 1'b1};

    // Binary-to-Gray conversion for write pointer
    assign wr_ptr_gray_next = wr_ptr_bin_next ^ (wr_ptr_bin_next >> 1);

    // Full detection:
    //   FIFO is full when the next gray write pointer matches the synced
    //   gray read pointer with the two MSBs inverted.
    //   Gray code property: full <=> next_wr_gray == {~rd_gray[MSB:MSB-1], rd_gray[MSB-2:0]}
    assign wr_full_next = (wr_ptr_gray_next == {~rd_ptr_gray_sync2[PTR_WIDTH-1 -: 2],
                                                 rd_ptr_gray_sync2[PTR_WIDTH-3:0]});

    // Combinational full output (same cycle, no register)
    assign full = wr_full_next;

    // ----------------------------------------------------------------
    // Read-domain combinational signals
    // ----------------------------------------------------------------
    wire [PTR_WIDTH-1:0] rd_ptr_bin_next;
    wire [PTR_WIDTH-1:0] rd_ptr_gray_next;

    // Next read pointer (binary)
    assign rd_ptr_bin_next  = rd_ptr_bin + {{(PTR_WIDTH-1){1'b0}}, 1'b1};

    // Binary-to-Gray conversion for read pointer
    assign rd_ptr_gray_next = rd_ptr_bin_next ^ (rd_ptr_bin_next >> 1);

    // Empty detection: FIFO is empty when synced gray write pointer equals
    // the current gray read pointer.
    assign empty = (wr_ptr_gray_sync2 == rd_ptr_gray);

    // ----------------------------------------------------------------
    // Write clock domain: sequential logic
    // ----------------------------------------------------------------
    // Write pointer update, memory write, sync rd_ptr_gray into wr_clk
    always @(posedge wr_clk or negedge wr_rst_n) begin
        if (!wr_rst_n) begin
            wr_ptr_bin        <= {PTR_WIDTH{1'b0}};
            wr_ptr_gray       <= {PTR_WIDTH{1'b0}};
            rd_ptr_gray_sync1 <= {PTR_WIDTH{1'b0}};
            rd_ptr_gray_sync2 <= {PTR_WIDTH{1'b0}};
        end else begin
            // 2-stage synchronizer: rd_ptr_gray -> wr_clk domain
            rd_ptr_gray_sync1 <= rd_ptr_gray;
            rd_ptr_gray_sync2 <= rd_ptr_gray_sync1;

            // Write pointer advance
            if (wr_en && !full) begin
                wr_ptr_bin  <= wr_ptr_bin_next;
                wr_ptr_gray <= wr_ptr_gray_next;
            end
        end
    end

    // Memory write (combinational write enable with registered address/data)
    always @(posedge wr_clk) begin
        if (wr_en && !full) begin
            mem[wr_ptr_bin[PTR_WIDTH-2:0]] <= wr_data;
        end
    end

    // ----------------------------------------------------------------
    // Read clock domain: sequential logic
    // ----------------------------------------------------------------
    // Read pointer update, sync wr_ptr_gray into rd_clk
    always @(posedge rd_clk or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            rd_ptr_bin        <= {PTR_WIDTH{1'b0}};
            rd_ptr_gray       <= {PTR_WIDTH{1'b0}};
            wr_ptr_gray_sync1 <= {PTR_WIDTH{1'b0}};
            wr_ptr_gray_sync2 <= {PTR_WIDTH{1'b0}};
        end else begin
            // 2-stage synchronizer: wr_ptr_gray -> rd_clk domain
            wr_ptr_gray_sync1 <= wr_ptr_gray;
            wr_ptr_gray_sync2 <= wr_ptr_gray_sync1;

            // Read pointer advance
            if (rd_en && !empty) begin
                rd_ptr_bin  <= rd_ptr_bin_next;
                rd_ptr_gray <= rd_ptr_gray_next;
            end
        end
    end

    // Read data output: combinational read from distributed RAM.
    // Data is available immediately when empty goes low (first-word fall-through).
    // Safe because Gray-code pointer crossing ensures write data is stable before
    // empty deasserts (2-cycle sync latency).
    assign rd_data = mem[rd_ptr_bin[PTR_WIDTH-2:0]];

endmodule

`resetall
