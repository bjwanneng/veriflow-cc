// -----------------------------------------------------------------------------
// File   : chacha20_qr.v
// Author : Auto-generated
// Date   : 2026-04-24
// -----------------------------------------------------------------------------
// Description:
//   ChaCha20 quarter-round function (combinational). Performs four additions,
//   four XORs, and four left-rotations on four 32-bit state words as defined
//   in RFC 8439 Section 2.1. No clock or reset; outputs are purely
//   combinational functions of the inputs.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-24  Auto-generated  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module chacha20_qr
(
    input  wire [31:0] a_i,
    input  wire [31:0] b_i,
    input  wire [31:0] c_i,
    input  wire [31:0] d_i,
    output wire [31:0] a_o,
    output wire [31:0] b_o,
    output wire [31:0] c_o,
    output wire [31:0] d_o
);

    //-------------------------------------------------------------------------
    // Step 1: a = (a + b); d = d XOR a; d = rot16(d)
    //-------------------------------------------------------------------------
    wire [31:0] step1_a = a_i + b_i;
    wire [31:0] xor1_d  = d_i ^ step1_a;
    wire [31:0] rot1_d  = {xor1_d[15:0], xor1_d[31:16]};

    //-------------------------------------------------------------------------
    // Step 2: c = (c + d_rot); b = b XOR c; b = rot12(b)
    //-------------------------------------------------------------------------
    wire [31:0] step2_c = c_i + rot1_d;
    wire [31:0] xor2_b  = b_i ^ step2_c;
    wire [31:0] rot2_b  = {xor2_b[19:0], xor2_b[31:20]};

    //-------------------------------------------------------------------------
    // Step 3: a = (a + b_rot); d = d XOR a; d = rot8(d)
    //-------------------------------------------------------------------------
    wire [31:0] step3_a = step1_a + rot2_b;
    wire [31:0] xor3_d  = rot1_d ^ step3_a;
    wire [31:0] rot3_d  = {xor3_d[23:0], xor3_d[31:24]};

    //-------------------------------------------------------------------------
    // Step 4: c = (c + d_rot); b = b XOR c; b = rot7(b)
    //-------------------------------------------------------------------------
    wire [31:0] step4_c = step2_c + rot3_d;
    wire [31:0] xor4_b  = rot2_b ^ step4_c;
    wire [31:0] rot4_b  = {xor4_b[24:0], xor4_b[31:25]};

    //-------------------------------------------------------------------------
    // Output assignments
    //-------------------------------------------------------------------------
    assign a_o = step3_a;
    assign b_o = rot4_b;
    assign c_o = step4_c;
    assign d_o = rot3_d;

endmodule

`resetall
