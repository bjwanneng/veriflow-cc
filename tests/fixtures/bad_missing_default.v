module bad_missing_default(
    input  wire        clk,
    input  wire        rst,
    input  wire [1:0]  sel,
    input  wire [31:0] data_in,
    output wire [31:0] data_out
);
    reg [31:0] out_reg = 32'd0, out_next;

    assign data_out = out_reg;

    always @* begin
        out_next = out_reg;
        case (sel)
            2'd0: out_next = data_in;
            2'd1: out_next = data_in + 1;
            2'd2: out_next = data_in + 2;
            // BUG: no default branch — latch risk
        endcase
    end

    always @(posedge clk) begin
        out_reg <= out_next;
        if (rst)
            out_reg <= 32'd0;
    end
endmodule
