module bad_coasserted_elif(
    input  wire        clk,
    input  wire        rst,
    input  wire        load_en,
    input  wire        calc_en,
    input  wire [31:0] data_in,
    output wire [31:0] data_out
);
    reg [31:0] acc_reg = 32'd0, acc_next;

    assign data_out = acc_reg;

    always @* begin
        acc_next = acc_reg;
        // BUG: if/else if for co-asserted enables
        if (load_en) begin
            acc_next = data_in;
        end
        else if (calc_en) begin  // L5 should flag this
            acc_next = acc_reg ^ data_in;
        end
    end

    always @(posedge clk) begin
        acc_reg <= acc_next;
        if (rst)
            acc_reg <= 32'd0;
    end
endmodule
