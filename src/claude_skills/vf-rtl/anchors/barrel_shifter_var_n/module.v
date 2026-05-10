// Anchor: 32-bit variable barrel shifter (rotate left)
// Style: pure combinational, log2(32)=5 cascaded mux stages
// Rule: variable rotation MUST use barrel shifter, never variable part-select

`resetall
`timescale 1ns / 1ps
`default_nettype none

module barrel_shifter_var_n
(
    input  wire [31:0] data,
    input  wire [4:0]  shift_amount,
    output wire [31:0] rotated
);

reg [31:0] s0;
reg [31:0] s1;
reg [31:0] s2;
reg [31:0] s3;
reg [31:0] s4;

always @(*) begin
    // Stage 0: conditional rotate by 1
    if (shift_amount[0])
        s0 = {data[30:0], data[31]};
    else
        s0 = data;

    // Stage 1: conditional rotate by 2
    if (shift_amount[1])
        s1 = {s0[29:0], s0[31:30]};
    else
        s1 = s0;

    // Stage 2: conditional rotate by 4
    if (shift_amount[2])
        s2 = {s1[27:0], s1[31:28]};
    else
        s2 = s1;

    // Stage 3: conditional rotate by 8
    if (shift_amount[3])
        s3 = {s2[23:0], s2[31:24]};
    else
        s3 = s2;

    // Stage 4: conditional rotate by 16
    if (shift_amount[4])
        s4 = {s3[15:0], s3[31:16]};
    else
        s4 = s3;
end

assign rotated = s4;

endmodule

`resetall
