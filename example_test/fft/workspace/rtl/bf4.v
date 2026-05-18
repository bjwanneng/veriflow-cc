`resetall
`timescale 1ns / 1ps
`default_nettype none

// bf4.v -- Radix-4 butterfly unit (combinational).
//
// Implements the radix-4 DIT butterfly:
//   Z0 = (x0+x2) + (x1+x3)
//   Z1 = (x0-x2) - j*(x1-x3)   =>  re=(x0_re-x2_re)+(x1_im-x3_im), im=(x0_im-x2_im)-(x1_re-x3_re)
//   Z2 = (x0+x2) - (x1+x3)
//   Z3 = (x0-x2) + j*(x1-x3)   =>  re=(x0_re-x2_re)-(x1_im-x3_im), im=(x0_im-x2_im)+(x1_re-x3_re)
//
// Input width = DATA_W, output width = DATA_W+2 (2-bit growth).
// Purely combinational -- no clock or reset.

module bf4 #(
    parameter DATA_W = 16
)(
    input  wire signed [DATA_W-1:0]  x0_re,
    input  wire signed [DATA_W-1:0]  x0_im,
    input  wire signed [DATA_W-1:0]  x1_re,
    input  wire signed [DATA_W-1:0]  x1_im,
    input  wire signed [DATA_W-1:0]  x2_re,
    input  wire signed [DATA_W-1:0]  x2_im,
    input  wire signed [DATA_W-1:0]  x3_re,
    input  wire signed [DATA_W-1:0]  x3_im,
    output wire signed [DATA_W+1:0]  z0_re,
    output wire signed [DATA_W+1:0]  z0_im,
    output wire signed [DATA_W+1:0]  z1_re,
    output wire signed [DATA_W+1:0]  z1_im,
    output wire signed [DATA_W+1:0]  z2_re,
    output wire signed [DATA_W+1:0]  z2_im,
    output wire signed [DATA_W+1:0]  z3_re,
    output wire signed [DATA_W+1:0]  z3_im
);

    // -----------------------------------------------------------------------
    // Intermediate sums/differences (DATA_W+1 bits due to addition)
    // -----------------------------------------------------------------------
    wire signed [DATA_W:0] a_re, a_im;   // x0 + x2
    wire signed [DATA_W:0] b_re, b_im;   // x0 - x2
    wire signed [DATA_W:0] c_re, c_im;   // x1 + x3
    wire signed [DATA_W:0] d_re, d_im;   // x1 - x3

    assign a_re = $signed(x0_re) + $signed(x2_re);
    assign a_im = $signed(x0_im) + $signed(x2_im);
    assign b_re = $signed(x0_re) - $signed(x2_re);
    assign b_im = $signed(x0_im) - $signed(x2_im);
    assign c_re = $signed(x1_re) + $signed(x3_re);
    assign c_im = $signed(x1_im) + $signed(x3_im);
    assign d_re = $signed(x1_re) - $signed(x3_re);
    assign d_im = $signed(x1_im) - $signed(x3_im);

    // -----------------------------------------------------------------------
    // Butterfly outputs (DATA_W+2 bits due to second addition)
    // Z0 = a + c
    // Z1 = b - j*d  =>  real = b_re,       imag = -d_im   (swap+negate)
    //                  but wait: -j*(d_re+j*d_im) = d_im - j*d_re
    //                  so Z1_real = b_re + d_im, Z1_imag = b_im - d_re
    //                  Hmm, let me re-derive from golden_model:
    //                  z1 = bv + complex(d.imag, -d.real)
    //                  bv = (x0-x2) complex, d = (x1-x3) complex
    //                  z1_real = b_re + d_im, z1_imag = b_im - d_re
    // Z2 = a - c
    // Z3 = b + j*d  =>  z3_real = b_re - d_im, z3_imag = b_im + d_re
    //   From golden: z3 = bv + complex(-d.imag, d.real)
    //   z3_real = b_re - d_im, z3_imag = b_im + d_re
    // -----------------------------------------------------------------------

    // Z0 = (x0+x2) + (x1+x3) = a + c
    assign z0_re = $signed(a_re) + $signed(c_re);
    assign z0_im = $signed(a_im) + $signed(c_im);

    // Z1 = (x0-x2) - j*(x1-x3)  [DIT butterfly]
    //    -j*(d_re+j*d_im) = d_im - j*d_re
    //    z1_real = b_re + d_im
    //    z1_imag = b_im - d_re
    assign z1_re = $signed(b_re) + $signed(d_im);
    assign z1_im = $signed(b_im) - $signed(d_re);

    // Z2 = (x0+x2) - (x1+x3) = a - c
    assign z2_re = $signed(a_re) - $signed(c_re);
    assign z2_im = $signed(a_im) - $signed(c_im);

    // Z3 = (x0-x2) + j*(x1-x3)  [DIT butterfly]
    //    j*(d_re+j*d_im) = -d_im + j*d_re
    //    z3_real = b_re - d_im
    //    z3_imag = b_im + d_re
    assign z3_re = $signed(b_re) - $signed(d_im);
    assign z3_im = $signed(b_im) + $signed(d_re);

endmodule

`resetall
