`resetall
`timescale 1ns / 1ps
`default_nettype none

// complex_mult_3m.v -- 3-multiplier complex multiply with 1 pipeline stage.
//
// Computes (a + j*b) * (c + j*d) using 3 real multipliers:
//   m1 = (a - b) * d
//   m2 = a * (c - d)
//   m3 = b * (c + d)
//   real_out = m1 + m2 = a*c - b*d
//   imag_out = m1 + m3 = a*d + b*c
//
// One pipeline register stage on all outputs.  Async active-low reset.

module complex_mult_3m #(
    parameter DATA_W = 16
)(
    input  wire                          clk,
    input  wire                          rst_n,
    input  wire signed [DATA_W-1:0]      a,
    input  wire signed [DATA_W-1:0]      b,
    input  wire signed [DATA_W-1:0]      c,
    input  wire signed [DATA_W-1:0]      d,
    input  wire                          in_valid,
    output wire signed [2*DATA_W-1:0]    re_out,
    output wire signed [2*DATA_W-1:0]    im_out,
    output wire                          out_valid
);

    // -----------------------------------------------------------------------
    // Stage 0: pre-add/sub + multiply (combinational)
    // -----------------------------------------------------------------------
    wire signed [DATA_W:0] a_minus_b = $signed(a) - $signed(b);
    wire signed [DATA_W:0] c_minus_d = $signed(c) - $signed(d);
    wire signed [DATA_W:0] c_plus_d  = $signed(c) + $signed(d);

    wire signed [2*DATA_W-1:0] m1 = a_minus_b * $signed(d);
    wire signed [2*DATA_W-1:0] m2 = $signed(a) * c_minus_d;
    wire signed [2*DATA_W-1:0] m3 = $signed(b) * c_plus_d;

    // -----------------------------------------------------------------------
    // Stage 1: final add + pipeline register
    // -----------------------------------------------------------------------
    wire signed [2*DATA_W:0] re_wide = $signed(m1) + $signed(m2);
    wire signed [2*DATA_W:0] im_wide = $signed(m1) + $signed(m3);

    reg signed [2*DATA_W-1:0] re_out_reg = {2*DATA_W{1'b0}};
    reg signed [2*DATA_W-1:0] im_out_reg = {2*DATA_W{1'b0}};
    reg                        out_valid_reg = 1'b0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            re_out_reg    <= {2*DATA_W{1'b0}};
            im_out_reg    <= {2*DATA_W{1'b0}};
            out_valid_reg <= 1'b0;
        end else begin
            re_out_reg    <= re_wide[2*DATA_W-1:0];
            im_out_reg    <= im_wide[2*DATA_W-1:0];
            out_valid_reg <= in_valid;
        end
    end

    assign re_out    = re_out_reg;
    assign im_out    = im_out_reg;
    assign out_valid = out_valid_reg;

endmodule

`resetall
