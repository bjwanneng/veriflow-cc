// -----------------------------------------------------------------------------
// File   : sm3_w_gen.v
// Author : AI Designer
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   SM3 message expansion module using a 16-stage shift register. Generates
//   W_j and W'_j for each compression round. On load_en, the 512-bit message
//   block is split into 16 x 32-bit words loaded into w_reg[0..15]. During
//   calc_en, outputs W_j and W'_j are driven combinationally before the shift.
//   For rounds >= 16, the P1 expansion function computes the next word shifted
//   into w_reg[15].
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  AI Designer  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_w_gen
(
    input  wire           clk,
    input  wire           rst_n,
    input  wire           load_en,
    input  wire           calc_en,
    input  wire [511:0]   msg_block,
    input  wire [5:0]     round_cnt,
    output wire [31:0]    w_j,
    output wire [31:0]    w_prime_j
);

    ///////////////////////////////////////////////////////////////////////
    // Internal registers                                                //
    ///////////////////////////////////////////////////////////////////////

    // 16-entry shift register, each 32 bits wide
    reg [31:0] w_reg_0  = 32'd0, w_reg_0_next;
    reg [31:0] w_reg_1  = 32'd0, w_reg_1_next;
    reg [31:0] w_reg_2  = 32'd0, w_reg_2_next;
    reg [31:0] w_reg_3  = 32'd0, w_reg_3_next;
    reg [31:0] w_reg_4  = 32'd0, w_reg_4_next;
    reg [31:0] w_reg_5  = 32'd0, w_reg_5_next;
    reg [31:0] w_reg_6  = 32'd0, w_reg_6_next;
    reg [31:0] w_reg_7  = 32'd0, w_reg_7_next;
    reg [31:0] w_reg_8  = 32'd0, w_reg_8_next;
    reg [31:0] w_reg_9  = 32'd0, w_reg_9_next;
    reg [31:0] w_reg_10 = 32'd0, w_reg_10_next;
    reg [31:0] w_reg_11 = 32'd0, w_reg_11_next;
    reg [31:0] w_reg_12 = 32'd0, w_reg_12_next;
    reg [31:0] w_reg_13 = 32'd0, w_reg_13_next;
    reg [31:0] w_reg_14 = 32'd0, w_reg_14_next;
    reg [31:0] w_reg_15 = 32'd0, w_reg_15_next;

    ///////////////////////////////////////////////////////////////////////
    // Output assignments (combinational from shift register)            //
    ///////////////////////////////////////////////////////////////////////

    assign w_j       = w_reg_0;
    assign w_prime_j = w_reg_0 ^ w_reg_4;

    ///////////////////////////////////////////////////////////////////////
    // Helper wires for P1 expansion                                     //
    ///////////////////////////////////////////////////////////////////////

    // Intermediate signals for next_w computation (round >= 16)
    wire [31:0] tmp_xor_0_7     = w_reg_0 ^ w_reg_7;
    wire [31:0] rol_w13_15      = {w_reg_13[16:0], w_reg_13[31:17]};
    wire [31:0] tmp_xor_all     = tmp_xor_0_7 ^ rol_w13_15;

    // P1(tmp) = tmp ^ ROL(tmp, 15) ^ ROL(tmp, 23)
    wire [31:0] p1_input        = tmp_xor_all;
    wire [31:0] rol_p1_15       = {p1_input[16:0], p1_input[31:17]};
    wire [31:0] rol_p1_23       = {p1_input[8:0],  p1_input[31:9]};
    wire [31:0] p1_result       = p1_input ^ rol_p1_15 ^ rol_p1_23;

    // next_w = P1(tmp) ^ ROL(w_reg_3, 7) ^ w_reg_10
    wire [31:0] rol_w3_7        = {w_reg_3[24:0], w_reg_3[31:25]};
    wire [31:0] next_w_expanded = p1_result ^ rol_w3_7 ^ w_reg_10;

    ///////////////////////////////////////////////////////////////////////
    // Combinational next-state logic                                    //
    ///////////////////////////////////////////////////////////////////////

    always @* begin
        // Default: hold current values
        w_reg_0_next  = w_reg_0;
        w_reg_1_next  = w_reg_1;
        w_reg_2_next  = w_reg_2;
        w_reg_3_next  = w_reg_3;
        w_reg_4_next  = w_reg_4;
        w_reg_5_next  = w_reg_5;
        w_reg_6_next  = w_reg_6;
        w_reg_7_next  = w_reg_7;
        w_reg_8_next  = w_reg_8;
        w_reg_9_next  = w_reg_9;
        w_reg_10_next = w_reg_10;
        w_reg_11_next = w_reg_11;
        w_reg_12_next = w_reg_12;
        w_reg_13_next = w_reg_13;
        w_reg_14_next = w_reg_14;
        w_reg_15_next = w_reg_15;

        if (load_en) begin
            // Load message block into shift register
            // msg_block[511:480] -> w_reg[0], msg_block[479:448] -> w_reg[1], etc.
            w_reg_0_next  = msg_block[511:480];
            w_reg_1_next  = msg_block[479:448];
            w_reg_2_next  = msg_block[447:416];
            w_reg_3_next  = msg_block[415:384];
            w_reg_4_next  = msg_block[383:352];
            w_reg_5_next  = msg_block[351:320];
            w_reg_6_next  = msg_block[319:288];
            w_reg_7_next  = msg_block[287:256];
            w_reg_8_next  = msg_block[255:224];
            w_reg_9_next  = msg_block[223:192];
            w_reg_10_next = msg_block[191:160];
            w_reg_11_next = msg_block[159:128];
            w_reg_12_next = msg_block[127:96];
            w_reg_13_next = msg_block[95:64];
            w_reg_14_next = msg_block[63:32];
            w_reg_15_next = msg_block[31:0];
        end else if (calc_en) begin
            // Shift: w_reg[i] <= w_reg[i+1] for i=0..14
            w_reg_0_next  = w_reg_1;
            w_reg_1_next  = w_reg_2;
            w_reg_2_next  = w_reg_3;
            w_reg_3_next  = w_reg_4;
            w_reg_4_next  = w_reg_5;
            w_reg_5_next  = w_reg_6;
            w_reg_6_next  = w_reg_7;
            w_reg_7_next  = w_reg_8;
            w_reg_8_next  = w_reg_9;
            w_reg_9_next  = w_reg_10;
            w_reg_10_next = w_reg_11;
            w_reg_11_next = w_reg_12;
            w_reg_12_next = w_reg_13;
            w_reg_13_next = w_reg_14;
            w_reg_14_next = w_reg_15;

            // w_reg[15] gets next_w: expanded word W_{j+16}
            // Expansion is needed for ALL rounds since each round computes
            // the word that will be consumed 16 rounds later.
            w_reg_15_next = next_w_expanded;
        end
    end

    ///////////////////////////////////////////////////////////////////////
    // Sequential register update                                        //
    ///////////////////////////////////////////////////////////////////////

    always @(posedge clk) begin
        w_reg_0  <= w_reg_0_next;
        w_reg_1  <= w_reg_1_next;
        w_reg_2  <= w_reg_2_next;
        w_reg_3  <= w_reg_3_next;
        w_reg_4  <= w_reg_4_next;
        w_reg_5  <= w_reg_5_next;
        w_reg_6  <= w_reg_6_next;
        w_reg_7  <= w_reg_7_next;
        w_reg_8  <= w_reg_8_next;
        w_reg_9  <= w_reg_9_next;
        w_reg_10 <= w_reg_10_next;
        w_reg_11 <= w_reg_11_next;
        w_reg_12 <= w_reg_12_next;
        w_reg_13 <= w_reg_13_next;
        w_reg_14 <= w_reg_14_next;
        w_reg_15 <= w_reg_15_next;

        if (!rst_n) begin
            w_reg_0  <= 32'd0;
            w_reg_1  <= 32'd0;
            w_reg_2  <= 32'd0;
            w_reg_3  <= 32'd0;
            w_reg_4  <= 32'd0;
            w_reg_5  <= 32'd0;
            w_reg_6  <= 32'd0;
            w_reg_7  <= 32'd0;
            w_reg_8  <= 32'd0;
            w_reg_9  <= 32'd0;
            w_reg_10 <= 32'd0;
            w_reg_11 <= 32'd0;
            w_reg_12 <= 32'd0;
            w_reg_13 <= 32'd0;
            w_reg_14 <= 32'd0;
            w_reg_15 <= 32'd0;
        end
    end

endmodule

`resetall
