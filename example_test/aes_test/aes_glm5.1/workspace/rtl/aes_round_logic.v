`resetall
`timescale 1ns / 1ps
`default_nettype none

module aes_round_logic
(
    input  wire [127:0] state_in,
    input  wire [127:0] round_key,
    input  wire [3:0]   round_num,
    output wire [127:0] state_out
);

// =========================================================================
// Stage 1: SubBytes - 16 parallel S-Box lookups
// =========================================================================
wire [7:0] sub_out_0,  sub_out_1,  sub_out_2,  sub_out_3;
wire [7:0] sub_out_4,  sub_out_5,  sub_out_6,  sub_out_7;
wire [7:0] sub_out_8,  sub_out_9,  sub_out_10, sub_out_11;
wire [7:0] sub_out_12, sub_out_13, sub_out_14, sub_out_15;

aes_sbox u_sbox_0  (.addr (state_in[127:120]), .dout (sub_out_0));
aes_sbox u_sbox_1  (.addr (state_in[119:112]), .dout (sub_out_1));
aes_sbox u_sbox_2  (.addr (state_in[111:104]), .dout (sub_out_2));
aes_sbox u_sbox_3  (.addr (state_in[103:96]),  .dout (sub_out_3));
aes_sbox u_sbox_4  (.addr (state_in[95:88]),   .dout (sub_out_4));
aes_sbox u_sbox_5  (.addr (state_in[87:80]),   .dout (sub_out_5));
aes_sbox u_sbox_6  (.addr (state_in[79:72]),   .dout (sub_out_6));
aes_sbox u_sbox_7  (.addr (state_in[71:64]),   .dout (sub_out_7));
aes_sbox u_sbox_8  (.addr (state_in[63:56]),   .dout (sub_out_8));
aes_sbox u_sbox_9  (.addr (state_in[55:48]),   .dout (sub_out_9));
aes_sbox u_sbox_10 (.addr (state_in[47:40]),   .dout (sub_out_10));
aes_sbox u_sbox_11 (.addr (state_in[39:32]),   .dout (sub_out_11));
aes_sbox u_sbox_12 (.addr (state_in[31:24]),   .dout (sub_out_12));
aes_sbox u_sbox_13 (.addr (state_in[23:16]),   .dout (sub_out_13));
aes_sbox u_sbox_14 (.addr (state_in[15:8]),    .dout (sub_out_14));
aes_sbox u_sbox_15 (.addr (state_in[7:0]),     .dout (sub_out_15));

wire [127:0] sub_out = {sub_out_0, sub_out_1, sub_out_2,  sub_out_3,
                        sub_out_4, sub_out_5, sub_out_6,  sub_out_7,
                        sub_out_8, sub_out_9, sub_out_10, sub_out_11,
                        sub_out_12, sub_out_13, sub_out_14, sub_out_15};

// =========================================================================
// Stage 2: ShiftRows - wire-level byte reordering
// =========================================================================
// State is stored in column-major order:
//   Byte index i maps to row = i%4, col = i/4
//   Byte positions in the 128-bit word:
//     [127:120]=s0  [119:112]=s1  [111:104]=s2  [103:96]=s3   (col 0)
//     [95:88]  =s4  [87:80]  =s5  [79:72]  =s6  [71:64] =s7   (col 1)
//     [63:56]  =s8  [55:48]  =s9  [47:40]  =s10 [39:32] =s11  (col 2)
//     [31:24]  =s12 [23:16]  =s13 [15:8]   =s14 [7:0]   =s15  (col 3)
//
// Row 0 (indices 0,4,8,12):  no shift
// Row 1 (indices 1,5,9,13):  shift left by 1 -> {5,9,13,1}
// Row 2 (indices 2,6,10,14): shift left by 2 -> {10,14,2,6}
// Row 3 (indices 3,7,11,15): shift left by 3 -> {15,3,7,11}

wire [127:0] shift_out;

assign shift_out[127:120] = sub_out_0;    // row 0, col 0 <- s0
assign shift_out[119:112] = sub_out_5;    // row 1, col 0 <- s5
assign shift_out[111:104] = sub_out_10;   // row 2, col 0 <- s10
assign shift_out[103:96]  = sub_out_15;   // row 3, col 0 <- s15

assign shift_out[95:88]   = sub_out_4;    // row 0, col 1 <- s4
assign shift_out[87:80]   = sub_out_9;    // row 1, col 1 <- s9
assign shift_out[79:72]   = sub_out_14;   // row 2, col 1 <- s14
assign shift_out[71:64]   = sub_out_3;    // row 3, col 1 <- s3

assign shift_out[63:56]   = sub_out_8;    // row 0, col 2 <- s8
assign shift_out[55:48]   = sub_out_13;   // row 1, col 2 <- s13
assign shift_out[47:40]   = sub_out_2;    // row 2, col 2 <- s2
assign shift_out[39:32]   = sub_out_7;    // row 3, col 2 <- s7

assign shift_out[31:24]   = sub_out_12;   // row 0, col 3 <- s12
assign shift_out[23:16]   = sub_out_1;    // row 1, col 3 <- s1
assign shift_out[15:8]    = sub_out_6;    // row 2, col 3 <- s6
assign shift_out[7:0]     = sub_out_11;   // row 3, col 3 <- s11

// =========================================================================
// Stage 3: MixColumns - GF(2^8) column mixing (bypassed for round 10)
// =========================================================================
// xtime(a) = (a << 1) ^ (0x1b if a[7] else 0), masked to 8 bits

function [7:0] xtime;
    input [7:0] a;
    begin
        xtime = (a[7]) ? ({a[6:0], 1'b0} ^ 8'h1b) : {a[6:0], 1'b0};
    end
endfunction

reg [127:0] mix_out;

always @* begin
    // Default: pass through (also covers round 10 bypass)
    mix_out = shift_out;

    if (round_num != 4'd10) begin
        // Column 0: bytes at [127:120], [119:112], [111:104], [103:96]
        begin : col0
            reg [7:0] s0, s1, s2, s3;
            reg [7:0] r0, r1, r2, r3;
            s0 = shift_out[127:120];
            s1 = shift_out[119:112];
            s2 = shift_out[111:104];
            s3 = shift_out[103:96];
            r0 = xtime(s0) ^ xtime(s1) ^ s1 ^ s2 ^ s3;
            r1 = s0 ^ xtime(s1) ^ xtime(s2) ^ s2 ^ s3;
            r2 = s0 ^ s1 ^ xtime(s2) ^ xtime(s3) ^ s3;
            r3 = xtime(s0) ^ s0 ^ s1 ^ s2 ^ xtime(s3);
            mix_out[127:120] = r0;
            mix_out[119:112] = r1;
            mix_out[111:104] = r2;
            mix_out[103:96]  = r3;
        end

        // Column 1: bytes at [95:88], [87:80], [79:72], [71:64]
        begin : col1
            reg [7:0] s0, s1, s2, s3;
            reg [7:0] r0, r1, r2, r3;
            s0 = shift_out[95:88];
            s1 = shift_out[87:80];
            s2 = shift_out[79:72];
            s3 = shift_out[71:64];
            r0 = xtime(s0) ^ xtime(s1) ^ s1 ^ s2 ^ s3;
            r1 = s0 ^ xtime(s1) ^ xtime(s2) ^ s2 ^ s3;
            r2 = s0 ^ s1 ^ xtime(s2) ^ xtime(s3) ^ s3;
            r3 = xtime(s0) ^ s0 ^ s1 ^ s2 ^ xtime(s3);
            mix_out[95:88] = r0;
            mix_out[87:80] = r1;
            mix_out[79:72] = r2;
            mix_out[71:64] = r3;
        end

        // Column 2: bytes at [63:56], [55:48], [47:40], [39:32]
        begin : col2
            reg [7:0] s0, s1, s2, s3;
            reg [7:0] r0, r1, r2, r3;
            s0 = shift_out[63:56];
            s1 = shift_out[55:48];
            s2 = shift_out[47:40];
            s3 = shift_out[39:32];
            r0 = xtime(s0) ^ xtime(s1) ^ s1 ^ s2 ^ s3;
            r1 = s0 ^ xtime(s1) ^ xtime(s2) ^ s2 ^ s3;
            r2 = s0 ^ s1 ^ xtime(s2) ^ xtime(s3) ^ s3;
            r3 = xtime(s0) ^ s0 ^ s1 ^ s2 ^ xtime(s3);
            mix_out[63:56] = r0;
            mix_out[55:48] = r1;
            mix_out[47:40] = r2;
            mix_out[39:32] = r3;
        end

        // Column 3: bytes at [31:24], [23:16], [15:8], [7:0]
        begin : col3
            reg [7:0] s0, s1, s2, s3;
            reg [7:0] r0, r1, r2, r3;
            s0 = shift_out[31:24];
            s1 = shift_out[23:16];
            s2 = shift_out[15:8];
            s3 = shift_out[7:0];
            r0 = xtime(s0) ^ xtime(s1) ^ s1 ^ s2 ^ s3;
            r1 = s0 ^ xtime(s1) ^ xtime(s2) ^ s2 ^ s3;
            r2 = s0 ^ s1 ^ xtime(s2) ^ xtime(s3) ^ s3;
            r3 = xtime(s0) ^ s0 ^ s1 ^ s2 ^ xtime(s3);
            mix_out[31:24] = r0;
            mix_out[23:16] = r1;
            mix_out[15:8]  = r2;
            mix_out[7:0]   = r3;
        end
    end
end

// =========================================================================
// Stage 4: AddRoundKey - XOR with round key
// =========================================================================
reg [127:0] state_out_r;

always @* begin
    state_out_r = mix_out ^ round_key;
end

assign state_out = state_out_r;

endmodule

`resetall
