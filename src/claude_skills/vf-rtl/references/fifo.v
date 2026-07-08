// Reference: synchronous FIFO (Verilog-2005). Single-clock, depth-power-of-2.
// Pointers wrap with bit-width truncation; full/empty derived from count.
module fifo #(parameter WIDTH = 8, parameter DEPTH = 8) (
    input  wire             clk,
    input  wire             rst,
    input  wire             wr_en,
    input  wire             rd_en,
    input  wire [WIDTH-1:0] data_in,
    output wire [WIDTH-1:0] data_out,
    output wire             full,
    output wire             empty
);
    localparam AW = $clog2(DEPTH);   // $clog2 supported by iverilog/yosys
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [AW:0]      wr_ptr, rd_ptr;  // one extra bit to disambiguate full/empty
    reg [AW-1:0]    wr_addr, rd_addr;

    assign wr_addr = wr_ptr[AW-1:0];
    assign rd_addr = rd_ptr[AW-1:0];
    assign data_out = mem[rd_addr];

    wire do_wr = wr_en && !full;
    wire do_rd = rd_en && !empty;

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr <= 0;
            rd_ptr <= 0;
        end else begin
            if (do_wr) begin
                mem[wr_addr] <= data_in;
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (do_rd)
                rd_ptr <= rd_ptr + 1'b1;
        end
    end

    assign empty = (wr_ptr == rd_ptr);
    assign full  = (wr_ptr[AW] != rd_ptr[AW]) && (wr_addr == rd_addr);
endmodule
