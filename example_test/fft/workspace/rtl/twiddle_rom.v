`resetall
`timescale 1ns / 1ps
`default_nettype none

// twiddle_rom.v -- ROM storing all 64 twiddle factors for 64-point FFT.
//
// Single unified ROM: 64 entries, W_64^k for k=0..63.
// Q1.15 format, 16-bit signed.
//   tw_re = cos(2*pi*k/64), tw_im = -sin(2*pi*k/64)
//
// Used by all stages that need twiddles.
// Address width = 6 bits (0..63).

module twiddle_rom #(
    parameter STAGE_IDX = 0,   // kept for API compat, not used internally
    parameter TWIDDLE_W = 16
)(
    input  wire [5:0]                  addr,
    output wire signed [TWIDDLE_W-1:0] tw_re,
    output wire signed [TWIDDLE_W-1:0] tw_im
);

    // -----------------------------------------------------------------------
    // Full 64-entry ROM
    // -----------------------------------------------------------------------
    reg signed [TWIDDLE_W-1:0] rom_re [0:63];
    reg signed [TWIDDLE_W-1:0] rom_im [0:63];

    // W_64^k = cos(2*pi*k/64) - j*sin(2*pi*k/64)
    // Q1.15: round(value * 32768), clamp to [-32768, 32767]
    initial begin
        // k=0..63: precomputed cos and -sin values
        rom_re[ 0] = 16'sd32767; rom_im[ 0] = 16'sd0;
        rom_re[ 1] = 16'sd32610; rom_im[ 1] = -16'sd3212;
        rom_re[ 2] = 16'sd32138; rom_im[ 2] = -16'sd6393;
        rom_re[ 3] = 16'sd31357; rom_im[ 3] = -16'sd9512;
        rom_re[ 4] = 16'sd30274; rom_im[ 4] = -16'sd12540;
        rom_re[ 5] = 16'sd28899; rom_im[ 5] = -16'sd15447;
        rom_re[ 6] = 16'sd27246; rom_im[ 6] = -16'sd18205;
        rom_re[ 7] = 16'sd25330; rom_im[ 7] = -16'sd20788;
        rom_re[ 8] = 16'sd23170; rom_im[ 8] = -16'sd23170;
        rom_re[ 9] = 16'sd20788; rom_im[ 9] = -16'sd25330;
        rom_re[10] = 16'sd18205; rom_im[10] = -16'sd27246;
        rom_re[11] = 16'sd15447; rom_im[11] = -16'sd28899;
        rom_re[12] = 16'sd12540; rom_im[12] = -16'sd30274;
        rom_re[13] = 16'sd9512;  rom_im[13] = -16'sd31357;
        rom_re[14] = 16'sd6393;  rom_im[14] = -16'sd32138;
        rom_re[15] = 16'sd3212;  rom_im[15] = -16'sd32610;
        rom_re[16] = 16'sd0;     rom_im[16] = -16'sd32768;
        rom_re[17] = -16'sd3212; rom_im[17] = -16'sd32610;
        rom_re[18] = -16'sd6393; rom_im[18] = -16'sd32138;
        rom_re[19] = -16'sd9512; rom_im[19] = -16'sd31357;
        rom_re[20] = -16'sd12540;rom_im[20] = -16'sd30274;
        rom_re[21] = -16'sd15447;rom_im[21] = -16'sd28899;
        rom_re[22] = -16'sd18205;rom_im[22] = -16'sd27246;
        rom_re[23] = -16'sd20788;rom_im[23] = -16'sd25330;
        rom_re[24] = -16'sd23170;rom_im[24] = -16'sd23170;
        rom_re[25] = -16'sd25330;rom_im[25] = -16'sd20788;
        rom_re[26] = -16'sd27246;rom_im[26] = -16'sd18205;
        rom_re[27] = -16'sd28899;rom_im[27] = -16'sd15447;
        rom_re[28] = -16'sd30274;rom_im[28] = -16'sd12540;
        rom_re[29] = -16'sd31357;rom_im[29] = -16'sd9512;
        rom_re[30] = -16'sd32138;rom_im[30] = -16'sd6393;
        rom_re[31] = -16'sd32610;rom_im[31] = -16'sd3212;
        rom_re[32] = -16'sd32768;rom_im[32] = 16'sd0;
        rom_re[33] = -16'sd32610;rom_im[33] = 16'sd3212;
        rom_re[34] = -16'sd32138;rom_im[34] = 16'sd6393;
        rom_re[35] = -16'sd31357;rom_im[35] = 16'sd9512;
        rom_re[36] = -16'sd30274;rom_im[36] = 16'sd12540;
        rom_re[37] = -16'sd28899;rom_im[37] = 16'sd15447;
        rom_re[38] = -16'sd27246;rom_im[38] = 16'sd18205;
        rom_re[39] = -16'sd25330;rom_im[39] = 16'sd20788;
        rom_re[40] = -16'sd23170;rom_im[40] = 16'sd23170;
        rom_re[41] = -16'sd20788;rom_im[41] = 16'sd25330;
        rom_re[42] = -16'sd18205;rom_im[42] = 16'sd27246;
        rom_re[43] = -16'sd15447;rom_im[43] = 16'sd28899;
        rom_re[44] = -16'sd12540;rom_im[44] = 16'sd30274;
        rom_re[45] = -16'sd9512;  rom_im[45] = 16'sd31357;
        rom_re[46] = -16'sd6393;  rom_im[46] = 16'sd32138;
        rom_re[47] = -16'sd3212;  rom_im[47] = 16'sd32610;
        rom_re[48] = 16'sd0;     rom_im[48] = 16'sd32767;
        rom_re[49] = 16'sd3212;  rom_im[49] = 16'sd32610;
        rom_re[50] = 16'sd6393;  rom_im[50] = 16'sd32138;
        rom_re[51] = 16'sd9512;  rom_im[51] = 16'sd31357;
        rom_re[52] = 16'sd12540; rom_im[52] = 16'sd30274;
        rom_re[53] = 16'sd15447; rom_im[53] = 16'sd28899;
        rom_re[54] = 16'sd18205; rom_im[54] = 16'sd27246;
        rom_re[55] = 16'sd20788; rom_im[55] = 16'sd25330;
        rom_re[56] = 16'sd23170; rom_im[56] = 16'sd23170;
        rom_re[57] = 16'sd25330; rom_im[57] = 16'sd20788;
        rom_re[58] = 16'sd27246; rom_im[58] = 16'sd18205;
        rom_re[59] = 16'sd28899; rom_im[59] = 16'sd15447;
        rom_re[60] = 16'sd30274; rom_im[60] = 16'sd12540;
        rom_re[61] = 16'sd31357; rom_im[61] = 16'sd9512;
        rom_re[62] = 16'sd32138; rom_im[62] = 16'sd6393;
        rom_re[63] = 16'sd32610; rom_im[63] = 16'sd3212;
    end

    // Combinational read
    assign tw_re = rom_re[addr];
    assign tw_im = rom_im[addr];

endmodule

`resetall
