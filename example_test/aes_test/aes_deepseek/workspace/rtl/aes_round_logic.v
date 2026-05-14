//------------------------------------------------------------------------------
// Module: aes_round_logic
// Description: Combinational AES round — SubBytes → ShiftRows → MixColumns
//              (skipped on round 10) → AddRoundKey.  Per FIPS 197.
//------------------------------------------------------------------------------
`resetall
`timescale 1ns / 1ps
`default_nettype none

module aes_round_logic(
    input  wire [127:0] state_in,
    input  wire [127:0] round_key,
    input  wire [3:0]   round,
    output wire [127:0] state_out
);

    //--------------------------------------------------------------------------
    // Internal wires
    //--------------------------------------------------------------------------
    wire [127:0] sb;       // SubBytes output
    wire [127:0] sr;       // ShiftRows output
    wire [127:0] mc;       // MixColumns output
    wire [127:0] pre_ark;  // selected input to AddRoundKey

    //--------------------------------------------------------------------------
    // Stage 1: SubBytes — 16 parallel S-Box lookups
    //--------------------------------------------------------------------------
    aes_sbox u_sbox0  (.byte_in(state_in[127:120]), .byte_out(sb[127:120]));
    aes_sbox u_sbox1  (.byte_in(state_in[119:112]), .byte_out(sb[119:112]));
    aes_sbox u_sbox2  (.byte_in(state_in[111:104]), .byte_out(sb[111:104]));
    aes_sbox u_sbox3  (.byte_in(state_in[103:96]),  .byte_out(sb[103:96]));
    aes_sbox u_sbox4  (.byte_in(state_in[95:88]),   .byte_out(sb[95:88]));
    aes_sbox u_sbox5  (.byte_in(state_in[87:80]),   .byte_out(sb[87:80]));
    aes_sbox u_sbox6  (.byte_in(state_in[79:72]),   .byte_out(sb[79:72]));
    aes_sbox u_sbox7  (.byte_in(state_in[71:64]),   .byte_out(sb[71:64]));
    aes_sbox u_sbox8  (.byte_in(state_in[63:56]),   .byte_out(sb[63:56]));
    aes_sbox u_sbox9  (.byte_in(state_in[55:48]),   .byte_out(sb[55:48]));
    aes_sbox u_sbox10 (.byte_in(state_in[47:40]),   .byte_out(sb[47:40]));
    aes_sbox u_sbox11 (.byte_in(state_in[39:32]),   .byte_out(sb[39:32]));
    aes_sbox u_sbox12 (.byte_in(state_in[31:24]),   .byte_out(sb[31:24]));
    aes_sbox u_sbox13 (.byte_in(state_in[23:16]),   .byte_out(sb[23:16]));
    aes_sbox u_sbox14 (.byte_in(state_in[15:8]),    .byte_out(sb[15:8]));
    aes_sbox u_sbox15 (.byte_in(state_in[7:0]),     .byte_out(sb[7:0]));

    //--------------------------------------------------------------------------
    // Stage 2: ShiftRows — byte-wise permutation
    // Row 0: no shift
    //--------------------------------------------------------------------------
    assign sr[127:120] = sb[127:120];
    assign sr[95:88]   = sb[95:88];
    assign sr[63:56]   = sb[63:56];
    assign sr[31:24]   = sb[31:24];

    // Row 1: cyclic left shift by 1
    assign sr[119:112] = sb[87:80];
    assign sr[87:80]   = sb[55:48];
    assign sr[55:48]   = sb[23:16];
    assign sr[23:16]   = sb[119:112];

    // Row 2: cyclic left shift by 2
    assign sr[111:104] = sb[47:40];
    assign sr[79:72]   = sb[15:8];
    assign sr[47:40]   = sb[111:104];
    assign sr[15:8]    = sb[79:72];

    // Row 3: cyclic left shift by 3
    assign sr[103:96]  = sb[7:0];
    assign sr[71:64]   = sb[103:96];
    assign sr[39:32]   = sb[71:64];
    assign sr[7:0]     = sb[39:32];

    //--------------------------------------------------------------------------
    // GF(2^8) xtime helper: multiply by {02} in GF(2^8) with polynomial x^8+x^4+x^3+x+1
    //--------------------------------------------------------------------------
    function [7:0] xtime;
        input [7:0] x;
        xtime = {x[6:0], 1'b0} ^ (x[7] ? 8'h1b : 8'h00);
    endfunction

    //--------------------------------------------------------------------------
    // Stage 3: MixColumns — apply GF(2^8) matrix to each of the 4 columns
    //--------------------------------------------------------------------------

    // Column 0: bytes [127:120, 119:112, 111:104, 103:96]
    wire [7:0] c0_xt0, c0_xt1, c0_xt2, c0_xt3;
    assign c0_xt0 = xtime(sr[127:120]);
    assign c0_xt1 = xtime(sr[119:112]);
    assign c0_xt2 = xtime(sr[111:104]);
    assign c0_xt3 = xtime(sr[103:96]);

    assign mc[127:120] = c0_xt0 ^ c0_xt1 ^ sr[119:112] ^ sr[111:104] ^ sr[103:96];
    assign mc[119:112] = sr[127:120] ^ c0_xt1 ^ c0_xt2 ^ sr[111:104] ^ sr[103:96];
    assign mc[111:104] = sr[127:120] ^ sr[119:112] ^ c0_xt2 ^ c0_xt3 ^ sr[103:96];
    assign mc[103:96]  = c0_xt0 ^ sr[127:120] ^ sr[119:112] ^ sr[111:104] ^ c0_xt3;

    // Column 1: bytes [95:88, 87:80, 79:72, 71:64]
    wire [7:0] c1_xt0, c1_xt1, c1_xt2, c1_xt3;
    assign c1_xt0 = xtime(sr[95:88]);
    assign c1_xt1 = xtime(sr[87:80]);
    assign c1_xt2 = xtime(sr[79:72]);
    assign c1_xt3 = xtime(sr[71:64]);

    assign mc[95:88]  = c1_xt0 ^ c1_xt1 ^ sr[87:80] ^ sr[79:72] ^ sr[71:64];
    assign mc[87:80]  = sr[95:88] ^ c1_xt1 ^ c1_xt2 ^ sr[79:72] ^ sr[71:64];
    assign mc[79:72]  = sr[95:88] ^ sr[87:80] ^ c1_xt2 ^ c1_xt3 ^ sr[71:64];
    assign mc[71:64]  = c1_xt0 ^ sr[95:88] ^ sr[87:80] ^ sr[79:72] ^ c1_xt3;

    // Column 2: bytes [63:56, 55:48, 47:40, 39:32]
    wire [7:0] c2_xt0, c2_xt1, c2_xt2, c2_xt3;
    assign c2_xt0 = xtime(sr[63:56]);
    assign c2_xt1 = xtime(sr[55:48]);
    assign c2_xt2 = xtime(sr[47:40]);
    assign c2_xt3 = xtime(sr[39:32]);

    assign mc[63:56]  = c2_xt0 ^ c2_xt1 ^ sr[55:48] ^ sr[47:40] ^ sr[39:32];
    assign mc[55:48]  = sr[63:56] ^ c2_xt1 ^ c2_xt2 ^ sr[47:40] ^ sr[39:32];
    assign mc[47:40]  = sr[63:56] ^ sr[55:48] ^ c2_xt2 ^ c2_xt3 ^ sr[39:32];
    assign mc[39:32]  = c2_xt0 ^ sr[63:56] ^ sr[55:48] ^ sr[47:40] ^ c2_xt3;

    // Column 3: bytes [31:24, 23:16, 15:8, 7:0]
    wire [7:0] c3_xt0, c3_xt1, c3_xt2, c3_xt3;
    assign c3_xt0 = xtime(sr[31:24]);
    assign c3_xt1 = xtime(sr[23:16]);
    assign c3_xt2 = xtime(sr[15:8]);
    assign c3_xt3 = xtime(sr[7:0]);

    assign mc[31:24]  = c3_xt0 ^ c3_xt1 ^ sr[23:16] ^ sr[15:8] ^ sr[7:0];
    assign mc[23:16]  = sr[31:24] ^ c3_xt1 ^ c3_xt2 ^ sr[15:8] ^ sr[7:0];
    assign mc[15:8]   = sr[31:24] ^ sr[23:16] ^ c3_xt2 ^ c3_xt3 ^ sr[7:0];
    assign mc[7:0]    = c3_xt0 ^ sr[31:24] ^ sr[23:16] ^ sr[15:8] ^ c3_xt3;

    //--------------------------------------------------------------------------
    // Round 10 bypass: skip MixColumns for the final round
    //--------------------------------------------------------------------------
    assign pre_ark = (round == 4'd10) ? sr : mc;

    //--------------------------------------------------------------------------
    // Stage 4: AddRoundKey
    //--------------------------------------------------------------------------
    assign state_out = pre_ark ^ round_key;

endmodule

`default_nettype wire
