// -----------------------------------------------------------------------------
// File   : sm3_w_gen.v
// Author : VeriFlow
// Date   : 2026-05-09
// -----------------------------------------------------------------------------
// Description: SM3 message expansion via 16-stage shift register (GM/T 0004-2012).
//              Produces W_j and W'_j per round for the compression data path.
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_w_gen
(
    input  wire         clk,
    input  wire         rst_n,
    input  wire         load_en,
    input  wire         calc_en,
    input  wire [511:0] msg_block,
    input  wire [5:0]   round_cnt,
    output wire [31:0]  w_j,
    output wire [31:0]  w_prime_j
);

    // -----------------------------------------------------------------
    // Shift register: 16 x 32-bit words
    // w_reg[0] = W[j]  (current round's W word, head of shift register)
    // w_reg[15] = tail (replenishment target)
    // -----------------------------------------------------------------
    reg [31:0] w_reg_00 = 32'h00000000, w_reg_00_next;
    reg [31:0] w_reg_01 = 32'h00000000, w_reg_01_next;
    reg [31:0] w_reg_02 = 32'h00000000, w_reg_02_next;
    reg [31:0] w_reg_03 = 32'h00000000, w_reg_03_next;
    reg [31:0] w_reg_04 = 32'h00000000, w_reg_04_next;
    reg [31:0] w_reg_05 = 32'h00000000, w_reg_05_next;
    reg [31:0] w_reg_06 = 32'h00000000, w_reg_06_next;
    reg [31:0] w_reg_07 = 32'h00000000, w_reg_07_next;
    reg [31:0] w_reg_08 = 32'h00000000, w_reg_08_next;
    reg [31:0] w_reg_09 = 32'h00000000, w_reg_09_next;
    reg [31:0] w_reg_10 = 32'h00000000, w_reg_10_next;
    reg [31:0] w_reg_11 = 32'h00000000, w_reg_11_next;
    reg [31:0] w_reg_12 = 32'h00000000, w_reg_12_next;
    reg [31:0] w_reg_13 = 32'h00000000, w_reg_13_next;
    reg [31:0] w_reg_14 = 32'h00000000, w_reg_14_next;
    reg [31:0] w_reg_15 = 32'h00000000, w_reg_15_next;

    // -----------------------------------------------------------------
    // Combinational wires for expansion formula
    // -----------------------------------------------------------------
    wire [31:0] rol_w13_15;
    wire [31:0] xor_0_7_rol13;
    wire [31:0] p1_out;
    wire [31:0] rol_w03_07;
    wire [31:0] w_new_entry;

    // ROL(w_reg[13], 15):  15 left + 17 right = 32
    assign rol_w13_15 = {w_reg_13[16:0], w_reg_13[31:17]};

    // w_reg[0] ^ w_reg[7] ^ ROL(w_reg[13], 15)
    assign xor_0_7_rol13 = w_reg_00 ^ w_reg_07 ^ rol_w13_15;

    // P1(X) = X ^ ROL(X,15) ^ ROL(X,23)
    //   ROL(xor_0_7_rol13, 15): 15 left + 17 right = 32
    //   ROL(xor_0_7_rol13, 23): 23 left + 9 right  = 32
    assign p1_out = xor_0_7_rol13
                  ^ {xor_0_7_rol13[16:0], xor_0_7_rol13[31:17]}
                  ^ {xor_0_7_rol13[8:0],  xor_0_7_rol13[31:9]};

    // ROL(w_reg[3], 7): 7 left + 25 right = 32
    assign rol_w03_07 = {w_reg_03[24:0], w_reg_03[31:25]};

    // W[j+16] = P1(...) ^ ROL(w_reg[3], 7) ^ w_reg[10]
    // Unconditional replenishment (rule 23.5): always compute, always shift in.
    assign w_new_entry = p1_out ^ rol_w03_07 ^ w_reg_10;

    // -----------------------------------------------------------------
    // Combinational outputs (from current register state, before shift)
    // -----------------------------------------------------------------
    assign w_j       = w_reg_00;
    assign w_prime_j = w_reg_00 ^ w_reg_04;

    // -----------------------------------------------------------------
    // Block 1: Combinational next-state logic
    // -----------------------------------------------------------------
    always @* begin
        // Defaults: hold current values (no shift)
        w_reg_00_next = w_reg_00;
        w_reg_01_next = w_reg_01;
        w_reg_02_next = w_reg_02;
        w_reg_03_next = w_reg_03;
        w_reg_04_next = w_reg_04;
        w_reg_05_next = w_reg_05;
        w_reg_06_next = w_reg_06;
        w_reg_07_next = w_reg_07;
        w_reg_08_next = w_reg_08;
        w_reg_09_next = w_reg_09;
        w_reg_10_next = w_reg_10;
        w_reg_11_next = w_reg_11;
        w_reg_12_next = w_reg_12;
        w_reg_13_next = w_reg_13;
        w_reg_14_next = w_reg_14;
        w_reg_15_next = w_reg_15;

        if (load_en) begin
            // Load msg_block into shift register (big-endian: MSB word first)
            // msg_block[511:480] -> w_reg[0], msg_block[479:448] -> w_reg[1], ...
            // msg_block[31:0]    -> w_reg[15]
            w_reg_00_next = msg_block[511:480];
            w_reg_01_next = msg_block[479:448];
            w_reg_02_next = msg_block[447:416];
            w_reg_03_next = msg_block[415:384];
            w_reg_04_next = msg_block[383:352];
            w_reg_05_next = msg_block[351:320];
            w_reg_06_next = msg_block[319:288];
            w_reg_07_next = msg_block[287:256];
            w_reg_08_next = msg_block[255:224];
            w_reg_09_next = msg_block[223:192];
            w_reg_10_next = msg_block[191:160];
            w_reg_11_next = msg_block[159:128];
            w_reg_12_next = msg_block[127:96];
            w_reg_13_next = msg_block[95:64];
            w_reg_14_next = msg_block[63:32];
            w_reg_15_next = msg_block[31:0];
        end else if (calc_en) begin
            // Shift left: w_reg[i] <- w_reg[i+1], tail gets expansion result
            // Unconditional replenishment (rule 23.5): w_new_entry always computed
            w_reg_00_next = w_reg_01;
            w_reg_01_next = w_reg_02;
            w_reg_02_next = w_reg_03;
            w_reg_03_next = w_reg_04;
            w_reg_04_next = w_reg_05;
            w_reg_05_next = w_reg_06;
            w_reg_06_next = w_reg_07;
            w_reg_07_next = w_reg_08;
            w_reg_08_next = w_reg_09;
            w_reg_09_next = w_reg_10;
            w_reg_10_next = w_reg_11;
            w_reg_11_next = w_reg_12;
            w_reg_12_next = w_reg_13;
            w_reg_13_next = w_reg_14;
            w_reg_14_next = w_reg_15;
            w_reg_15_next = w_new_entry;
        end
    end

    // -----------------------------------------------------------------
    // Block 2: Sequential register update
    // -----------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            w_reg_00 <= 32'h00000000;
            w_reg_01 <= 32'h00000000;
            w_reg_02 <= 32'h00000000;
            w_reg_03 <= 32'h00000000;
            w_reg_04 <= 32'h00000000;
            w_reg_05 <= 32'h00000000;
            w_reg_06 <= 32'h00000000;
            w_reg_07 <= 32'h00000000;
            w_reg_08 <= 32'h00000000;
            w_reg_09 <= 32'h00000000;
            w_reg_10 <= 32'h00000000;
            w_reg_11 <= 32'h00000000;
            w_reg_12 <= 32'h00000000;
            w_reg_13 <= 32'h00000000;
            w_reg_14 <= 32'h00000000;
            w_reg_15 <= 32'h00000000;
        end else begin
            w_reg_00 <= w_reg_00_next;
            w_reg_01 <= w_reg_01_next;
            w_reg_02 <= w_reg_02_next;
            w_reg_03 <= w_reg_03_next;
            w_reg_04 <= w_reg_04_next;
            w_reg_05 <= w_reg_05_next;
            w_reg_06 <= w_reg_06_next;
            w_reg_07 <= w_reg_07_next;
            w_reg_08 <= w_reg_08_next;
            w_reg_09 <= w_reg_09_next;
            w_reg_10 <= w_reg_10_next;
            w_reg_11 <= w_reg_11_next;
            w_reg_12 <= w_reg_12_next;
            w_reg_13 <= w_reg_13_next;
            w_reg_14 <= w_reg_14_next;
            w_reg_15 <= w_reg_15_next;
        end
    end

endmodule

`resetall
