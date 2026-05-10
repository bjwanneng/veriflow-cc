// Anchor: 8-bit shift register with enable gating
// Style: single sequential block, synchronous active-high reset

`resetall
`timescale 1ns / 1ps
`default_nettype none

module shift_register
(
    input  wire         clk,
    input  wire         rst,
    input  wire         shift_en,
    input  wire         data_in,
    output wire [7:0]   shift_reg
);

reg [7:0] shift_reg_reg = 8'd0;

always @(posedge clk) begin
    if (rst) begin
        shift_reg_reg <= 8'd0;
    end else begin
        if (shift_en) begin
            shift_reg_reg <= {data_in, shift_reg_reg[6:0]};
        end else begin
            shift_reg_reg <= shift_reg_reg;
        end
    end
end

assign shift_reg = shift_reg_reg;

endmodule

`resetall
