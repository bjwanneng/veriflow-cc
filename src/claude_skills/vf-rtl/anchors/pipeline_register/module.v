// Anchor: 3-stage pipeline register with valid following data flow
// Style: single sequential block, synchronous active-high reset
// Bubble handling: invalid data is replaced with 0

`resetall
`timescale 1ns / 1ps
`default_nettype none

module pipeline_register
(
    input  wire         clk,
    input  wire         rst,
    input  wire         valid_in,
    input  wire [31:0]  data_in,
    output wire         valid_out,
    output wire [31:0]  data_out
);

reg [31:0] data_0_reg = 32'd0;
reg [31:0] data_1_reg = 32'd0;
reg [31:0] data_2_reg = 32'd0;
reg        valid_0_reg = 1'b0;
reg        valid_1_reg = 1'b0;
reg        valid_2_reg = 1'b0;

always @(posedge clk) begin
    if (rst) begin
        data_0_reg  <= 32'd0;
        data_1_reg  <= 32'd0;
        data_2_reg  <= 32'd0;
        valid_0_reg <= 1'b0;
        valid_1_reg <= 1'b0;
        valid_2_reg <= 1'b0;
    end else begin
        data_0_reg  <= valid_in ? data_in : 32'd0;
        valid_0_reg <= valid_in;
        data_1_reg  <= valid_0_reg ? data_0_reg : 32'd0;
        valid_1_reg <= valid_0_reg;
        data_2_reg  <= valid_1_reg ? data_1_reg : 32'd0;
        valid_2_reg <= valid_1_reg;
    end
end

assign valid_out = valid_2_reg;
assign data_out  = data_2_reg;

endmodule

`resetall
