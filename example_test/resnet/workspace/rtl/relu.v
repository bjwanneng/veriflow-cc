`resetall
`timescale 1ns / 1ps
`default_nettype none

module relu #(
    parameter IN_BITS  = 32,
    parameter OUT_BITS = 8
)(
    input  wire clk,
    input  wire rst,
    input  wire in_valid_i,
    input  wire signed [IN_BITS-1:0] in_data_i,
    output wire out_valid_o,
    output wire signed [OUT_BITS-1:0] out_data_o
);

    // -------------------------------------------------------------------------
    // Combinational logic: ReLU = max(0, in_data_i), clamped to INT8 [0, 127]
    // -------------------------------------------------------------------------
    reg signed [OUT_BITS-1:0] relu_next;
    always @* begin
        if (in_data_i < {IN_BITS{1'b0}}) begin
            relu_next = {OUT_BITS{1'b0}};
        end else if (in_data_i > { {(IN_BITS-7){1'b0}}, 7'd127 }) begin
            relu_next = {1'b0, 7'd127};  // 8'sd127
        end else begin
            relu_next = in_data_i[OUT_BITS-1:0];
        end
    end

    // -------------------------------------------------------------------------
    // Sequential logic: register output with synchronous active-high reset
    // -------------------------------------------------------------------------
    reg        out_valid_reg = 1'b0;
    reg signed [OUT_BITS-1:0] out_data_reg = {OUT_BITS{1'b0}};

    always @(posedge clk) begin
        if (rst) begin
            out_valid_reg <= 1'b0;
            out_data_reg  <= {OUT_BITS{1'b0}};
        end else begin
            out_valid_reg <= in_valid_i;
            out_data_reg  <= relu_next;
        end
    end

    // -------------------------------------------------------------------------
    // Output assignments
    // -------------------------------------------------------------------------
    assign out_valid_o = out_valid_reg;
    assign out_data_o  = out_data_reg;

endmodule

`resetall
