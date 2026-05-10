module bad_concat_width(
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] data_in,
    output wire [31:0] data_out
);
    reg [31:0] out_reg = 32'd0;

    // BUG: ROL by 9 with wrong bit widths
    // Should be {data_in[22:0], data_in[31:23]} (23+9=32)
    // But has {data_in[22:0], data_in[31:7]}  (23+25=48)
    wire [31:0] rol_bad = {data_in[22:0], data_in[31:7]};

    assign data_out = out_reg;

    always @(posedge clk) begin
        out_reg <= rol_bad;
        if (rst)
            out_reg <= 32'd0;
    end
endmodule
